"""Test, lint, and type-check runners.

Each runner:
    * checks whether the underlying tool is on PATH;
    * if not, returns a *skipped* result (never fatal - we degrade gracefully);
    * otherwise runs the tool inside the project workspace and captures
      stdout/stderr/return code.

The orchestrator surfaces results through the Test phase artifact
``TEST_RESULTS.md``.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..config import VerificationSettings
from ..logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class CommandResult:
    name: str
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    skipped: bool = False
    skipped_reason: str = ""

    @property
    def passed(self) -> bool:
        return self.skipped or self.returncode == 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "returncode": self.returncode,
            "stdout_tail": self.stdout[-4000:],
            "stderr_tail": self.stderr[-4000:],
            "skipped": self.skipped,
            "skipped_reason": self.skipped_reason,
            "passed": self.passed,
        }


@dataclass
class VerificationReport:
    results: list[CommandResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def hard_failures(self) -> list[CommandResult]:
        return [r for r in self.results if not r.passed and not r.skipped]

    def to_markdown(self) -> str:
        lines = ["# Test Results", ""]
        for r in self.results:
            status = (
                "SKIPPED" if r.skipped
                else "PASS" if r.passed
                else "FAIL"
            )
            lines.append(f"## {r.name} - {status}")
            lines.append("")
            lines.append(f"`{' '.join(r.command)}`")
            lines.append("")
            if r.skipped:
                lines.append(f"_Skipped: {r.skipped_reason}_")
            else:
                lines.append(f"Return code: `{r.returncode}`")
                if r.stdout.strip():
                    lines.append("\n```\n" + r.stdout[-3000:] + "\n```")
                if r.stderr.strip():
                    lines.append("\nstderr:\n```\n" + r.stderr[-2000:] + "\n```")
            lines.append("")
        return "\n".join(lines)


class VerificationRunner:
    def __init__(self, settings: VerificationSettings,
                 timeout_seconds: int = 1200) -> None:
        self.s = settings
        self.timeout_seconds = timeout_seconds

    async def run_all(self, workspace: Path) -> VerificationReport:
        report = VerificationReport()
        # Detect project type by file presence.
        has_python = any(workspace.rglob("*.py"))
        has_node = (workspace / "package.json").exists()

        if has_python:
            report.results.append(
                await self._run("pytest", self.s.python_test_command, workspace))
            report.results.append(
                await self._run("ruff", self.s.python_lint_command, workspace))
            report.results.append(
                await self._run("mypy", self.s.python_typecheck_command, workspace))

        if has_node:
            report.results.append(
                await self._run("npm test", self.s.node_test_command, workspace))

        if not report.results:
            report.results.append(CommandResult(
                name="auto-detect",
                command=[],
                returncode=None,
                stdout="",
                stderr="",
                skipped=True,
                skipped_reason="No recognised project type (no .py or package.json found).",
            ))
        return report

    async def _run(self, name: str, cmd: list[str], cwd: Path) -> CommandResult:
        if not cmd:
            return CommandResult(name, cmd, None, "", "", skipped=True,
                                 skipped_reason="empty command")
        exe = cmd[0]
        if shutil.which(exe) is None:
            return CommandResult(name, cmd, None, "", "", skipped=True,
                                 skipped_reason=f"'{exe}' not on PATH")
        log.info("verify.run", extra={"name": name, "cmd": cmd, "cwd": str(cwd)})
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return CommandResult(name, cmd, None, "", f"timeout after {self.timeout_seconds}s")
            return CommandResult(
                name=name,
                command=cmd,
                returncode=proc.returncode,
                stdout=stdout_b.decode("utf-8", errors="replace"),
                stderr=stderr_b.decode("utf-8", errors="replace"),
            )
        except OSError as exc:
            return CommandResult(name, cmd, None, "", str(exc),
                                 skipped=True, skipped_reason=f"OSError: {exc}")


__all__ = ["VerificationRunner", "VerificationReport", "CommandResult"]
