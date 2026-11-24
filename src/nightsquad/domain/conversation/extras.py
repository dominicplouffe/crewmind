"""The pair breaker, search, read positions, the chat header and the activity feed
(MSG-9, CHAT-14, CHAT-17, CHAT-18, CHAT-19, EXE-4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import PERSON_AND_MCP, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.budget import service as budget
from nightsquad.domain.conversation import service
from nightsquad.domain.conversation.operations import MessageItem, item
from nightsquad.domain.conversation.service import Author, MessageKind
from nightsquad.domain.decisions import desk
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.model import LIVE_STATES, SeatState
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.projects import lifecycle
from nightsquad.domain.projects.access import view_of
from nightsquad.domain.projects.model import LIFTED_BY, Hold
from nightsquad.domain.projects.operations import ProjectRef
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject
from nightsquad.services import services_of
from nightsquad.storage.events import event_type
from nightsquad.storage.models import (
    Artifact,
    Channel,
    Event,
    FrozenThread,
    Message,
    Project,
    Run,
    RunStep,
    Seat,
)

THREAD_FROZEN = event_type("thread.frozen", "The pair breaker froze a thread (MSG-9).")
THREAD_UNFROZEN = event_type("thread.unfrozen", "The chairman unfroze a thread (MSG-9).")
MSG_9 = rules.register(Rule("MSG-9", "Two agents cannot loop in a thread while nothing changes."))

# Events that are talk or bookkeeping, not a change of work state (MSG-9).
_NOT_WORK = ("message.", "run.", "thread.", "session.", "token.", "action_card.")


async def is_frozen(session: AsyncSession, channel_id: str, thread_id: int) -> bool:
    row = await session.scalar(
        select(FrozenThread).where(
            FrozenThread.channel_id == channel_id,
            FrozenThread.thread_id == thread_id,
            FrozenThread.frozen.is_(True),
        )
    )
    return row is not None


async def check_pair(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    target: Channel,
    thread_id: int,
    now: datetime,
) -> None:
    """MSG-9: when a thread's last `thread.freeze_after` messages come from the same two
    agents, with no person, and nothing else changed in the project during that span, the
    thread freezes. Further posts are refused and the CEO is told."""
    if await is_frozen(session, target.id, thread_id):
        raise Refusal(
            "thread_frozen",
            "This thread is frozen: two agents were going back and forth while nothing in "
            "the project changed.",
            rule=MSG_9.id,
            hint="Only the chairman can unfreeze it. Do the work, or raise it with the CEO.",
        )
    limit = int(
        await settings.get(
            session, Subject(Scope.PROJECT, project.id, project.type), "thread.freeze_after"
        )
    )
    in_thread = (
        (Message.thread_id == thread_id) | (Message.id == thread_id)
        if thread_id
        else Message.thread_id.is_(None)
    )
    last = list(
        await session.scalars(
            select(Message)
            .where(Message.channel_id == target.id, Message.kind == MessageKind.MESSAGE, in_thread)
            .order_by(Message.id.desc())
            .limit(limit)
        )
    )
    authors = {message.author_id for message in last}
    only_agents = all(message.author_kind == Author.AGENT for message in last)
    if len(last) < limit or not only_agents or len(authors) != 2:
        return
    span_start = await session.scalar(
        select(Event.id).where(
            Event.project_id == project.id,
            Event.type == "message.posted",
            Event.subject_id == str(last[-1].id),
        )
    )
    changed = await session.scalar(
        select(func.count())
        .select_from(Event)
        .where(
            Event.project_id == project.id,
            Event.id > (span_start or 0),
            *[Event.type.not_like(f"{prefix}%") for prefix in _NOT_WORK],
        )
    )
    if changed:
        return
    raise_frozen = Refusal(
        "thread_frozen",
        f"This thread is now frozen after {limit} messages between two agents with nothing "
        "else changing.",
        rule=MSG_9.id,
        hint="Only the chairman can unfreeze it.",
    )

    project_id, channel_id, channel_name = project.id, target.id, target.name

    async def keep(after: AsyncSession) -> None:
        after.add(
            FrozenThread(
                project_id=project_id,
                channel_id=channel_id,
                thread_id=thread_id,
                frozen=True,
                detail={"messages": limit, "agents": sorted(authors)},
                frozen_at=now,
            )
        )
        chief = await ceo_of(after, project_id)
        notices.notify(
            after, project_id, chief.id, "thread frozen",
            f"A thread in {channel_name} was frozen after {limit} messages between two "
            "agents with nothing else changing.", now,
        )  # fmt: skip
        await service.platform_line(
            after,
            project_id,
            f"A thread in {channel_name} was frozen: {limit} messages between two agents "
            "while nothing in the project changed. Only you can unfreeze it.",
            now,
            detail={"kind": "thread frozen", "channel": channel_name, "thread": thread_id},
        )

    raise_frozen.afterwards = keep
    raise raise_frozen


class ThreadRef(ProjectRef):
    channel: str = Field(description="The channel's name.")
    thread_id: int = Field(0, description="The thread's first message id; 0 for the main line.")


class Done(BaseModel):
    done: bool = True


class SearchInput(ProjectRef):
    query: str = Field(min_length=2, max_length=200, description="Words to look for.")
    limit: int = Field(20, ge=1, le=100, description="How many results.")


class SearchHits(BaseModel):
    messages: list[MessageItem]
    artifacts: list[str]


class MarkReadInput(ProjectRef):
    message_id: int = Field(description="The last message you have read.")
    channel: str = Field(service.PROJECT_CHAT, description="The channel.")


class Working(BaseModel):
    seat: str
    name: str = Field(description="The name the agent goes by (EXE-18).")
    run_kind: str
    doing: str


class HoldLine(BaseModel):
    reason: str
    lifts: str


class Header(BaseModel):
    """CHAT-18: Now, Next, Waiting on you, and the budget against the wall."""

    state: str
    now: list[Working]
    next: list[str]
    waiting_on_you: int = Field(description="The desk count for this project (HUM-10).")
    budget: str
    budget_spent: int
    budget_wall: int
    holds: list[HoldLine]
    notes: list[str] = Field(description="Substitutions and seats that cannot run (P12).")
    unread: int


class FeedItem(BaseModel):
    id: int
    at: datetime
    text: str
    actor: str
    type: str


class Feed(BaseModel):
    items: list[FeedItem]
    next: str | None = None


class FeedInput(ProjectRef):
    after: str | None = Field(default=None, description="Cursor from the previous page.")
    limit: int = Field(50, ge=1, le=200, description="How many items.")


@operation(
    "chat.unfreeze",
    summary="Unfreeze a thread the pair breaker froze.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def unfreeze(context: Context, payload: ThreadRef) -> Done:
    """MSG-9: only the chairman unfreezes a thread."""
    target = await service.channel(context.session, payload.project_id, payload.channel)
    row = await context.session.scalar(
        select(FrozenThread).where(
            FrozenThread.channel_id == target.id,
            FrozenThread.thread_id == payload.thread_id,
            FrozenThread.frozen.is_(True),
        )
    )
    if row is None:
        raise Refusal("thread_not_frozen", "That thread is not frozen.", kind=RefusalKind.NOT_FOUND)
    await context.session.delete(row)
    context.record(
        THREAD_UNFROZEN,
        subject=("thread", f"{target.name}/{payload.thread_id}"),
        project_id=payload.project_id,
        before={"frozen": True},
        after={"frozen": False},
    )
    return Done()


@operation(
    "chat.search",
    summary="Search the project's messages and files.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def search(context: Context, payload: SearchInput) -> SearchHits:
    """CHAT-14: search across the project's history and artifact names."""
    pattern = f"%{payload.query.lower()}%"
    rows = await context.session.execute(
        select(Message, Channel.name)
        .join(Channel, Channel.id == Message.channel_id)
        .where(Message.project_id == payload.project_id, func.lower(Message.body).like(pattern))
        .order_by(Message.id.desc())
        .limit(payload.limit)
    )
    names = await context.session.scalars(
        select(Artifact.name)
        .where(Artifact.project_id == payload.project_id, func.lower(Artifact.name).like(pattern))
        .order_by(Artifact.name)
        .limit(payload.limit)
    )
    return SearchHits(
        messages=[item(message, name) for message, name in rows.all()], artifacts=list(names)
    )


