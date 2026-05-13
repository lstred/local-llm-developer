"""Architect agent - designs system architecture & contracts."""

from __future__ import annotations

from typing import Any

from ..memory import ProjectMemory
from ..models import ModelManager
from .base import Agent, AgentResult


class ArchitectAgent(Agent):
    role = "architect"

    async def run(self, memory: ProjectMemory, manager: ModelManager,
                  *, cycle: int = 1,
                  context: dict[str, Any] | None = None) -> AgentResult:
        task = memory.read_text("TASK.md")
        plan = memory.read_text("PLAN.md")
        plan_handoff = memory.read_text("handoffs/plan_to_architect.md")
        prior = memory.read_text("ARCHITECTURE.md") if cycle > 1 else ""

        prompt = (
            "You are running the **architect** phase.\n\n"
            "## TASK.md\n\n"
            f"{task}\n\n"
            "## PLAN.md\n\n"
            f"{plan}\n\n"
            "## handoffs/plan_to_architect.md\n\n"
            f"{plan_handoff}\n"
        )
        if prior.strip() and prior.strip() != "# Architecture":
            prompt += (
                "\n## Existing ARCHITECTURE.md (revise / improve it)\n\n"
                f"{prior}\n"
            )
        prompt += (
            "\nProduce the ARCHITECTURE.md document per your role "
            "specification. Emit the document body directly with no "
            "surrounding fences or preamble."
        )

        text = await self._generate(manager, prompt=prompt)
        arch_md = text.strip() + "\n"
        arch_ref = memory.write_text("ARCHITECTURE.md", arch_md)

        handoff = (
            "# Architect -> Implementation Handoff\n\n"
            f"Architecture cycle: {cycle}\n\n"
            "## Pointer\n"
            "Authoritative design lives in `ARCHITECTURE.md`. Public "
            "contracts in section 4 are normative - match signatures "
            "exactly.\n\n"
            "## Implementation focus\n"
            "1. Create every file listed in `Module Layout`.\n"
            "2. Implement every contract in `Public Contracts` exactly.\n"
            "3. Honour the error model and concurrency model.\n"
            "4. No placeholders; no stubs; no TODOs.\n"
        )
        ho_ref = memory.write_handoff("architect_to_impl.md", handoff)

        return AgentResult(
            role=self.role,
            success=bool(arch_md.strip()),
            written_artifacts=[arch_ref.relpath, ho_ref.relpath],
            raw_output=text,
        )
