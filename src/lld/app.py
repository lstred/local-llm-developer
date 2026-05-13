"""Application bootstrap.

Builds the heavy singletons (config, store, model manager, engine,
broadcaster) once and exposes them through a single :class:`AppContext`
that the API layer holds for the lifetime of the process.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .logging_setup import configure_logging, get_logger
from .models import ModelManager, build_provider
from .orchestrator import Engine
from .persistence import StateStore
from .prompts import PromptLibrary

log = get_logger(__name__)


class EventBroadcaster:
    """Fan-out of orchestrator events to attached websocket consumers."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def publish(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop event for this slow consumer rather than blocking the engine.
                pass


@dataclass
class AppContext:
    config: AppConfig
    store: StateStore
    manager: ModelManager
    engine: Engine
    broadcaster: EventBroadcaster
    missing_models: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.missing_models is None:
            self.missing_models = {}

    async def refresh_missing_models(self) -> dict[str, str]:
        """Re-probe the provider and update ``missing_models`` in place."""
        result: dict[str, str] = {}
        try:
            available = set(await self.manager.provider.list_available())
        except Exception:  # noqa: BLE001 - probe must never raise
            available = set()
        if available:
            for role, role_cfg in self.config.models.roles.items():
                if not _model_present(role_cfg.model, available):
                    result[role] = role_cfg.model
        self.missing_models = result
        return result

    async def close(self) -> None:
        await self.manager.close()
        await self.store.close()


async def build_app_context(config_dir: Path | str = "config") -> AppContext:
    config = AppConfig.load(config_dir)

    # Filesystem
    config.settings.storage.state_dir.mkdir(parents=True, exist_ok=True)
    config.settings.logging.log_file.parent.mkdir(parents=True, exist_ok=True)
    config.settings.storage.projects_root.mkdir(parents=True, exist_ok=True)

    configure_logging(
        level=config.settings.logging.level,
        log_file=config.settings.logging.log_file,
        json_console=config.settings.logging.json,
    )

    # State store
    store = StateStore(config.settings.storage.database_url)
    await store.init()

    # Model provider + manager
    provider = build_provider(
        config.models.provider,
        ollama_host=config.models.ollama_host,
        llamacpp_models_dir=config.models.llamacpp_models_dir,
        retries=config.settings.execution.llm_call_retries,
        initial_backoff=config.settings.execution.llm_call_initial_backoff_seconds,
        request_timeout_seconds=config.settings.execution.per_phase_timeout_seconds,
    )
    manager = ModelManager(provider)

    # Verify configured per-role models are actually available locally.
    # We don't fail startup - the user may pull missing models at runtime -
    # but we log and stash the report so the API can surface it.
    missing_models: dict[str, str] = {}
    try:
        available = set(await provider.list_available())
        if available:  # only meaningful when we got a real listing
            for role, role_cfg in config.models.roles.items():
                if not _model_present(role_cfg.model, available):
                    missing_models[role] = role_cfg.model
        else:
            log.warning("models.availability_unknown",
                        extra={"reason": "provider returned empty listing"})
    except Exception as exc:  # noqa: BLE001 - best-effort probe
        log.warning("models.availability_check_failed",
                    extra={"error": str(exc)})

    if missing_models:
        log.warning("models.missing",
                    extra={"missing": missing_models,
                           "hint": "Run `ollama pull <model>` for each."})

    # Broadcaster + engine
    broadcaster = EventBroadcaster()
    engine = Engine(config=config, manager=manager,
                    store=store, prompts=PromptLibrary())
    engine.add_listener(broadcaster.publish)

    log.info("app.context_ready",
             extra={"provider": config.models.provider,
                    "workspace_root": str(config.settings.storage.projects_root),
                    "missing_models": missing_models})

    ctx = AppContext(config=config, store=store, manager=manager,
                     engine=engine, broadcaster=broadcaster,
                     missing_models=missing_models)
    return ctx


def _model_present(wanted: str, available: set[str]) -> bool:
    """Match Ollama's flexible naming: ``llama3.1`` matches ``llama3.1:latest``."""
    if wanted in available:
        return True
    if ":" not in wanted and f"{wanted}:latest" in available:
        return True
    # Fallback: bare-name match (strip tag on either side).
    bare = wanted.split(":", 1)[0]
    return any(a.split(":", 1)[0] == bare for a in available)


__all__ = ["AppContext", "EventBroadcaster", "build_app_context"]
