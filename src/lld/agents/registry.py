"""Agent registry - maps role name -> Agent subclass."""

from __future__ import annotations

from ..config import ModelsConfig
from ..prompts import PromptLibrary
from .architect import ArchitectAgent
from .base import Agent
from .file_writing import (
    DocumentationAgent,
    ImplementationAgent,
    RefactorAgent,
    TestAgent,
)
from .planner import PlannerAgent
from .review_agents import FinalAuditorAgent, ReviewAgent, SecurityAgent

_REGISTRY: dict[str, type[Agent]] = {
    "planner": PlannerAgent,
    "architect": ArchitectAgent,
    "implementation": ImplementationAgent,
    "test": TestAgent,
    "review": ReviewAgent,
    "security": SecurityAgent,
    "refactor": RefactorAgent,
    "documentation": DocumentationAgent,
    "final_auditor": FinalAuditorAgent,
}


def build_agent(role: str, models_config: ModelsConfig,
                prompts: PromptLibrary) -> Agent:
    if role not in _REGISTRY:
        raise KeyError(f"Unknown agent role: {role}")
    return _REGISTRY[role](models_config, prompts)


def known_roles() -> list[str]:
    return list(_REGISTRY)


__all__ = ["build_agent", "known_roles"]
