"""The CEO's safety-net heartbeat (EXE-2): when it is next due and whether it will fire.
The dispatcher and the agenda both ask here, so they cannot disagree (INV-22)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.domain.execution import runs
from crewmind.domain.execution.model import RunKind
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.models import Event, Project, Run, Seat


async def next_heartbeat(
    session: AsyncSession, settings: SettingsService, project: Project, seat: Seat
) -> tuple[datetime, bool]:
    """EXE-2, HUM-12: when the CEO's safety-net heartbeat is next due, and whether it will
    fire: it skips when the event log shows no change since the last CEO run."""
    every = timedelta(
        seconds=int(await settings.get(session, runs.subject(project), "heartbeat.every"))
    )
    last = await session.scalar(
        select(func.max(Run.queued_at)).where(Run.seat_id == seat.id, Run.kind == RunKind.WORK)
    )
    changed = (
        select(func.count())
        .select_from(Event)
        .where(Event.project_id == project.id, Event.type.not_like("run.%"))
    )
    if last is not None:
        changed = changed.where(Event.at > last)
    return (last or project.created_at) + every, bool(await session.scalar(changed))
