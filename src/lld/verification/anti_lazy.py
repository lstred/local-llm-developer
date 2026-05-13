"""Anti-lazy heuristics.

The platform refuses to accept agent output that exhibits common
"laziness" patterns (TODOs, placeholder strings, empty bodies, fake tests,
hallucinated mocks, etc.). The detectors here run after the implementation,
test, and refactor phases. Any finding is surfaced to the orchestrator,
which (per ``settings.verification.anti_lazy.*``) blocks progression.

Detectors are intentionally simple and fast - they are pre-filters, not
a substitute for the Review and Final Auditor agents. False positives are
preferred over false negatives.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import AntiLazySettings


# --------------------------------------------------------------------------- #
#  Patterns
# --------------------------------------------------------------------------- #

# Comment-style TODO/FIXME/XXX markers (any source language with // # or --).
_TODO_RX = re.compile(
    r"(?P<prefix>//|#|--|/\*|\*)\s*(TODO|FIXME|XXX|HACK|STUB|PLACEHOLDER)\b",
    re.IGNORECASE,
)

# String placeholders the model loves to invent.
_PLACEHOLDER_STRINGS_RX = re.compile(
    r"\b("
    r"placeholder|"
    r"fill[_\- ]?in|"
    r"replace[_\- ]?me|"
    r"your[_\- ]?code[_\- ]?here|"
    r"implement[_\- ]?this|"
    r"to[_\- ]?be[_\- ]?implemented|"
    r"not[_\- ]?implemented[_\- ]?yet|"
    r"dummy[_\- ]?value"
    r")\b",
    re.IGNORECASE,
)

# Python `raise NotImplementedError(...)` pattern outside abstract methods.
_NOTIMPL_RX = re.compile(r"\braise\s+NotImplementedError\b")

# JS/TS placeholder throws.
_JS_THROW_NOTIMPL_RX = re.compile(
    r"throw\s+new\s+Error\s*\(\s*['\"](not\s*implemented|todo|placeholder)",
    re.IGNORECASE,
)

# Generic "mock" / "fake" usage in source (NOT in tests).
_MOCK_USAGE_RX = re.compile(r"\b(mock|fake|stub)[_\-A-Za-z]*\s*=", re.IGNORECASE)


SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                     ".java", ".kt", ".rb", ".cs", ".cpp", ".c", ".h", ".hpp"}


# --------------------------------------------------------------------------- #
#  Findings
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    rule: str
    path: str
    line: int
    snippet: str
    severity: str = "error"   # "error" blocks; "warning" only flags

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "path": self.path,
            "line": self.line,
            "snippet": self.snippet,
            "severity": self.severity,
        }


# --------------------------------------------------------------------------- #
#  Detector
# --------------------------------------------------------------------------- #


class AntiLazyDetector:
    """Scans a workspace for low-effort / placeholder code."""

    def __init__(self, settings: AntiLazySettings, *,
                 mock_explicitly_requested: bool = False) -> None:
        self.s = settings
        self.mock_explicitly_requested = mock_explicitly_requested

    def scan_workspace(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        for path in self._iter_source_files(root):
            findings.extend(self.scan_file(path, root))
        return findings

    def scan_file(self, path: Path, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return findings

        is_test = self._is_test_file(rel)

        # 1. TODO / FIXME / placeholder comments
        if self.s.forbid_todo_comments:
            for ln, line in enumerate(text.splitlines(), start=1):
                if _TODO_RX.search(line):
                    findings.append(Finding(
                        "todo_comment", rel, ln, line.strip()[:200]))

        # 2. Placeholder strings/identifiers
        if self.s.forbid_placeholder_strings:
            for ln, line in enumerate(text.splitlines(), start=1):
                if _PLACEHOLDER_STRINGS_RX.search(line):
                    findings.append(Finding(
                        "placeholder_string", rel, ln, line.strip()[:200]))

        # 3. NotImplementedError / throw-not-implemented
        if self.s.forbid_notimplemented:
            for ln, line in enumerate(text.splitlines(), start=1):
                if _NOTIMPL_RX.search(line) or _JS_THROW_NOTIMPL_RX.search(line):
                    findings.append(Finding(
                        "not_implemented", rel, ln, line.strip()[:200]))

        # 4. Empty / pass-only function bodies & empty test bodies (Python).
        if path.suffix == ".py":
            findings.extend(self._scan_python_bodies(text, rel, is_test))

        # 5. Mock usage in non-test source unless explicitly requested.
        if (self.s.forbid_mock_unless_requested
                and not self.mock_explicitly_requested
                and not is_test):
            for ln, line in enumerate(text.splitlines(), start=1):
                if _MOCK_USAGE_RX.search(line):
                    findings.append(Finding(
                        "mock_in_production", rel, ln, line.strip()[:200],
                        severity="warning"))

        return findings

    # -- helpers ---------------------------------------------------------- #

    def _iter_source_files(self, root: Path):
        for sub in ("src", "tests"):
            base = root / sub
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if p.is_file() and p.suffix.lower() in SOURCE_EXTENSIONS:
                    yield p

    @staticmethod
    def _is_test_file(rel: str) -> bool:
        rel_lower = rel.lower()
        return (
            rel_lower.startswith("tests/")
            or "/tests/" in rel_lower
            or "/test_" in rel_lower
            or rel_lower.endswith("_test.py")
            or rel_lower.endswith(".test.ts")
            or rel_lower.endswith(".test.js")
            or rel_lower.endswith(".spec.ts")
            or rel_lower.endswith(".spec.js")
        )

    def _scan_python_bodies(self, text: str, rel: str, is_test: bool) -> list[Finding]:
        out: list[Finding] = []
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            out.append(Finding(
                "syntax_error", rel, exc.lineno or 1,
                (exc.msg or "syntax error")[:200],
                severity="error"))
            return out

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                # Strip a leading docstring before judging the body.
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    body = body[1:]

                # Allow truly abstract methods (decorated @abstractmethod).
                if any(self._is_abstract_decorator(d) for d in node.decorator_list):
                    continue

                if self.s.forbid_pass_only_bodies and self._is_pass_only(body):
                    out.append(Finding(
                        "empty_function_body", rel, node.lineno,
                        f"def {node.name}(): pass"))

                if (is_test and self.s.forbid_empty_test_bodies
                        and node.name.startswith("test_")
                        and self._is_trivial_test_body(body)):
                    out.append(Finding(
                        "empty_test_body", rel, node.lineno,
                        f"test {node.name} has no real assertions"))
        return out

    @staticmethod
    def _is_abstract_decorator(d: ast.expr) -> bool:
        if isinstance(d, ast.Name):
            return d.id == "abstractmethod"
        if isinstance(d, ast.Attribute):
            return d.attr == "abstractmethod"
        return False

    @staticmethod
    def _is_pass_only(body: list[ast.stmt]) -> bool:
        if not body:
            return True
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            return True
        if len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(
            body[0].value, ast.Constant) and body[0].value.value is Ellipsis:
            return True
        return False

    @staticmethod
    def _is_trivial_test_body(body: list[ast.stmt]) -> bool:
        if not body:
            return True
        # Walk the entire body subtree: a real test must contain at least one
        # assertion, raise, or call (covers `assert x`, `with pytest.raises(...):`,
        # `self.assertEqual(...)`, `await client.get(...)`, etc.).
        for stmt in body:
            for n in ast.walk(stmt):
                if isinstance(n, (ast.Assert, ast.Raise, ast.Call)):
                    return False
        return True


__all__ = ["AntiLazyDetector", "Finding"]
