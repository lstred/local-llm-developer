"""Filesystem-backed project memory.

Every job operates inside a *project workspace* with the canonical layout
described in the README. The :class:`ProjectMemory` class is the single
gateway agents use to read or write artifacts. Hand-off documents live
under ``handoffs/`` and form the explicit contract between phases - no
agent is allowed to depend on conversation context for prior outputs.

Design goals:
    * **Atomic writes** - never leave half-written files visible.
    * **Versioning** - every overwrite of a top-level artifact is archived
      under ``artifacts/<name>/<timestamp>.md`` so we can diff revisions.
    * **Structured logging** - each artifact write is appended to
      ``handoffs/_log.jsonl`` for resume / observability.
    * **Safety** - all paths are sandboxed inside the workspace root.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..logging_setup import get_logger

log = get_logger(__name__)


CANONICAL_DIRS = ("src", "tests", "docs", "artifacts", "handoffs")
CANONICAL_FILES = (
    "TASK.md",
    "PLAN.md",
    "ARCHITECTURE.md",
    "IMPLEMENTATION_LOG.md",
    "REVIEW.md",
    "BUGS.md",
    "SECURITY.md",
    "TEST_RESULTS.md",
    "AUDIT.md",
    "README.md",
)


@dataclass(frozen=True)
class ArtifactRef:
    relpath: str
    bytes_written: int
    sha_short: str


class ProjectMemory:
    """Sandboxed read/write access to a single project workspace."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # -- Layout ----------------------------------------------------------- #

    def ensure_layout(self) -> None:
        for d in CANONICAL_DIRS:
            (self.root / d).mkdir(parents=True, exist_ok=True)
        for f in CANONICAL_FILES:
            p = self.root / f
            if not p.exists():
                p.write_text(f"# {f.replace('.md', '').replace('_', ' ').title()}\n",
                             encoding="utf-8")

    # -- Path safety ------------------------------------------------------ #

    def _safe(self, relpath: str | Path) -> Path:
        p = (self.root / relpath).resolve()
        try:
            p.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Path escapes workspace: {relpath}") from exc
        return p

    def abs(self, relpath: str | Path) -> Path:
        return self._safe(relpath)

    def exists(self, relpath: str | Path) -> bool:
        try:
            return self._safe(relpath).exists()
        except ValueError:
            return False

    # -- Read ------------------------------------------------------------- #

    def read_text(self, relpath: str | Path, default: str = "") -> str:
        p = self._safe(relpath)
        if not p.exists():
            return default
        return p.read_text(encoding="utf-8", errors="replace")

    def read_many(self, relpaths: Iterable[str]) -> dict[str, str]:
        return {rp: self.read_text(rp) for rp in relpaths}

    def list_glob(self, pattern: str) -> list[Path]:
        # Defensive - reject absolute patterns or escapes.
        if Path(pattern).is_absolute():
            raise ValueError("Absolute glob patterns are not allowed")
        return [p for p in self.root.glob(pattern) if p.is_file()]

    def collect_source_tree(self, max_files: int = 200,
                            max_bytes_per_file: int = 64 * 1024) -> dict[str, str]:
        """Return a snapshot of ``src/**`` and ``tests/**`` for handoff."""
        snapshot: dict[str, str] = {}
        for sub in ("src", "tests"):
            base = self.root / sub
            if not base.exists():
                continue
            for p in sorted(base.rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(self.root).as_posix()
                try:
                    data = p.read_bytes()
                except OSError:
                    continue
                if len(data) > max_bytes_per_file:
                    snapshot[rel] = (
                        data[:max_bytes_per_file].decode("utf-8", errors="replace")
                        + f"\n...[truncated {len(data) - max_bytes_per_file} bytes]..."
                    )
                else:
                    snapshot[rel] = data.decode("utf-8", errors="replace")
                if len(snapshot) >= max_files:
                    break
        return snapshot

    # -- Write (atomic + versioned) -------------------------------------- #

    def write_text(self, relpath: str | Path, content: str, *,
                   archive: bool = True) -> ArtifactRef:
        target = self._safe(relpath)
        target.parent.mkdir(parents=True, exist_ok=True)

        # If archiving, snapshot prior version before overwrite.
        if archive and target.exists():
            self._archive(target)

        # Atomic write via tempfile + os.replace
        fd, tmp_path = tempfile.mkstemp(prefix=".lld_", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            os.replace(tmp_path, target)
        except Exception:
            # Best-effort cleanup
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        ref = ArtifactRef(
            relpath=str(target.relative_to(self.root).as_posix()),
            bytes_written=len(content.encode("utf-8")),
            sha_short=_short_hash(content),
        )
        self._log_write(ref)
        return ref

    def write_handoff(self, name: str, content: str) -> ArtifactRef:
        return self.write_text(f"handoffs/{name}", content, archive=True)

    def append_log(self, relpath: str, line: str) -> None:
        p = self._safe(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line.rstrip("\n") + "\n")

    # -- Internal --------------------------------------------------------- #

    def _archive(self, target: Path) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rel = target.relative_to(self.root).as_posix().replace("/", "__")
        archive_dir = self.root / "artifacts" / rel
        archive_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(target, archive_dir / f"{ts}{target.suffix or '.txt'}")
        except OSError as exc:
            log.warning("memory.archive_failed",
                        extra={"target": str(target), "error": str(exc)})

    def _log_write(self, ref: ArtifactRef) -> None:
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "artifact.write",
            "path": ref.relpath,
            "bytes": ref.bytes_written,
            "sha": ref.sha_short,
        })
        self.append_log("handoffs/_log.jsonl", line)


def _short_hash(content: str) -> str:
    import hashlib
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


__all__ = ["ProjectMemory", "ArtifactRef", "CANONICAL_DIRS", "CANONICAL_FILES"]
