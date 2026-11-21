"""The dispatcher: derives wake triggers from stored state and queues runs (EXE-2, EXE-3).

Whether an agent has work is decided by queries, before any model call, so an idle project
costs nothing (P8, INV-11). It also keeps the chat from going silent (CHAT-3, INV-24).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.execute import Clock
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import directives
from crewmind.domain.conversation import service as conversation
from crewmind.domain.conversation.service import Author, MessageKind
from crewmind.domain.execution import notices, runs
from crewmind.domain.execution.model import OPEN_STATES, RunKind, RunState, SeatKind, SeatState
from crewmind.domain.projects.model import ProjectState
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.models import Event, Message, Project, Run, Seat, Wake

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=2)  # section 10: the dispatcher runs every 2 s
STATUS_AFTER = timedelta(seconds=45)
"""INV-24 allows 60 seconds. The status is posted at 45 so that it lands inside the limit."""
WAKE_WINDOW = timedelta(hours=1)


async def _work_reasons(
    session: AsyncSession, settings: SettingsService, project: Project, seat: Seat, now: datetime
) -> list[str]:
    reasons: list[str] = []
    if await conversation.unread_for(session, seat, from_agents_only=True):
        reasons.append("unread messages")
    reasons.extend(
        f"notice: {notice.kind}"
        for notice in await notices.pending(session, seat.id)
        if notice.urgent
    )
    if not reasons and seat.kind == SeatKind.CEO:
        every = timedelta(
            seconds=int(await settings.get(session, runs.subject(project), "heartbeat.every"))
        )
        last = await session.scalar(
            select(func.max(Run.queued_at)).where(Run.seat_id == seat.id, Run.kind == RunKind.WORK)
        )
        since = last or project.created_at
        if now - since >= every:
            changed = (
                select(func.count())
                .select_from(Event)
                .where(Event.project_id == project.id, Event.type.not_like("run.%"))
            )
            if last is not None:
                changed = changed.where(Event.at > last)
            changes = await session.scalar(changed)
            if changes:
                reasons.append("heartbeat")
    return reasons


async def wake_limit_reached(
    session: AsyncSession, settings: SettingsService, project: Project, seat: Seat, now: datetime
) -> datetime | None:
    """When the agent may next be woken, if `agent.max_wakes_per_hour` holds it now (GOV-7)."""
    limit = int(await settings.get(session, runs.subject(project), "agent.max_wakes_per_hour"))
    recent = list(
        await session.scalars(
            select(Wake.created_at)
            .where(
                Wake.seat_id == seat.id,
                Wake.kind == RunKind.WORK,
                Wake.created_at > now - WAKE_WINDOW,
            )
            .order_by(Wake.created_at)
        )
    )
    if len(recent) < limit:
        return None
    return recent[len(recent) - limit] + WAKE_WINDOW


async def _status_posted(session: AsyncSession, message_id: int) -> bool:
    return bool(
        await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.reply_to == message_id, Message.kind == MessageKind.STATUS)
        )
    )


async def _silence_reason(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    seat: Seat,
    message: Message,
    now: datetime,
) -> str | None:
    """Why no reply has started, and when one will come; None while a reply is on time."""
    if project.state == ProjectState.PAUSED and await runs.at_wall(session, project.id):
        state = await budget.state(session, settings, project, now)
        return (
            f"No reply yet: the project is paused at its budget wall ({budget.arithmetic(state)}). "
            f"{seat.name} will reply once the budget is raised."
        )
    if RunKind.CHAT not in await runs.allowed_kinds(session, project):
        return (
            f"No reply: the project is {project.state}, so agents are not running. "
            "Start or reopen the project to talk to them."
        )
    if seat.state != SeatState.ACTIVE:
        why = seat.pause_reason or "it is not active"
        return f"No reply yet: {seat.name} is {seat.state} ({why}). It replies once that is fixed."
    if now - message.created_at < STATUS_AFTER:
        return None
    run = await session.scalar(
        select(Run)
        .where(Run.seat_id == seat.id, Run.kind == RunKind.CHAT)
        .order_by(Run.queued_at.desc())
        .limit(1)
    )
    if run is None or run.state not in OPEN_STATES:
        ended = "no run could start" if run is None else f"the last attempt {run.state}"
        return f"No reply yet: {ended}. {seat.name} will try again shortly."
    if run.state == RunState.QUEUED and run.not_before and run.not_before > now:
        return (
            f"No reply yet: a crash is being retried (attempt {run.attempt}). The next try "
            f"starts at {run.not_before.isoformat(timespec='seconds')}."
        )
    if run.state == RunState.QUEUED:
        return (
            f"No reply yet: {seat.name}'s reply is waiting for a free runner. It starts as "
            "soon as one is free."
        )
    return f"{seat.name} is still working on the reply. It will post when ready."


async def dispatch(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """One pass for one project: queue work runs, queue chat runs, post overdue statuses."""
    await directives.release_waiting(session, project, now)
    allowed = await runs.allowed_kinds(session, project)
    seats = list(await session.scalars(select(Seat).where(Seat.project_id == project.id)))
    by_id = {seat.id: seat for seat in seats}
    ceo = next((seat for seat in seats if seat.kind == SeatKind.CEO), None)
    for seat in seats:
        if seat.state != SeatState.ACTIVE:
            continue
        if RunKind.WORK in allowed and not await runs.has_open_run(session, seat.id):
            reasons = await _work_reasons(session, settings, project, seat, now)
            if reasons and await wake_limit_reached(session, settings, project, seat, now) is None:
                await runs.queue(session, seat, RunKind.WORK, reasons, now)
        if RunKind.CHAT in allowed and not await runs.has_open_run(session, seat.id, RunKind.CHAT):
            waiting = await conversation.unanswered_from_people(session, seat)
            if waiting:
                await runs.queue(
                    session, seat, RunKind.CHAT, [f"message {waiting[0].id} from a person"], now
                )
    if ceo is None:
        return
    target = await conversation.channel(session, project.id, conversation.PROJECT_CHAT)
    replied = select(Message.reply_to).where(
        Message.channel_id == target.id, Message.reply_to.is_not(None)
    )
    silent = await session.scalars(
        select(Message).where(
            Message.channel_id == target.id,
            Message.author_kind == Author.PERSON,
            Message.id.not_in(replied),
        )
    )
    for message in silent:
        addressed = [by_id[i] for i in message.addressed if i in by_id] or [ceo]
        reason = await _silence_reason(session, settings, project, addressed[0], message, now)
        if reason is not None and not await _status_posted(session, message.id):
            await conversation.platform_line(
                session,
                project.id,
                reason,
                now,
                reply_to=message.id,
                detail={"kind": "reply status"},
            )


class Dispatcher:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], settings: SettingsService, clock: Clock
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._clock = clock

    async def tick(self) -> None:
        """Each project in its own transaction (BG-1)."""
        now = self._clock()
        async with self._sessions() as session:
            project_ids = list(
                await session.scalars(
                    select(Project.id).where(
                        Project.state.not_in([ProjectState.DELETING, ProjectState.DELETED])
                    )
                )
            )
        for project_id in project_ids:
            try:
                async with self._sessions() as session, session.begin():
                    project = await session.get(Project, project_id)
                    if project is not None:
                        await dispatch(session, self._settings, project, now)
            except Exception:
                logger.exception("dispatcher: project %s failed this tick", project_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("dispatcher: tick failed")
            await asyncio.sleep(TICK.total_seconds())
