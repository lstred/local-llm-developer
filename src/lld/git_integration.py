"""Optional Git integration.

The orchestrator commits a snapshot of the workspace after every phase
when ``settings.git.auto_commit_per_phase`` is true. The repository is
initialised on first use; commits are scoped to the workspace directory
so the platform's own repo is never touched.

Failures are logged and ignored - Git is a *nice-to-have*, never a
blocker for completing a job.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import GitSettings
from .logging_setup import get_logger

log = get_logger(__name__)


class GitRecorder:
    def __init__(self, settings: GitSettings) -> None:
        self.s = settings
        self._repo: Optional[object] = None
        self._workspace: Optional[Path] = None

    def attach(self, workspace: Path) -> None:
        if not self.s.enabled:
            return
        try:
            from git import Repo  # type: ignore
            from git.exc import InvalidGitRepositoryError  # type: ignore
        except ImportError:
            log.warning("git.unavailable: GitPython not installed")
            return

        self._workspace = workspace
        try:
            self._repo = Repo(workspace)
        except InvalidGitRepositoryError:
            self._repo = Repo.init(workspace)
            with self._repo.config_writer() as cw:
                cw.set_value("user", "name", self.s.commit_author_name)
                cw.set_value("user", "email", self.s.commit_author_email)
            log.info("git.initialised", extra={"workspace": str(workspace)})

    def commit_phase(self, phase: str, cycle: int, message_extra: str = "") -> None:
        if not self.s.enabled or self._repo is None or self._workspace is None:
            return
        try:
            self._repo.git.add(A=True)
            if not self._repo.is_dirty(untracked_files=True):
                return
            msg = f"[{phase}] cycle {cycle}"
            if message_extra:
                msg += f" - {message_extra}"
            self._repo.index.commit(
                msg,
                author=self._mk_actor(),
                committer=self._mk_actor(),
            )
            log.info("git.commit", extra={"phase": phase, "cycle": cycle})
        except Exception as exc:  # noqa: BLE001 - never fatal
            log.warning("git.commit_failed", extra={"phase": phase, "error": str(exc)})

    def _mk_actor(self):
        from git import Actor  # type: ignore
        return Actor(self.s.commit_author_name, self.s.commit_author_email)


__all__ = ["GitRecorder"]
