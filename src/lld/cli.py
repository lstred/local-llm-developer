"""Typer CLI entry point: ``local-llm-dev``.

Subcommands:
    serve       Run the FastAPI orchestrator + UI.
    run         Run a single job synchronously, streaming logs to stdout.
    list-jobs   List recent jobs from the state DB.
    show        Show the details of a specific job.
    health      Probe the LLM provider.
    config      Print the resolved configuration.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from .app import build_app_context
from .config import AppConfig
from .orchestrator import JobSpec

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="local-llm-developer - quality-first local AI engineering.")
console = Console()


# --------------------------------------------------------------------------- #
#  serve
# --------------------------------------------------------------------------- #


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, help="Override server host."),
    port: Optional[int] = typer.Option(None, help="Override server port."),
    reload: bool = typer.Option(False, help="Enable autoreload (dev only)."),
) -> None:
    """Run the FastAPI orchestrator + UI."""
    cfg = AppConfig.load()
    h = host or cfg.settings.server.host
    p = port or cfg.settings.server.port
    console.print(f"[bold]Serving on http://{h}:{p}[/bold]")
    uvicorn.run("lld.api:create_app", host=h, port=p, reload=reload, factory=True)


# --------------------------------------------------------------------------- #
#  run
# --------------------------------------------------------------------------- #


@app.command()
def run(
    task: str = typer.Option(..., "--task", "-t", help="Task description."),
    workspace: Path = typer.Option(..., "--workspace", "-w",
                                   help="Project workspace directory."),
    workflow: str = typer.Option("full_pipeline", "--workflow",
                                 help="Workflow name (must match workflow.yaml)."),
) -> None:
    """Run a single job synchronously."""
    asyncio.run(_run(task, workspace, workflow))


async def _run(task: str, workspace: Path, workflow: str) -> None:
    ctx = await build_app_context()
    try:
        async def _print_event(ev: dict) -> None:
            console.log(f"[cyan]{ev.get('event')}[/cyan] {json.dumps({k:v for k,v in ev.items() if k != 'event'}, default=str)}")

        ctx.engine.add_listener(_print_event)
        spec = JobSpec(
            job_id=ctx.engine.make_job_id(),
            workspace=workspace.resolve(),
            task=task,
            workflow_name=workflow,
        )
        outcome = await ctx.engine.run_job(spec)
        console.print(f"\n[bold]Job {outcome.job_id} {outcome.status}[/bold] "
                      f"verdict={outcome.final_verdict} score={outcome.final_score}")
    finally:
        await ctx.close()


# --------------------------------------------------------------------------- #
#  list-jobs
# --------------------------------------------------------------------------- #


@app.command("list-jobs")
def list_jobs(limit: int = typer.Option(20)) -> None:
    """List recent jobs."""
    asyncio.run(_list_jobs(limit))


async def _list_jobs(limit: int) -> None:
    ctx = await build_app_context()
    try:
        jobs = await ctx.store.list_jobs(limit=limit)
        table = Table("id", "status", "verdict", "score", "workspace", "created")
        for j in jobs:
            table.add_row(
                j.id, j.status, j.final_verdict or "-",
                str(j.final_score) if j.final_score is not None else "-",
                j.workspace, j.created_at.isoformat(timespec="seconds"),
            )
        console.print(table)
    finally:
        await ctx.close()


# --------------------------------------------------------------------------- #
#  show
# --------------------------------------------------------------------------- #


@app.command()
def show(job_id: str) -> None:
    """Show details for a job."""
    asyncio.run(_show(job_id))


async def _show(job_id: str) -> None:
    ctx = await build_app_context()
    try:
        job = await ctx.store.get_job(job_id)
        if not job:
            console.print(f"[red]Job not found: {job_id}[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]Job {job.id}[/bold]  status={job.status}  "
                      f"verdict={job.final_verdict}  score={job.final_score}")
        console.print(f"workspace: {job.workspace}")
        console.rule("phases")
        table = Table("phase", "agent", "cycle", "status", "score", "started", "finished")
        for p in job.phases:
            table.add_row(
                p.phase, p.agent, str(p.cycle), p.status,
                str(p.score) if p.score is not None else "-",
                p.started_at.isoformat(timespec="seconds") if p.started_at else "-",
                p.finished_at.isoformat(timespec="seconds") if p.finished_at else "-",
            )
        console.print(table)
    finally:
        await ctx.close()


# --------------------------------------------------------------------------- #
#  health / config
# --------------------------------------------------------------------------- #


@app.command()
def health() -> None:
    """Check LLM provider connectivity."""
    asyncio.run(_health())


async def _health() -> None:
    ctx = await build_app_context()
    try:
        ok = await ctx.manager.health()
        loaded = await ctx.manager.provider.list_loaded()
        console.print({"provider": ctx.config.models.provider, "ok": ok,
                       "loaded_models": loaded})
    finally:
        await ctx.close()


@app.command()
def config() -> None:
    """Print resolved configuration."""
    cfg = AppConfig.load()
    console.print_json(data=cfg.model_dump(mode="json"))


@app.command()
def models() -> None:
    """List configured models and report which are missing locally."""
    asyncio.run(_models())


async def _models() -> None:
    ctx = await build_app_context()
    try:
        available = sorted(await ctx.manager.provider.list_available())
        loaded = await ctx.manager.provider.list_loaded()

        table = Table(title="Configured models")
        table.add_column("Role")
        table.add_column("Model")
        table.add_column("Status")
        for role, missing in ctx.missing_models.items():
            pass
        for role, role_cfg in ctx.config.models.roles.items():
            status = ("[red]MISSING[/red]"
                      if role in ctx.missing_models else "[green]ok[/green]")
            table.add_row(role, role_cfg.model, status)
        console.print(table)

        if ctx.missing_models:
            console.print("\n[bold yellow]Missing models - install with:[/bold yellow]")
            for model in sorted(set(ctx.missing_models.values())):
                console.print(f"  ollama pull {model}")
            raise typer.Exit(code=1)

        console.print(f"\n[dim]Available locally ({len(available)}):[/dim] "
                      + ", ".join(available))
        if loaded:
            console.print(f"[dim]Currently loaded:[/dim] " + ", ".join(loaded))
    finally:
        await ctx.close()


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
