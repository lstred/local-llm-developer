"""FastAPI server: REST + websocket UI feed."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .app import AppContext, build_app_context
from .logging_setup import get_logger
from .orchestrator import JobSpec

log = get_logger(__name__)

_ctx: AppContext | None = None
_SAFE_NAME_RX = re.compile(r"[^A-Za-z0-9._\-]+")


# --------------------------------------------------------------------------- #
#  Lifespan
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _ctx
    _ctx = await build_app_context()
    try:
        yield
    finally:
        if _ctx is not None:
            await _ctx.close()


def _ctx_dep() -> AppContext:
    if _ctx is None:
        raise HTTPException(503, "App context not initialised")
    return _ctx


# --------------------------------------------------------------------------- #
#  Schemas
# --------------------------------------------------------------------------- #


class CreateJobRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=20_000)
    workspace_name: str | None = None
    workflow: str = "full_pipeline"


class CreateJobResponse(BaseModel):
    job_id: str
    workspace: str


# --------------------------------------------------------------------------- #
#  App + routes
# --------------------------------------------------------------------------- #


def create_app() -> FastAPI:
    app = FastAPI(
        title="local-llm-developer",
        version="0.1.0",
        lifespan=_lifespan,
    )

    here = Path(__file__).parent
    static_dir = here / "ui" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        index_html = here / "ui" / "templates" / "index.html"
        return index_html.read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        ctx = _ctx_dep()
        return {
            "ok": True,
            "provider": ctx.config.models.provider,
            "provider_healthy": await ctx.manager.health(),
            "current_model": ctx.manager.current_model,
        }

    @app.get("/api/config")
    async def get_config() -> dict[str, Any]:
        ctx = _ctx_dep()
        return {
            "provider": ctx.config.models.provider,
            "roles": {
                role: cfg.model_dump()
                for role, cfg in ctx.config.models.roles.items()
            },
            "workflow": ctx.config.workflow.model_dump(),
            "anti_lazy": ctx.config.settings.verification.anti_lazy.model_dump(),
        }

    @app.get("/api/jobs")
    async def list_jobs() -> list[dict[str, Any]]:
        ctx = _ctx_dep()
        jobs = await ctx.store.list_jobs(limit=100)
        return [
            {
                "job_id": j.id,
                "workspace": j.workspace,
                "task": j.task[:200],
                "status": j.status,
                "verdict": j.final_verdict,
                "score": j.final_score,
                "created_at": j.created_at.isoformat(),
                "updated_at": j.updated_at.isoformat(),
            }
            for j in jobs
        ]

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        ctx = _ctx_dep()
        job = await ctx.store.get_job(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        events = await ctx.store.list_events(job_id, limit=2000)
        return {
            "job": {
                "job_id": job.id,
                "workspace": job.workspace,
                "task": job.task,
                "status": job.status,
                "verdict": job.final_verdict,
                "score": job.final_score,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
            },
            "phases": [
                {
                    "phase": p.phase,
                    "agent": p.agent,
                    "cycle": p.cycle,
                    "status": p.status,
                    "score": p.score,
                    "started_at": p.started_at.isoformat() if p.started_at else None,
                    "finished_at": p.finished_at.isoformat() if p.finished_at else None,
                    "notes": p.notes,
                    "artifacts": p.artifacts,
                }
                for p in job.phases
            ],
            "events": [
                {"ts": e.ts.isoformat(), "kind": e.kind, "payload": e.payload}
                for e in events
            ],
        }

    @app.get("/api/jobs/{job_id}/artifact")
    async def get_artifact(job_id: str, path: str) -> dict[str, Any]:
        ctx = _ctx_dep()
        job = await ctx.store.get_job(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        # Sandbox: resolve under workspace.
        ws = Path(job.workspace).resolve()
        target = (ws / path).resolve()
        try:
            target.relative_to(ws)
        except ValueError as exc:
            raise HTTPException(400, "Path escapes workspace") from exc
        if not target.exists() or not target.is_file():
            raise HTTPException(404, "Artifact not found")
        return {
            "path": path,
            "content": target.read_text(encoding="utf-8", errors="replace"),
        }

    @app.post("/api/jobs", response_model=CreateJobResponse)
    async def create_job(req: CreateJobRequest) -> CreateJobResponse:
        ctx = _ctx_dep()
        job_id = ctx.engine.make_job_id()
        name = req.workspace_name or f"job-{job_id}"
        name = _SAFE_NAME_RX.sub("-", name).strip("-") or f"job-{job_id}"
        workspace = (ctx.config.settings.storage.projects_root / name).resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        spec = JobSpec(
            job_id=job_id,
            workspace=workspace,
            task=req.task,
            workflow_name=req.workflow,
        )
        # Fire-and-forget; UI tracks progress via /api/jobs/{id} and websocket.
        asyncio.create_task(_run_safely(ctx, spec))
        return CreateJobResponse(job_id=job_id, workspace=str(workspace))

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> JSONResponse:
        ctx = _ctx_dep()
        ctx.engine.cancel(job_id)
        return JSONResponse({"ok": True, "job_id": job_id})

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        ctx = _ctx_dep()
        await ws.accept()
        q = ctx.broadcaster.subscribe()
        try:
            while True:
                event = await q.get()
                await ws.send_text(json.dumps(event, default=str))
        except WebSocketDisconnect:
            pass
        finally:
            ctx.broadcaster.unsubscribe(q)

    return app


async def _run_safely(ctx: AppContext, spec: JobSpec) -> None:
    try:
        await ctx.engine.run_job(spec)
    except Exception:  # noqa: BLE001
        log.exception("job.unhandled_error", extra={"job_id": spec.job_id})


__all__ = ["create_app"]
