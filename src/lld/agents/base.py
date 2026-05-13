"""Base classes for the nine specialist agents.

Every agent follows the same lifecycle:

    1. ``gather_inputs(memory)``  - read prior artifacts.
    2. ``build_user_prompt(...)`` - produce the user-side prompt.
    3. ``run(memory, manager)``   - call the model and write outputs.

The orchestrator never instantiates raw agent classes directly; it goes
through :func:`lld.agents.registry.build_agent`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from ..config import ModelsConfig
from ..memory import ProjectMemory
from ..models import ModelManager
from ..prompts import PromptLibrary


@dataclass
class AgentResult:
    role: str
    success: bool
    written_artifacts: list[str] = field(default_factory=list)
    raw_output: str = ""
    notes: str = ""
    score: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Agent(abc.ABC):
    role: str = "base"

    def __init__(self, models_config: ModelsConfig,
                 prompts: PromptLibrary) -> None:
        self.models_config = models_config
        self.prompts = prompts

    # -- Hooks ----------------------------------------------------------- #

    @abc.abstractmethod
    async def run(self, memory: ProjectMemory,
                  manager: ModelManager,
                  *, cycle: int = 1,
                  context: dict[str, Any] | None = None) -> AgentResult: ...

    # -- Helpers --------------------------------------------------------- #

    def system_prompt(self) -> str:
        return self.prompts.system_prompt_for(self.role)

    async def _generate(self, manager: ModelManager, *, prompt: str) -> str:
        params = self.models_config.for_role(self.role)
        result = await manager.generate(
            role=self.role,
            system=self.system_prompt(),
            prompt=prompt,
            params=params,
        )
        return result.text

    @staticmethod
    def _section(title: str, body: str) -> str:
        body = body.strip("\n")
        return f"\n## {title}\n\n{body}\n" if body else ""


__all__ = ["Agent", "AgentResult"]
