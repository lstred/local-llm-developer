"""SQLAlchemy models + helpers for orchestrator state.

Three tables:

* ``jobs``       - one row per long-running orchestration job
* ``phase_runs`` - one row per phase execution (incl. retries / cycles)
* ``events``     - append-only timeline (artifact writes, model events,
                   gate decisions, errors)

The store is intentionally append-mostly. The current state of a job
can always be reconstructed from its ``phase_runs`` + ``events``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace: Mapped[str] = mapped_column(Text)
    task: Mapped[str] = mapped_column(Text)
    workflow: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_utcnow, onupdate=_utcnow)
    final_verdict: Mapped[str | None] = mapped_column(String(32), default=None)
    final_score: Mapped[int | None] = mapped_column(Integer, default=None)

    phases: Mapped[list[PhaseRun]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin")


class PhaseRun(Base):
    __tablename__ = "phase_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    phase: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str] = mapped_column(String(64))
    cycle: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    artifacts: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    job: Mapped[Job] = relationship(back_populates="phases")


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


# --------------------------------------------------------------------------- #
#  Store
# --------------------------------------------------------------------------- #


class StateStore:
    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(database_url, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    def session(self) -> AsyncSession:
        return self.session_factory()

    # -- Convenience ----------------------------------------------------- #

    async def create_job(self, *, job_id: str, workspace: str,
                         task: str, workflow: str) -> Job:
        async with self.session() as s:
            job = Job(id=job_id, workspace=workspace, task=task,
                      workflow=workflow, status="pending")
            s.add(job)
            await s.commit()
            await s.refresh(job)
            return job

    async def update_job_status(self, job_id: str, status: str, *,
                                verdict: str | None = None,
                                score: int | None = None) -> None:
        async with self.session() as s:
            job = await s.get(Job, job_id)
            if not job:
                return
            job.status = status
            job.updated_at = _utcnow()
            if verdict is not None:
                job.final_verdict = verdict
            if score is not None:
                job.final_score = score
            await s.commit()

    async def add_phase_run(self, *, job_id: str, phase: str, agent: str,
                            cycle: int) -> int:
        async with self.session() as s:
            row = PhaseRun(job_id=job_id, phase=phase, agent=agent,
                           cycle=cycle, status="running",
                           started_at=_utcnow())
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return row.id

    async def finish_phase_run(self, run_id: int, *, status: str,
                               score: int | None = None,
                               notes: str | None = None,
                               artifacts: dict[str, Any] | None = None) -> None:
        async with self.session() as s:
            row = await s.get(PhaseRun, run_id)
            if not row:
                return
            row.status = status
            row.score = score
            row.notes = notes
            row.artifacts = artifacts
            row.finished_at = _utcnow()
            await s.commit()

    async def log_event(self, *, kind: str, job_id: str | None = None,
                        payload: dict[str, Any] | None = None) -> None:
        async with self.session() as s:
            s.add(Event(kind=kind, job_id=job_id, payload=payload or {}))
            await s.commit()

    async def list_jobs(self, limit: int = 50) -> list[Job]:
        async with self.session() as s:
            res = await s.execute(
                select(Job).order_by(Job.created_at.desc()).limit(limit)
            )
            return list(res.scalars())

    async def get_job(self, job_id: str) -> Job | None:
        async with self.session() as s:
            return await s.get(Job, job_id)

    async def list_events(self, job_id: str, limit: int = 500) -> list[Event]:
        async with self.session() as s:
            res = await s.execute(
                select(Event).where(Event.job_id == job_id)
                .order_by(Event.ts.asc()).limit(limit)
            )
            return list(res.scalars())


__all__ = ["StateStore", "Job", "PhaseRun", "Event"]