@operation(
    "chat.mark_read",
    summary="Record how far you have read. Your read position is your own.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.REVERSIBLE,
)
async def mark_read(context: Context, payload: MarkReadInput) -> Done:
    """CHAT-17, MSG-13: each person has their own read position, shared by every surface."""
    target = await service.channel(context.session, payload.project_id, payload.channel)
    await service.mark_read(
        context.session, target.id, "person", context.caller.actor_id, payload.message_id
    )
    return Done()


def _doing(step: RunStep | None, run: Run) -> str:
    if step is None:
        return "starting" if run.state == "leased" else "reading its context"
    if step.kind == "tool call":
        return f"using {step.data.get('tool', 'a tool')}"
    return "thinking"


@operation(
    "chat.header",
    summary="What is happening now, what is next, what waits on you, and the budget.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def header(context: Context, payload: ProjectRef) -> Header:
    """CHAT-18, HUM-10, EXE-4, P17: every hold is shown with what lifts it, and "waiting
    on you" is the caller's desk for this project, not a count of its own."""
    project = view_of(context).project
    session = context.session
    working: list[Working] = []
    live = await session.execute(
        select(Run, Seat)
        .join(Seat, Seat.id == Run.seat_id)
        .where(Run.project_id == project.id, Run.state.in_(LIVE_STATES))
        .order_by(Run.queued_at)
    )
    for run, seat in live.all():
        step = await session.scalar(
            select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.id.desc()).limit(1)
        )
        working.append(
            Working(
                seat=seat.name,
                name=seat.display_name,
                run_kind=run.kind,
                doing=_doing(step, run),
            )
        )
    holds = await lifecycle.active_holds(session, project.id)
    coming = [
        f"The hold lifts at {row.lift_at.isoformat(timespec='minutes')}."
        for row in holds
        if row.lift_at is not None
    ]
    queued = await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(Run.project_id == project.id, Run.state == "queued")
    )
    if queued:
        coming.append(f"{queued} run(s) queued.")
    waiting = await desk.of_person_in(session, context.caller.actor_id, project.id, context.now)
    state = await budget.state(session, services_of(context).settings, project, context.now)
    seats = await session.scalars(select(Seat).where(Seat.project_id == project.id))
    notes: list[str] = []
    for seat in seats:
        if seat.substitution:
            notes.append(f"{seat.display_name}: {seat.substitution}")
        if seat.state == SeatState.PAUSED:
            notes.append(f"{seat.display_name} is paused: {seat.pause_reason or 'it cannot run'}.")
    target = await service.channel(session, project.id, service.PROJECT_CHAT)
    position = await service.read_position(session, target.id, "person", context.caller.actor_id)
    unread = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.channel_id == target.id,
            Message.id > position,
            Message.author_id != context.caller.actor_id,
        )
    )
    return Header(
        state=project.state,
        now=working,
        next=coming,
        waiting_on_you=len(waiting),
        budget=budget.arithmetic(state),
        budget_spent=state.spent,
        budget_wall=state.wall,
        holds=[HoldLine(reason=row.reason, lifts=LIFTED_BY[Hold(row.reason)]) for row in holds],
        notes=notes,
        unread=int(unread or 0),
    )


