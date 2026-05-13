"""Tests for project memory: layout, atomic writes, sandboxing, archiving."""

from __future__ import annotations

from pathlib import Path

import pytest

from lld.memory import CANONICAL_DIRS, CANONICAL_FILES, ProjectMemory


def test_ensure_layout_creates_canonical_structure(tmp_path: Path):
    pm = ProjectMemory(tmp_path)
    pm.ensure_layout()
    for d in CANONICAL_DIRS:
        assert (tmp_path / d).is_dir()
    for f in CANONICAL_FILES:
        assert (tmp_path / f).is_file()


def test_write_text_archives_prior_version(tmp_path: Path):
    pm = ProjectMemory(tmp_path)
    pm.write_text("PLAN.md", "v1")
    pm.write_text("PLAN.md", "v2")
    archive_dir = tmp_path / "artifacts" / "PLAN.md"
    assert archive_dir.is_dir()
    archived = list(archive_dir.glob("*.md"))
    assert len(archived) >= 1
    # Newest content on disk
    assert (tmp_path / "PLAN.md").read_text() == "v2"


def test_write_text_rejects_path_escapes(tmp_path: Path):
    pm = ProjectMemory(tmp_path)
    with pytest.raises(ValueError):
        pm.write_text("../escape.txt", "bad")
    with pytest.raises(ValueError):
        pm.write_text("subdir/../../escape.txt", "bad")


def test_handoff_writes_under_handoffs(tmp_path: Path):
    pm = ProjectMemory(tmp_path)
    ref = pm.write_handoff("plan_to_architect.md", "hi")
    assert ref.relpath == "handoffs/plan_to_architect.md"
    assert (tmp_path / "handoffs" / "plan_to_architect.md").read_text() == "hi"


def test_collect_source_tree(tmp_path: Path):
    pm = ProjectMemory(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "src" / "deep").mkdir()
    (tmp_path / "src" / "deep" / "b.py").write_text("x = 1\n", encoding="utf-8")
    snap = pm.collect_source_tree()
    assert "src/a.py" in snap and "src/deep/b.py" in snap


def test_collect_source_tree_truncates_huge_files(tmp_path: Path):
    pm = ProjectMemory(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "big.py").write_text("x" * 200_000, encoding="utf-8")
    snap = pm.collect_source_tree(max_bytes_per_file=1024)
    assert "[truncated" in snap["src/big.py"]
