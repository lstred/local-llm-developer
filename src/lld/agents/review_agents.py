"""Review, Security, and Final-Auditor agents."""

from __future__ import annotations

from typing import Any

from ..memory import ProjectMemory
from ..models import ModelManager
from .base import Agent, AgentResult
from .parsing import extract_score, extract_verdict


class ReviewAgent(Agent):
    role = "review"

    async def run(self, memory: ProjectMemory, manager: ModelManager,
                  *, cycle: int = 1,
                  context: dict[str, Any] | None = None) -> AgentResult:
        prompt = (
            f"You are running the **review** phase (cycle {cycle}).\n\n"
            "## ARCHITECTURE.md\n\n" + memory.read_text("ARCHITECTURE.md") + "\n\n"
            "## TEST_RESULTS.md\n\n" + memory.read_text("TEST_RESULTS.md") + "\n\n"
            "## Source tree\n"
        )
        for rel, body in memory.collect_source_tree(
                max_files=120, max_bytes_per_file=16_000).items():
            prompt += f"\n### FILE: {rel}\n```\n{body}\n```\n"

        prior = memory.read_text("REVIEW.md")
        if cycle > 1 and prior.strip() and prior.strip() != "# Review":
            prompt += "\n## Prior REVIEW.md\n\n" + prior + "\n"

        prompt += (
            "\nProduce the REVIEW.md document per your role spec. "
            "Include `## Score: <n>`."
        )

        text = await self._generate(manager, prompt=prompt)
        review_md = text.strip() + "\n"
        ref = memory.write_text("REVIEW.md", review_md)
        score = extract_score(review_md)

        handoff = (
            "# Review -> Refactor Handoff\n\n"
            f"Review cycle: {cycle}\n"
            f"Score: {score if score is not None else 'unparsed'}\n\n"
            "Refactor agent must address every blocker / major finding "
            "in `REVIEW.md`. Justify any deferred minor / nit items in "
            "the CHANGE_LOG."
        )
        ho = memory.write_handoff("review_to_refactor.md", handoff)

        return AgentResult(
            role=self.role,
            success=score is not None,
            written_artifacts=[ref.relpath, ho.relpath],
            raw_output=text,
            score=score,
        )


class SecurityAgent(Agent):
    role = "security"

    async def run(self, memory, manager, *, cycle=1, context=None):
        prompt = (
            f"You are running the **security** phase (cycle {cycle}).\n\n"
            "## ARCHITECTURE.md\n\n" + memory.read_text("ARCHITECTURE.md") + "\n\n"
            "## Source tree\n"
        )
        for rel, body in memory.collect_source_tree(
                max_files=120, max_bytes_per_file=16_000).items():
            prompt += f"\n### FILE: {rel}\n```\n{body}\n```\n"
        prompt += "\nProduce the SECURITY.md document per your role spec. Include `## Score: <n>`."

        text = await self._generate(manager, prompt=prompt)
        sec_md = text.strip() + "\n"
        ref = memory.write_text("SECURITY.md", sec_md)
        score = extract_score(sec_md)

        handoff = (
            "# Security -> Refactor Handoff\n\n"
            f"Security cycle: {cycle}\n"
            f"Score: {score if score is not None else 'unparsed'}\n\n"
            "Refactor agent must address every critical/high finding."
        )
        ho = memory.write_handoff("security_to_refactor.md", handoff)

        return AgentResult(
            role=self.role,
            success=score is not None,
            written_artifacts=[ref.relpath, ho.relpath],
            raw_output=text,
            score=score,
        )


class FinalAuditorAgent(Agent):
    role = "final_auditor"

    async def run(self, memory, manager, *, cycle=1, context=None):
        prompt = (
            f"You are running the **final audit** phase (cycle {cycle}).\n\n"
            "## TASK.md\n\n" + memory.read_text("TASK.md") + "\n\n"
            "## PLAN.md\n\n" + memory.read_text("PLAN.md") + "\n\n"
            "## ARCHITECTURE.md\n\n" + memory.read_text("ARCHITECTURE.md") + "\n\n"
            "## REVIEW.md\n\n" + memory.read_text("REVIEW.md") + "\n\n"
            "## SECURITY.md\n\n" + memory.read_text("SECURITY.md") + "\n\n"
            "## TEST_RESULTS.md\n\n" + memory.read_text("TEST_RESULTS.md") + "\n\n"
            "## README.md\n\n" + memory.read_text("README.md") + "\n\n"
            "## Source tree\n"
        )
        for rel, body in memory.collect_source_tree(
                max_files=150, max_bytes_per_file=12_000).items():
            prompt += f"\n### FILE: {rel}\n```\n{body}\n```\n"

        prompt += (
            "\nProduce AUDIT.md per your role spec. Include "
            "`## Verdict: APPROVED|BLOCKED` and `## Score: <n>`."
        )

        text = await self._generate(manager, prompt=prompt)
        audit_md = text.strip() + "\n"
        ref = memory.write_text("AUDIT.md", audit_md)

        score = extract_score(audit_md)
        verdict = extract_verdict(audit_md)

        return AgentResult(
            role=self.role,
            success=score is not None and verdict is not None,
            written_artifacts=[ref.relpath],
            raw_output=text,
            score=score,
            extra={"verdict": verdict or "UNKNOWN"},
        )


__all__ = ["ReviewAgent", "SecurityAgent", "FinalAuditorAgent"]
