"""Typed configuration loaders for the platform.

Configuration lives in three YAML files inside ``config/``:

* ``settings.yaml``  - server, storage, logging, verification toggles
* ``models.yaml``    - per-role model assignments & generation params
* ``workflow.yaml``  - phase ordering, gates, repair-loop bounds

All three are loaded into pydantic models so the rest of the codebase
can rely on validated, autocompleting structures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
#  settings.yaml
# --------------------------------------------------------------------------- #


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    reload: bool = False


class StorageSettings(BaseModel):
    state_dir: Path = Path("./state")
    database_url: str = "sqlite+aiosqlite:///./state/orchestrator.db"
    projects_root: Path = Path("./projects")


class LoggingSettings(BaseModel):
    level: str = "INFO"
    json: bool = False
    log_file: Path = Path("./state/logs/orchestrator.log")


class GitSettings(BaseModel):
    enabled: bool = True
    auto_commit_per_phase: bool = True
    commit_author_name: str = "local-llm-developer"
    commit_author_email: str = "bot@local-llm-developer.local"
    branch_prefix: str = "lld/"


class AntiLazySettings(BaseModel):
    forbid_todo_comments: bool = True
    forbid_pass_only_bodies: bool = True
    forbid_notimplemented: bool = True
    forbid_placeholder_strings: bool = True
    forbid_empty_test_bodies: bool = True
    forbid_mock_unless_requested: bool = True


class VerificationSettings(BaseModel):
    python_test_command: list[str] = Field(
        default_factory=lambda: ["pytest", "-x", "--tb=short", "-q"]
    )
    python_lint_command: list[str] = Field(default_factory=lambda: ["ruff", "check", "."])
    python_typecheck_command: list[str] = Field(
        default_factory=lambda: ["mypy", "--ignore-missing-imports", "."]
    )
    node_test_command: list[str] = Field(default_factory=lambda: ["npm", "test", "--silent"])
    anti_lazy: AntiLazySettings = Field(default_factory=AntiLazySettings)


class ExecutionSettings(BaseModel):
    per_phase_timeout_seconds: int = 3600
    llm_call_retries: int = 3
    llm_call_initial_backoff_seconds: int = 2


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    git: GitSettings = Field(default_factory=GitSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)


# --------------------------------------------------------------------------- #
#  models.yaml
# --------------------------------------------------------------------------- #


class GenerationDefaults(BaseModel):
    temperature: float = 0.2
    top_p: float = 0.9
    num_ctx: int = 8192
    num_predict: int = 4096
    repeat_penalty: float = 1.05
    seed: int = 0
    keep_alive: int = 0


class RoleModelConfig(BaseModel):
    model: str
    temperature: float | None = None
    top_p: float | None = None
    num_ctx: int | None = None
    num_predict: int | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    keep_alive: int | None = None
    system_style: str = "implementation"

    def merged(self, defaults: GenerationDefaults) -> dict[str, Any]:
        """Return a dict of generation params with role overrides applied."""
        base = defaults.model_dump()
        for k, v in self.model_dump(exclude={"model", "system_style"}).items():
            if v is not None:
                base[k] = v
        base["model"] = self.model
        return base


class ModelsConfig(BaseModel):
    provider: str = "ollama"
    ollama_host: str = "http://127.0.0.1:11434"
    llamacpp_models_dir: Path = Path("./models")
    defaults: GenerationDefaults = Field(default_factory=GenerationDefaults)
    roles: dict[str, RoleModelConfig]

    def for_role(self, role: str) -> dict[str, Any]:
        if role not in self.roles:
            raise KeyError(f"No model configured for role '{role}'")
        return self.roles[role].merged(self.defaults)

    def system_style_for(self, role: str) -> str:
        return self.roles[role].system_style if role in self.roles else "implementation"


# --------------------------------------------------------------------------- #
#  workflow.yaml
# --------------------------------------------------------------------------- #


class RepairLoop(BaseModel):
    on_failure: str | None = None     # phase id to loop back to on hard failure
    on_low_score: str | None = None   # phase id to loop back to on score gate fail
    max_cycles: int = 3


class PhaseConfig(BaseModel):
    id: str
    agent: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    gates: list[str] = Field(default_factory=list)
    repair_loop: RepairLoop | None = None


class QualityConfig(BaseModel):
    min_review_score: int = 7
    min_audit_score: int = 8
    max_review_cycles: int = 3
    max_test_repair_cycles: int = 4
    fail_on_anti_lazy: bool = True


class WorkflowConfig(BaseModel):
    name: str
    description: str = ""
    quality: QualityConfig = Field(default_factory=QualityConfig)
    phases: list[PhaseConfig]


# --------------------------------------------------------------------------- #
#  Loader
# --------------------------------------------------------------------------- #


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file missing: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} did not parse to a mapping")
    return data


class AppConfig(BaseModel):
    settings: Settings
    models: ModelsConfig
    workflow: WorkflowConfig

    @classmethod
    def load(cls, config_dir: Path | str = "config") -> AppConfig:
        cdir = Path(config_dir)
        return cls(
            settings=Settings.model_validate(_read_yaml(cdir / "settings.yaml")),
            models=ModelsConfig.model_validate(_read_yaml(cdir / "models.yaml")),
            workflow=WorkflowConfig.model_validate(_read_yaml(cdir / "workflow.yaml")),
        )


__all__ = [
    "AppConfig",
    "Settings",
    "ModelsConfig",
    "WorkflowConfig",
    "PhaseConfig",
    "RoleModelConfig",
    "GenerationDefaults",
    "QualityConfig",
    "RepairLoop",
]
