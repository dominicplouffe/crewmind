"""What happens to an agent's message before it is posted: the quote-back after a
correction, the communication lint with one rewrite, and reporting cadence (MSG-8, MSG-12,
CHAT-11). None of this refuses: a message is posted, sent back once, or held for a slot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import platform_job
from crewmind.domain.conversation import service as conversation
from crewmind.domain.conversation import standard
from crewmind.domain.conversation.service import Author, ChannelKind
from crewmind.domain.execution.model import SeatKind
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import SettingsService, Subject
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import (
    Channel,
    Correction,
    HeldPost,
    Membership,
    Message,
    Project,
    Run,
    Seat,
)

OFF = "off"
DEFAULT_FIRST_SLOT = time(8, 0)  # `brief.time`'s default, used when the chairman's is off
REPORT_DELIVERED = event_type("report.delivered", "A held status post went out at its slot.")
CADENCE_JOB = platform_job("scheduler: reporting cadence")


@dataclass(frozen=True)
class Prepared:
    """What to do with a message: post `body` (with `marker`), send `feedback` back, or
    hold it until `hold_until`."""

    body: str
    marker: str | None = None
    feedback: str | None = None
    hold_until: datetime | None = None


def next_slot(now: datetime, slots: int, first: time, zone: ZoneInfo) -> datetime:
    """MSG-8: `slots` reporting times a day, evenly spaced from `first` in the project's
    time zone. Returns the first one after `now`."""
    local = now.astimezone(zone)
    start = datetime.combine(local.date(), first, tzinfo=zone) - timedelta(days=1)
    step = timedelta(days=1) / slots
    slot = start
    while slot <= local:
        slot += step
    return slot.astimezone(UTC)


async def _chairman(session: AsyncSession, project_id: str) -> str | None:
    return await session.scalar(
        select(Membership.person_id).where(
            Membership.project_id == project_id,
            Membership.role == "chairman",
            Membership.state == "member",
        )
    )


async def _budget(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    target: Channel,
    parent: Message | None,
) -> tuple[int, bool]:
    """The word budget for a message and whether a person reads it (MSG-12)."""
    if target.kind != ChannelKind.PROJECT:
        subject = Subject(Scope.PROJECT, project.id, project.type)
        return int(await settings.get(session, subject, "agent.message_words")), False
    reader = (
        parent.author_id
        if parent is not None and parent.author_kind == Author.PERSON
        else await _chairman(session, project.id)
    )
    level = (
        await settings.get(session, Subject(Scope.PERSON, reader), "chat.brevity")
        if reader
        else "normal"
    )
    return standard.WORD_BUDGETS[str(level)], True


async def budget_line(session: AsyncSession, settings: SettingsService, project: Project) -> str:
    """MSG-12, CHAT-13: the length budgets, stated to the agent before it writes."""
    chairman = await _chairman(session, project.id)
    level = (
        str(await settings.get(session, Subject(Scope.PERSON, chairman), "chat.brevity"))
        if chairman
        else "normal"
    )
    subject = Subject(Scope.PROJECT, project.id, project.type)
    to_agents = int(await settings.get(session, subject, "agent.message_words"))
    return (
        f"Length: at most {standard.WORD_BUDGETS[level]} words to a person (their brevity "
        f"setting is {level}) and {to_agents} to an agent. Quoted text does not count."
    )


async def prepare(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    seat: Seat,
    run: Run,
    target: Channel,
    reply_to: int | None,
    body: str,
    now: datetime,
) -> Prepared:
    parent = await session.get(Message, reply_to) if reply_to is not None else None
    if parent is not None and (parent.detail or {}).get("kind") == "correction":
        correction = await session.get(Correction, (parent.detail or {}).get("correction"))
        if correction is not None:
            body = standard.quoted(correction.question, body)

    budget, to_a_person = await _budget(session, settings, project, target, parent)
    findings = standard.lint(body, budget=budget, to_a_person=to_a_person)
    if findings and not run.rewrite_asked:
        run.rewrite_asked = True
        return Prepared(body, feedback=standard.feedback_of(findings))
    run.rewrite_asked = False
    marker = standard.marker_of(findings)

    unprompted = parent is None or parent.author_kind != Author.PERSON
    if seat.kind == SeatKind.CEO and target.kind == ChannelKind.PROJECT and unprompted:
        subject = Subject(Scope.PROJECT, project.id, project.type)
        cadence = await settings.get(session, subject, "report.cadence")
        if cadence != OFF:
            chairman = await _chairman(session, project.id)
            first = (
                await settings.get(session, Subject(Scope.PERSON, chairman), "brief.time")
                if chairman
                else OFF
            )
            start = DEFAULT_FIRST_SLOT if first == OFF else time.fromisoformat(str(first))
            zone = ZoneInfo(str(await settings.get(session, subject, "project.timezone")))
            return Prepared(body, marker, hold_until=next_slot(now, int(cadence), start, zone))
    return Prepared(body, marker)


def hold(session: AsyncSession, seat: Seat, run: Run, prepared: Prepared, now: datetime) -> None:
    """MSG-8: an unprompted status post between slots is queued, never refused."""
    assert prepared.hold_until is not None
    session.add(
        HeldPost(
            project_id=seat.project_id,
            seat_id=seat.id,
            body=prepared.body,
            marker=prepared.marker,
            run_id=run.id,
            created_at=now,
            due_at=prepared.hold_until,
        )
    )


async def deliver_due(session: AsyncSession, project: Project, now: datetime) -> None:
    """MSG-8: at a slot, every held post goes out together, in the order written."""
    rows = list(
        await session.scalars(
            select(HeldPost)
            .where(
                HeldPost.project_id == project.id,
                HeldPost.delivered_at.is_(None),
                HeldPost.due_at <= now,
            )
            .order_by(HeldPost.id)
        )
    )
    if not rows:
        return
    target = await conversation.channel(session, project.id, conversation.PROJECT_CHAT)
    for row in rows:
        seat = await session.get(Seat, row.seat_id)
        if seat is None:
            continue
        detail: dict[str, object] = {"kind": "held report"}
        if row.marker:
            detail["lint"] = row.marker
        message = await conversation.post(
            session,
            target,
            author=Author.AGENT,
            author_id=seat.id,
            author_name=seat.name,
            body=row.body,
            now=now,
            run_id=row.run_id,
            detail=detail,
        )
        row.delivered_at = now
        append_event(
            session,
            type=REPORT_DELIVERED,
            caller=CADENCE_JOB,
            at=now,
            subject=("message", str(message.id)),
            project_id=project.id,
        )