def _plain(event: Event) -> str:
    """One event in plain words (CHAT-19, P18)."""
    after: dict[str, Any] = event.after or {}
    before: dict[str, Any] = event.before or {}
    detail: dict[str, Any] = event.detail or {}
    kind = event.type
    if kind == "project.state_changed":
        return f"The project went from {before.get('state')} to {after.get('state')}."
    if kind == "project.hold_added":
        return f"A hold was added: {after.get('hold')}. It lifts by {detail.get('lifted_by')}."
    if kind == "project.hold_lifted":
        return f"The {before.get('hold')} hold was lifted ({detail.get('cause')})."
    if kind == "setting.changed":
        return f"{event.subject_id} changed from {before.get('value')} to {after.get('value')}" + (
            f": {detail.get('reason')}" if detail.get("reason") else "."
        )
    if kind == "run.state_changed":
        why = f" ({detail.get('why')})" if detail.get("why") else ""
        return f"A {detail.get('kind')} run is now {after.get('state')}{why}."
    if kind == "artifact.version_added":
        return f"{detail.get('author')} saved version {after.get('version')} of {event.subject_id}."
    if kind == "team.hired":
        return f"Team {event.subject_id} was hired ({detail.get('members')} x {after.get('role')})."
    if kind == "directive.state_changed":
        return f"Directive {event.subject_id} is now {after.get('state')}."
    if kind == "budget.threshold_reached":
        return f"The budget passed its {after.get('threshold')} level."
    noun = event.subject_kind.replace("_", " ").capitalize()
    if kind == "project.created":
        return "The project was created."
    if kind == "seat.created":
        return f"{after.get('display_name') or event.subject_id} joined the squad."
    if kind == "seat.renamed":
        return f"{before.get('display_name')} is now called {after.get('display_name')}."
    if kind == "guard.changed":
        return f"The {event.subject_id} guard changed."
    if kind.endswith(".state_changed") and after.get("state"):
        return f"{noun} {event.subject_id} is now {after.get('state')}."
    action = kind.split(".", 1)[-1].replace("_", " ")
    return f"{noun} {event.subject_id}: {action}."


@operation(
    "record.feed",
    summary="The activity feed: every state change in plain words, newest last.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def feed(context: Context, payload: FeedInput) -> Feed:
    """CHAT-19: the feed is the event log, in plain words. Messages are left to the chat."""
    statement = select(Event).where(
        Event.project_id == payload.project_id, Event.type != "message.posted"
    )
    if payload.after:
        statement = statement.where(Event.id > int(payload.after))
    rows = list(
        await context.session.scalars(statement.order_by(Event.id).limit(payload.limit + 1))
    )
    more = len(rows) > payload.limit
    rows = rows[: payload.limit]
    return Feed(
        items=[
            FeedItem(id=row.id, at=row.at, text=_plain(row), actor=row.actor_id, type=row.type)
            for row in rows
        ],
        next=str(rows[-1].id) if more else None,
    )
