"""File-writing agents (Implementation, Test, Refactor, Documentation).

These agents share the same output protocol: ``### FILE: <path>`` blocks.
The base class :class:`FileWritingAgent` handles parsing & writing; each
concrete subclass overrides ``allowed_roots`` and ``build_prompt``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..memory import ProjectMemory
from ..models import ModelManager
from .base import Agent, AgentResult
from .parsing import parse_file_blocks


class FileWritingAgent(Agent):
    """Base for agents that emit `### FILE:` blocks."""

    #: Tuple of relpath prefixes the agent is allowed to write to.
    allowed_roots: ClassVar[tuple[str, ...]] = ()

    #: The hand-off file this agent writes after producing files.
    handoff_name: ClassVar[str] = ""
    handoff_body: ClassVar[str] = ""

    #: Optional path to capture an `IMPLEMENTATION_LOG`-style trailer.
    log_artifact: ClassVar[str | None] = None
    log_section_marker: ClassVar[str] = "### IMPLEMENTATION_LOG"

    async def run(self, memory: ProjectMemory, manager: ModelManager,
                  *, cycle: int = 1,
                  context: dict[str, Any] | None = None) -> AgentResult:
        prompt = self.build_prompt(memory, cycle=cycle, context=context or {})
        text = await self._generate(manager, prompt=prompt)

        blocks = parse_file_blocks(text)
        written: list[str] = []
        rejected: list[str] = []
        for blk in blocks:
            if not self._is_allowed(blk.path):
                rejected.append(blk.path)
                continue
            ref = memory.write_text(blk.path, blk.body)
            written.append(ref.relpath)

        # Capture trailing log (if present) into IMPLEMENTATION_LOG.md.
        if self.log_artifact and self.log_section_marker in text:
            tail = text.split(self.log_section_marker, 1)[1].strip()
            if tail:
                existing = memory.read_text(self.log_artifact)
                stamp = f"\n\n---\n\n## {self.role.title()} (cycle {cycle})\n\n{tail}\n"
                memory.write_text(self.log_artifact, existing.rstrip() + stamp)
                written.append(self.log_artifact)

        # Write hand-off pointer.
        if self.handoff_name:
            ho_ref = memory.write_handoff(self.handoff_name,
                                          self.handoff_body.strip() + "\n")
            written.append(ho_ref.relpath)

        notes_lines = []
        if rejected:
            notes_lines.append(
                "Rejected file blocks (path outside allowed roots): "
                + ", ".join(rejected)
            )
        notes = "\n".join(notes_lines)

        return AgentResult(
            role=self.role,
            success=bool(blocks) and not rejected,
            written_artifacts=written,
            raw_output=text,
            notes=notes,
            extra={"file_blocks": len(blocks),
                   "rejected_paths": rejected},
        )

    # -- Hooks ------------------------------------------------------------ #

    def build_prompt(self, memory: ProjectMemory, *,
                     cycle: int, context: dict[str, Any]) -> str:
        raise NotImplementedError

    def _is_allowed(self, path: str) -> bool:
        if not self.allowed_roots:
            return True
        norm = path.replace("\\", "/").lstrip("./")
        return any(norm.startswith(root) for root in self.allowed_roots)


# --------------------------------------------------------------------------- #
#  Implementation
# --------------------------------------------------------------------------- #


class ImplementationAgent(FileWritingAgent):
    role = "implementation"
    allowed_roots = ("src/", "tests/conftest.py", "pyproject.toml",
                     "package.json", "tsconfig.json")
    handoff_name = "impl_to_test.md"
    log_artifact = "IMPLEMENTATION_LOG.md"
    handoff_body = (
        "# Implementation -> Test Handoff\n\n"
        "Source code is in `src/`. Architecture lives in `ARCHITECTURE.md`. "
        "The Test agent must cover every public symbol with happy-path, "
        "edge-case, and failure-path tests."
    )

    def build_prompt(self, memory, *, cycle, context):
        prompt = (
            f"You are running the **implement** phase (cycle {cycle}).\n\n"
            "## TASK.md\n\n" + memory.read_text("TASK.md") + "\n\n"
            "## ARCHITECTURE.md\n\n" + memory.read_text("ARCHITECTURE.md") + "\n\n"
            "## handoffs/architect_to_impl.md\n\n"
            + memory.read_text("handoffs/architect_to_impl.md") + "\n"
        )

        # Include current source tree so the agent can iterate, not rebuild.
        existing = memory.collect_source_tree(max_files=80,
                                              max_bytes_per_file=20_000)
        if existing:
            prompt += "\n## Existing source tree (full overwrites only)\n"
            for rel, body in existing.items():
                prompt += f"\n### Existing FILE: {rel}\n```\n{body}\n```\n"

        # If we are looping after a test failure, surface those.
        test_results = memory.read_text("TEST_RESULTS.md")
        if cycle > 1 and test_results.strip() and test_results.strip() != "# Test Results":
            prompt += (
                "\n## Most recent TEST_RESULTS.md (you must fix these failures)\n\n"
                + test_results + "\n"
            )

        prompt += (
            "\nEmit `### FILE: <path>` blocks for every file you create or "
            "modify. NEVER truncate. Conclude (optionally) with "
            "`### IMPLEMENTATION_LOG` notes for the Review agent."
        )
        return prompt


# --------------------------------------------------------------------------- #
#  Test
# --------------------------------------------------------------------------- #


class TestAgent(FileWritingAgent):
    role = "test"
    allowed_roots = ("tests/", "pytest.ini", "pyproject.toml",
                     "package.json", "jest.config.js")
    handoff_name = "test_to_review.md"
    log_artifact = "IMPLEMENTATION_LOG.md"
    log_section_marker = "### TEST_PLAN"
    handoff_body = (
        "# Test -> Review Handoff\n\n"
        "Tests live under `tests/`. Concrete results (after running) are "
        "captured separately in `TEST_RESULTS.md` by the orchestrator."
    )

    def build_prompt(self, memory, *, cycle, context):
        prompt = (
            f"You are running the **test** phase (cycle {cycle}).\n\n"
            "## ARCHITECTURE.md\n\n" + memory.read_text("ARCHITECTURE.md") + "\n\n"
            "## handoffs/impl_to_test.md\n\n"
            + memory.read_text("handoffs/impl_to_test.md") + "\n\n"
            "## Source tree to test\n"
        )
        for rel, body in memory.collect_source_tree(
                max_files=80, max_bytes_per_file=20_000).items():
            prompt += f"\n### FILE (read-only): {rel}\n```\n{body}\n```\n"

        # Show prior failing results if any.
        results = memory.read_text("TEST_RESULTS.md")
        if cycle > 1 and results.strip() and results.strip() != "# Test Results":
            prompt += (
                "\n## Prior TEST_RESULTS.md\n\n" + results + "\n"
                "Improve coverage and address any gaps the failures revealed.\n"
            )

        prompt += (
            "\nEmit `### FILE: tests/...` blocks. Conclude with a "
            "`### TEST_PLAN` section listing every behaviour you cover."
        )
        return prompt


# --------------------------------------------------------------------------- #
#  Refactor
# --------------------------------------------------------------------------- #


class RefactorAgent(FileWritingAgent):
    role = "refactor"
    allowed_roots = ("src/", "tests/", "pyproject.toml")
    handoff_name = "refactor_to_review.md"
    log_artifact = "IMPLEMENTATION_LOG.md"
    log_section_marker = "### CHANGE_LOG"
    handoff_body = (
        "# Refactor -> Review Handoff\n\n"
        "Code revised in response to `REVIEW.md` and `SECURITY.md`. "
        "The Review agent should re-score and confirm findings are "
        "addressed."
    )

    def build_prompt(self, memory, *, cycle, context):
        prompt = (
            f"You are running the **refactor** phase (cycle {cycle}).\n\n"
            "## REVIEW.md\n\n" + memory.read_text("REVIEW.md") + "\n\n"
            "## SECURITY.md\n\n" + memory.read_text("SECURITY.md") + "\n\n"
            "## handoffs/review_to_refactor.md\n\n"
            + memory.read_text("handoffs/review_to_refactor.md") + "\n\n"
            "## handoffs/security_to_refactor.md\n\n"
            + memory.read_text("handoffs/security_to_refactor.md") + "\n\n"
            "## Current source tree\n"
        )
        for rel, body in memory.collect_source_tree(
                max_files=120, max_bytes_per_file=20_000).items():
            prompt += f"\n### FILE: {rel}\n```\n{body}\n```\n"

        prompt += (
            "\nEmit revised `### FILE:` blocks for every file you change "
            "(full contents). Conclude with `### CHANGE_LOG` mapping "
            "findings -> changes."
        )
        return prompt


# --------------------------------------------------------------------------- #
#  Documentation
# --------------------------------------------------------------------------- #


class DocumentationAgent(FileWritingAgent):
    role = "documentation"
    allowed_roots = ("README.md", "docs/")
    handoff_name = "doc_to_audit.md"
    handoff_body = (
        "# Documentation -> Audit Handoff\n\n"
        "User-facing docs updated. The Final Auditor should verify they "
        "match the actual code."
    )

    def build_prompt(self, memory, *, cycle, context):
        prompt = (
            f"You are running the **document** phase (cycle {cycle}).\n\n"
            "## ARCHITECTURE.md\n\n" + memory.read_text("ARCHITECTURE.md") + "\n\n"
            "## Existing README.md\n\n" + memory.read_text("README.md") + "\n\n"
            "## Source tree (use to verify accuracy)\n"
        )
        for rel, body in memory.collect_source_tree(
                max_files=80, max_bytes_per_file=12_000).items():
            prompt += f"\n### FILE (read-only): {rel}\n```\n{body}\n```\n"

        prompt += (
            "\nEmit `### FILE: README.md` and `### FILE: docs/...` blocks. "
            "Examples must be exact and runnable as written."
        )
        return prompt


__all__ = [
    "FileWritingAgent",
    "ImplementationAgent",
    "TestAgent",
    "RefactorAgent",
    "DocumentationAgent",
]
