"""Sequential phase executor with quality gates and repair loops.

The :class:`Engine` is the heart of the platform. It walks the workflow
defined in ``workflow.yaml`` one phase at a time. For each phase it:

    1. Loads the appropriate agent.
    2. Runs the agent through the :class:`ModelManager` (which keeps
       only one model in VRAM at a time).
    3. Runs anti-lazy and verification gates on the produced artifacts.
    4. Decides whether to advance, retry, or loop back to a prior phase.
    5. Persists state to the SQLite store.
    6. Optionally commits to Git.
    7. Pushes structured events to a websocket broadcaster (UI live view).

Cancellation: each phase respects ``settings.execution.per_phase_timeout``.
Resumability: state is persisted after every phase, so a job can be
resumed by replaying from the last completed phase.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .agents import AgentResult, build_agent
from .agents.parsing import extract_score, extract_verdict
from .config import AppConfig, PhaseConfig
from .git_integration import GitRecorder
from .logging_setup import get_logger
from .memory import ProjectMemory
from .models import ModelManager
from .persistence import StateStore
from .prompts import PromptLibrary
from .verification import AntiLazyDetector, VerificationRunner

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Public types
# --------------------------------------------------------------------------- #


@dataclass
class JobSpec:
    job_id: str
    workspace: Path
    task: str
    workflow_name: str = "full_pipeline"


@dataclass
class JobOutcome:
    job_id: str
    status: str                       # "completed" | "blocked" | "failed"
    final_verdict: str | None = None
    final_score: int | None = None
    phase_history: list[dict[str, Any]] = field(default_factory=list)


EventListener = Callable[[dict[str, Any]], Awaitable[None]]


# --------------------------------------------------------------------------- #
#  Engine
# --------------------------------------------------------------------------- #


class Engine:
    def __init__(
        self,
        config: AppConfig,
        manager: ModelManager,
        store: StateStore,
        prompts: PromptLibrary | None = None,
    ) -> None:
        self.config = config
        self.manager = manager
        self.store = store
        self.prompts = prompts or PromptLibrary()
        self._listeners: list[EventListener] = []
        self._cancelled: set[str] = set()

    # -- Public API ------------------------------------------------------- #

    def add_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: EventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def cancel(self, job_id: str) -> None:
        self._cancelled.add(job_id)

    @staticmethod
    def make_job_id() -> str:
        return uuid.uuid4().hex[:12]

    async def run_job(self, spec: JobSpec) -> JobOutcome:
        memory = ProjectMemory(spec.workspace)
        memory.ensure_layout()
        if not memory.read_text("TASK.md").strip().replace("# Task", "").strip():
            memory.write_text("TASK.md", f"# Task\n\n{spec.task}\n", archive=False)

        await self.store.create_job(
            job_id=spec.job_id,
            workspace=str(spec.workspace),
            task=spec.task,
            workflow=spec.workflow_name,
        )
        await self._emit({"event": "job.start", "job_id": spec.job_id,
                          "workspace": str(spec.workspace)})

        git = GitRecorder(self.config.settings.git)
        git.attach(spec.workspace)
        git.commit_phase("init", 0, "TASK.md")

        outcome = JobOutcome(job_id=spec.job_id, status="running")

        wf = self.config.workflow
        phases = wf.phases
        i = 0
        review_loop_count = 0
        test_repair_count = 0

        while i < len(phases):
            if spec.job_id in self._cancelled:
                outcome.status = "cancelled"
                break

            phase = phases[i]
            cycle = self._cycle_for_phase(phase.id, outcome.phase_history)

            try:
                result = await self._run_phase(spec, memory, phase, cycle)
            except Exception as exc:  # noqa: BLE001 - capture all
                log.exception("phase.crashed", extra={"phase": phase.id})
                await self._emit({"event": "phase.crashed", "job_id": spec.job_id,
                                  "phase": phase.id, "error": str(exc)})
                await self.store.update_job_status(spec.job_id, "failed")
                outcome.status = "failed"
                return outcome

            outcome.phase_history.append({
                "phase": phase.id,
                "cycle": cycle,
                "score": result.score,
                "success": result.success,
                "artifacts": result.written_artifacts,
                "extra": result.extra,
            })

            # Per-phase commit
            git.commit_phase(phase.id, cycle,
                             f"score={result.score} ok={result.success}")

            # Gate / repair-loop logic per phase id.
            decision = self._decide_next(
                phase=phase, result=result,
                outcome=outcome,
                review_loop_count=review_loop_count,
                test_repair_count=test_repair_count,
            )

            await self._emit({
                "event": "phase.decision",
                "job_id": spec.job_id,
                "phase": phase.id,
                "decision": decision.kind,
                "to_phase": decision.to_phase,
                "reason": decision.reason,
            })

            if decision.kind == "advance":
                i += 1
            elif decision.kind == "retry":
                # stay on same phase; counters tracked via cycle
                continue
            elif decision.kind == "loop_back":
                # find target index
                target_idx = self._index_of_phase(phases, decision.to_phase)
                if target_idx is None or target_idx >= i:
                    # Misconfiguration - treat as advance to avoid infinite loops
                    log.warning("phase.loop_back_invalid",
                                extra={"phase": phase.id,
                                       "target": decision.to_phase})
                    i += 1
                    continue
                if decision.to_phase in {"implement", "implementation"}:
                    test_repair_count += 1
                if decision.to_phase == "review":
                    review_loop_count += 1
                i = target_idx
            elif decision.kind == "block":
                outcome.status = "blocked"
                outcome.final_verdict = "BLOCKED"
                outcome.final_score = result.score
                await self.store.update_job_status(spec.job_id, "blocked",
                                                   verdict="BLOCKED",
                                                   score=result.score)
                await self._emit({"event": "job.blocked", "job_id": spec.job_id,
                                  "phase": phase.id, "reason": decision.reason})
                return outcome

        # If we ran the audit phase, capture its verdict.
        last_audit = next(
            (h for h in reversed(outcome.phase_history) if h["phase"] == "audit"),
            None,
        )
        if last_audit:
            audit_text = memory.read_text("AUDIT.md")
            outcome.final_verdict = extract_verdict(audit_text)
            outcome.final_score = extract_score(audit_text)

        if outcome.status == "running":
            outcome.status = (
                "completed" if outcome.final_verdict != "BLOCKED" else "blocked"
            )

        await self.store.update_job_status(
            spec.job_id, outcome.status,
            verdict=outcome.final_verdict, score=outcome.final_score,
        )
        await self._emit({"event": "job.end", "job_id": spec.job_id,
                          "status": outcome.status,
                          "verdict": outcome.final_verdict,
                          "score": outcome.final_score})
        return outcome

    # -- Phase execution -------------------------------------------------- #

    async def _run_phase(self, spec: JobSpec, memory: ProjectMemory,
                         phase: PhaseConfig, cycle: int) -> AgentResult:
        log.info("phase.start", extra={"phase": phase.id, "agent": phase.agent,
                                       "cycle": cycle})
        await self._emit({"event": "phase.start", "job_id": spec.job_id,
                          "phase": phase.id, "agent": phase.agent,
                          "cycle": cycle, "model": self.config.models.for_role(
                              phase.agent).get("model")})

        run_id = await self.store.add_phase_run(
            job_id=spec.job_id, phase=phase.id, agent=phase.agent, cycle=cycle)

        agent = build_agent(phase.agent, self.config.models, self.prompts)
        timeout = self.config.settings.execution.per_phase_timeout_seconds

        try:
            result: AgentResult = await asyncio.wait_for(
                agent.run(memory, self.manager, cycle=cycle),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log.error("phase.timeout", extra={"phase": phase.id, "timeout": timeout})
            await self.store.finish_phase_run(run_id, status="timeout",
                                              notes=f"timeout after {timeout}s")
            raise

        # Test phase: actually run the verification suite.
        if phase.id == "test":
            runner = VerificationRunner(self.config.settings.verification,
                                        timeout_seconds=min(timeout, 1200))
            report = await runner.run_all(spec.workspace)
            memory.write_text("TEST_RESULTS.md", report.to_markdown())
            result.extra["verification"] = {
                "all_passed": report.all_passed,
                "results": [r.to_dict() for r in report.results],
            }
            # If hard failures, mark result as not successful so repair loop fires.
            if not report.all_passed and report.hard_failures:
                result.success = False

        # Anti-lazy gate (apply after writing-agent phases).
        if phase.id in {"implement", "test", "refactor"}:
            detector = AntiLazyDetector(
                self.config.settings.verification.anti_lazy)
            findings = detector.scan_workspace(spec.workspace)
            blocking = [f for f in findings if f.severity == "error"]
            result.extra["anti_lazy"] = [f.to_dict() for f in findings]
            if blocking and self.config.workflow.quality.fail_on_anti_lazy:
                result.success = False
                result.notes = (
                    (result.notes + "\n" if result.notes else "")
                    + f"Anti-lazy detector found {len(blocking)} blocking issues."
                )

        await self.store.finish_phase_run(
            run_id,
            status="ok" if result.success else "failed",
            score=result.score,
            notes=result.notes,
            artifacts={"written": result.written_artifacts,
                       "extra": result.extra},
        )
        await self._emit({
            "event": "phase.end",
            "job_id": spec.job_id,
            "phase": phase.id,
            "agent": phase.agent,
            "cycle": cycle,
            "success": result.success,
            "score": result.score,
            "artifacts": result.written_artifacts,
        })
        log.info("phase.end", extra={"phase": phase.id, "success": result.success,
                                     "score": result.score})
        return result

    # -- Decision logic --------------------------------------------------- #

    @dataclass
    class _Decision:
        kind: str           # "advance" | "retry" | "loop_back" | "block"
        to_phase: str | None = None
        reason: str = ""

    def _decide_next(self, *, phase: PhaseConfig, result: AgentResult,
                     outcome: JobOutcome,
                     review_loop_count: int,
                     test_repair_count: int) -> _Decision:
        q = self.config.workflow.quality

        # Test phase: repair loop on hard failures.
        if phase.id == "test":
            verif = result.extra.get("verification", {})
            anti = result.extra.get("anti_lazy", [])
            blocking_anti = [f for f in anti if f.get("severity") == "error"]
            if (not verif.get("all_passed", True) or blocking_anti):
                if test_repair_count < q.max_test_repair_cycles:
                    return self._Decision(
                        kind="loop_back",
                        to_phase="implement",
                        reason="tests failed or anti-lazy violations",
                    )
                return self._Decision(
                    kind="block",
                    reason="exceeded max test-repair cycles",
                )
            return self._Decision(kind="advance")

        # Review phase: low score => loop into refactor.
        if phase.id == "review":
            if result.score is None:
                return self._Decision(kind="advance")  # cannot gate, move on
            if result.score < q.min_review_score:
                return self._Decision(kind="advance",
                                      reason=f"score {result.score} < {q.min_review_score}; "
                                             "refactor will address findings")
            return self._Decision(kind="advance")

        # Refactor phase: re-review unless we've exhausted cycles.
        if phase.id == "refactor":
            if review_loop_count < q.max_review_cycles - 1:
                return self._Decision(kind="loop_back", to_phase="review",
                                      reason="re-review after refactor")
            return self._Decision(kind="advance",
                                  reason="max review cycles reached")

        # Final audit: blocking on score / verdict.
        if phase.id == "audit":
            if (result.score is not None and result.score < q.min_audit_score) or \
               (result.extra.get("verdict") == "BLOCKED"):
                return self._Decision(
                    kind="block",
                    reason=f"audit blocked (score={result.score}, "
                           f"verdict={result.extra.get('verdict')})",
                )
            return self._Decision(kind="advance")

        # Implementation: anti-lazy violations => retry once at this phase.
        if phase.id == "implement":
            anti = result.extra.get("anti_lazy", [])
            blocking_anti = [f for f in anti if f.get("severity") == "error"]
            if blocking_anti:
                # Stay on implement; engine increments cycle automatically.
                if self._cycle_for_phase("implement", outcome.phase_history) < 3:
                    return self._Decision(kind="retry",
                                          reason="anti-lazy violations on first emit")
                return self._Decision(kind="block",
                                      reason="repeated anti-lazy violations")
            return self._Decision(kind="advance")

        # Default: advance.
        return self._Decision(kind="advance")

    # -- Helpers ---------------------------------------------------------- #

    @staticmethod
    def _index_of_phase(phases: list[PhaseConfig], phase_id: str) -> int | None:
        # Allow target to match either the phase id or the agent name (loose).
        for idx, p in enumerate(phases):
            if p.id == phase_id or p.agent == phase_id:
                return idx
        # Some workflow names use "implement" while phase id is "implement"
        # already; this branch handles "implementation" alias.
        if phase_id == "implementation":
            return Engine._index_of_phase(phases, "implement")
        return None

    @staticmethod
    def _cycle_for_phase(phase_id: str,
                         history: list[dict[str, Any]]) -> int:
        return 1 + sum(1 for h in history if h["phase"] == phase_id)

    async def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("ts", datetime.now(timezone.utc).isoformat())
        for listener in list(self._listeners):
            try:
                await listener(event)
            except Exception as exc:  # noqa: BLE001 - listener errors are non-fatal
                log.warning("listener.failed", extra={"error": str(exc)})
        await self.store.log_event(
            kind=event.get("event", "unknown"),
            job_id=event.get("job_id"),
            payload=event,
        )


__all__ = ["Engine", "JobSpec", "JobOutcome"]
