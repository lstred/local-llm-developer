"""Tests for the anti-lazy detector."""

from __future__ import annotations

from pathlib import Path

from lld.config import AntiLazySettings
from lld.verification.anti_lazy import AntiLazyDetector


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_detects_todo_comment(tmp_path: Path):
    _write(tmp_path, "src/a.py",
           "def f():\n    # TODO: implement this later\n    return 1\n")
    findings = AntiLazyDetector(AntiLazySettings()).scan_workspace(tmp_path)
    rules = {f.rule for f in findings}
    assert "todo_comment" in rules


def test_detects_pass_only_body(tmp_path: Path):
    _write(tmp_path, "src/a.py", "def f():\n    pass\n")
    findings = AntiLazyDetector(AntiLazySettings()).scan_workspace(tmp_path)
    assert any(f.rule == "empty_function_body" for f in findings)


def test_allows_abstractmethod_pass(tmp_path: Path):
    _write(
        tmp_path, "src/a.py",
        "from abc import ABC, abstractmethod\n"
        "class Base(ABC):\n"
        "    @abstractmethod\n"
        "    def f(self):\n"
        "        pass\n",
    )
    findings = AntiLazyDetector(AntiLazySettings()).scan_workspace(tmp_path)
    assert not any(f.rule == "empty_function_body" for f in findings)


def test_detects_not_implemented(tmp_path: Path):
    _write(
        tmp_path, "src/a.py",
        "def f():\n    raise NotImplementedError('soon')\n",
    )
    findings = AntiLazyDetector(AntiLazySettings()).scan_workspace(tmp_path)
    assert any(f.rule == "not_implemented" for f in findings)


def test_detects_placeholder_string(tmp_path: Path):
    _write(
        tmp_path, "src/a.py",
        "def f():\n    return 'placeholder value'\n",
    )
    findings = AntiLazyDetector(AntiLazySettings()).scan_workspace(tmp_path)
    assert any(f.rule == "placeholder_string" for f in findings)


def test_detects_empty_test_body(tmp_path: Path):
    _write(
        tmp_path, "tests/test_x.py",
        "def test_nothing():\n    x = 1\n",   # no assert, no call
    )
    findings = AntiLazyDetector(AntiLazySettings()).scan_workspace(tmp_path)
    assert any(f.rule == "empty_test_body" for f in findings)


def test_clean_code_is_clean(tmp_path: Path):
    _write(
        tmp_path, "src/a.py",
        "def add(a: int, b: int) -> int:\n"
        "    \"\"\"Add two ints.\"\"\"\n"
        "    if not isinstance(a, int) or not isinstance(b, int):\n"
        "        raise TypeError('ints required')\n"
        "    return a + b\n",
    )
    _write(
        tmp_path, "tests/test_a.py",
        "from src.a import add\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
    )
    findings = AntiLazyDetector(AntiLazySettings()).scan_workspace(tmp_path)
    blocking = [f for f in findings if f.severity == "error"]
    assert blocking == []
