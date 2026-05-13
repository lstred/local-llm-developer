"""Planner agent - decomposes the task into milestones."""

from __future__ import annotations

from typing import Any

from ..memory import ProjectMemory
from ..models import ModelManager
from .base import Agent, AgentResult


class PlannerAgent(Agent):
    role = "planner"

    async def run(self, memory: ProjectMemory, manager: ModelManager,
                  *, cycle: int = 1,
                  context: dict[str, Any] | None = None) -> AgentResult:
        task = memory.read_text("TASK.md")
        prior_plan = memory.read_text("PLAN.md") if cycle > 1 else ""

        prompt = (
            "You are running the **plan** phase.\n\n"
            "## TASK.md\n\n"
            f"{task}\n"
        )
        if prior_plan.strip() and prior_plan.strip() != "# Plan":
            prompt += (
                "\n## Existing PLAN.md (revise / improve it)\n\n"
                f"{prior_plan}\n"
            )
        prompt += (
            "\nProduce the PLAN.md document per your role specification. "
            "Do NOT include any preamble, conversational text, or markdown "
            "fences around the document - emit the document body directly."
        )

        text = await self._generate(manager, prompt=prompt)
        plan_md = text.strip() + "\n"
        plan_ref = memory.write_text("PLAN.md", plan_md)

        # Hand-off doc summarises plan deltas + open questions for the Architect.
        handoff = (
            "# Plan -> Architect Handoff\n\n"
            f"Plan cycle: {cycle}\n\n"
            "## Pointer\n"
            "Read `PLAN.md` for the authoritative plan.\n\n"
            "## Architect's job\n"
            "1. Resolve every [BLOCKING] open question.\n"
            "2. Translate each milestone into one or more components / "
            "modules with explicit contracts.\n"
            "3. Produce `ARCHITECTURE.md` per the architect role spec.\n"
        )
        ho_ref = memory.write_handoff("plan_to_architect.md", handoff)

        return AgentResult(
            role=self.role,
            success=bool(plan_md.strip()),
            written_artifacts=[plan_ref.relpath, ho_ref.relpath],
            raw_output=text,
        )
