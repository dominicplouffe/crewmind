"""Corrections and examples: "not what I asked", and text that is an illustration, not
data (MSG-6, MSG-7, CHAT-8, CHAT-11, section 7.17)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Authority, platform_job
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW, StateMachine
from crewmind.domain.accounts.people import person_or_refuse
from crewmind.domain.conversation import service
from crewmind.domain.conversation.service import Author, MessageKind
from crewmind.domain.memory import pinned
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import Subject
from crewmind.services import services_of
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Correction, ExampleMark, Message, Project, Seat

MSG_6 = rules.register(Rule("MSG-6", "Only the chairman records or removes a correction."))
MSG_7 = rules.register(Rule("MSG-7", "Only a person's message can be marked as an example."))
CORRECTION_CHANGED = event_type("correction.state_changed", "A correction changed state (7.17).")
EXAMPLE_MARKED = event_type("example.marked", "A message was marked as an example (MSG-7).")
EXAMPLE_UNMARKED = event_type("example.unmarked", "An example mark was removed (MSG-7).")
EXPIRY_JOB = platform_job("scheduler: expire corrections")

ILLUSTRATION = "ILLUSTRATION — NOT DATA"  # MSG-7
FOREVER = "forever"


class CorrectionState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"


C = CorrectionState
CORRECTION_MACHINE = StateMachine(
    "correction", "7.17-correction", [(NEW, C.ACTIVE), (C.ACTIVE, C.EXPIRED), (C.ACTIVE, C.REMOVED)]
)


class FixInput(ProjectRef):
    words: str = Field(
        min_length=3, max_length=2000, description="What was wrong, in your own words."
    )
    message_id: int | None = Field(
        default=None, description="The agent's message. Default: the newest one in the chat."
    )


class CorrectionRef(ProjectRef):
    correction_id: int = Field(description="The correction's id, from `corrections list`.")


class ExampleInput(ProjectRef):
    what: str = Field(
        min_length=1,
        max_length=20_000,
        description="The example text, or the id of a message of yours to mark.",
    )


class MessageRef(ProjectRef):
    message_id: int = Field(description="The message's id.")


class CorrectionItem(BaseModel):
    id: int
    agent: str
    question: str
    words: str
    state: str
    expires_at: datetime | None
    note: str | None = None


class CorrectionList(BaseModel):
    items: list[CorrectionItem]


class ExampleItem(BaseModel):
    message_id: int
    is_example: bool


def _item(row: Correction, agent: str, note: str | None = None) -> CorrectionItem:
    return CorrectionItem(
        id=row.id,
        agent=agent,
        question=row.question,
        words=row.words,
        state=row.state,
        expires_at=row.expires_at,
        note=note,
    )


async def _question(session: AsyncSession, reply: Message) -> str:
    """The question that should have been answered: the person's message the reply was
    for, or else the last thing a person said before it."""
    asked = await session.get(Message, reply.reply_to) if reply.reply_to else None
    if asked is None or asked.author_kind != Author.PERSON:
        asked = await session.scalar(
            select(Message)
            .where(
                Message.channel_id == reply.channel_id,
                Message.author_kind == Author.PERSON,
                Message.kind == MessageKind.MESSAGE,
                Message.id < reply.id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
    return asked.body if asked is not None else ""


@operation(
    "corrections.record",
    summary="Tell an agent its reply was not what you asked. It answers again and remembers.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/fix",
)
async def fix(context: Context, payload: FixInput) -> CorrectionItem:
    """MSG-6, CHAT-8, CHAT-11: records the reply, the chairman's words and the question that
    should have been answered. It is pinned for that agent, and for the CEO, until it
    expires or is removed. The agent is asked the question again."""
    person = await person_or_refuse(context.session, context.caller.actor_id)
    project = view_of(context).project
    target = await service.channel(context.session, project.id, service.PROJECT_CHAT)
    wanted = select(Message).where(
        Message.channel_id == target.id,
        Message.author_kind == Author.AGENT,
        Message.kind == MessageKind.MESSAGE,
    )
    if payload.message_id is not None:
        wanted = wanted.where(Message.id == payload.message_id)
    reply = await context.session.scalar(wanted.order_by(Message.id.desc()).limit(1))
    if reply is None:
        raise Refusal(
            "not_an_agents_message",
            "There is no agent's message to correct"
            + (f" with id {payload.message_id}." if payload.message_id else " in this chat yet."),
            kind=RefusalKind.NOT_FOUND,
            rule=MSG_6.id,
            hint="Give the id of an agent's message in the project chat.",
        )
    seat = await context.session.get(Seat, reply.author_id)
    assert seat is not None
    settings = services_of(context).settings
    ttl = await settings.get(
        context.session, Subject(Scope.PROJECT, project.id, project.type), "correction.ttl"
    )
    CORRECTION_MACHINE.check(NEW, C.ACTIVE)
    row = Correction(
        project_id=project.id,
        seat_id=seat.id,
        message_id=reply.id,
        reply=reply.body,
        words=payload.words.strip(),
        question=await _question(context.session, reply),
        state=C.ACTIVE,
        created_at=context.now,
        expires_at=None if ttl == FOREVER else context.now + timedelta(seconds=int(ttl)),
    )
    context.session.add(row)
    await context.session.flush()
    context.record(
        CORRECTION_CHANGED,
        subject=("correction", str(row.id)),
        project_id=project.id,
        after={"state": C.ACTIVE, "agent": seat.name, "message": reply.id},
    )
    await service.post(
        context.session,
        target,
        author=Author.PERSON,
        author_id=person.id,
        author_name=person.name,
        body=f"Not what I asked: {row.words}",
        now=context.now,
        reply_to=reply.id,
        addressed=[seat.id],
        detail={"kind": "correction", "correction": row.id},
    )
    note = await pinned.note_if_over(context.session, settings, project, seat, context.now)
    return _item(row, seat.name, note)


@operation(
    "corrections.remove",
    summary="Remove a correction from an agent's pinned memory.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def remove(context: Context, payload: CorrectionRef) -> CorrectionItem:
    row = await context.session.get(Correction, payload.correction_id)
    if row is None or row.project_id != payload.project_id:
        raise Refusal(
            "correction_not_found",
            f"There is no correction {payload.correction_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            hint="List them with `corrections list`.",
        )
    CORRECTION_MACHINE.check(row.state, C.REMOVED)
    row.state = C.REMOVED
    context.record(
        CORRECTION_CHANGED,
        subject=("correction", str(row.id)),
        project_id=row.project_id,
        before={"state": C.ACTIVE},
        after={"state": C.REMOVED},
    )
    seat = await context.session.get(Seat, row.seat_id)
    return _item(row, seat.name if seat else "")


@operation(
    "corrections.list",
    summary="List the corrections you have given agents.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_corrections(context: Context, payload: ProjectRef) -> CorrectionList:
    rows = await context.session.execute(
        select(Correction, Seat)
        .join(Seat, Seat.id == Correction.seat_id)
        .where(Correction.project_id == payload.project_id)
        .order_by(Correction.id)
    )
    return CorrectionList(items=[_item(row, seat.name) for row, seat in rows.all()])


async def expire(session: AsyncSession, project: Project, now: datetime) -> None:
    """Section 7.17: a correction expires when `correction.ttl` has passed."""
    rows = await session.scalars(
        select(Correction).where(
            Correction.project_id == project.id,
            Correction.state == C.ACTIVE,
            Correction.expires_at.is_not(None),
            Correction.expires_at <= now,
        )
    )
    for row in rows:
        CORRECTION_MACHINE.check(row.state, C.EXPIRED)
        row.state = C.EXPIRED
        append_event(
            session,
            type=CORRECTION_CHANGED,
            caller=EXPIRY_JOB,
            at=now,
            subject=("correction", str(row.id)),
            project_id=project.id,
            before={"state": C.ACTIVE},
            after={"state": C.EXPIRED},
        )


async def example_ids(session: AsyncSession, project_id: str) -> set[int]:
    """The messages marked as examples in a project."""
    rows = await session.scalars(
        select(ExampleMark.message_id).where(ExampleMark.project_id == project_id)
    )
    return set(rows)


def labelled(body: str, is_example: bool) -> str:
    """MSG-7: an example never reaches an agent without its label."""
    return f"[{ILLUSTRATION}] {body}" if is_example else body


@operation(
    "examples.mark",
    summary="Mark text as an example: an illustration agents must not use as data.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/example",
)
async def example(context: Context, payload: ExampleInput) -> ExampleItem:
    """MSG-7, CHAT-8: `/example <text>` posts the text as an example. `/example <message
    id>` marks a message a person already sent."""
    person = await person_or_refuse(context.session, context.caller.actor_id)
    what = payload.what.strip()
    if what.isdigit():
        message = await context.session.get(Message, int(what))
        if (
            message is None
            or message.project_id != payload.project_id
            or message.author_kind != Author.PERSON
        ):
            raise Refusal(
                "not_a_persons_message",
                f"Message {what} is not a person's message in this project.",
                kind=RefusalKind.NOT_FOUND,
                rule=MSG_7.id,
                hint="Mark one of your own messages, or write the example after /example.",
            )
    else:
        target = await service.channel(context.session, payload.project_id, service.PROJECT_CHAT)
        message = await service.post(
            context.session,
            target,
            author=Author.PERSON,
            author_id=person.id,
            author_name=person.name,
            body=what,
            now=context.now,
            kind=MessageKind.STATUS,
            detail={"kind": "example"},
        )
    if message.id not in await example_ids(context.session, payload.project_id):
        context.session.add(
            ExampleMark(
                project_id=payload.project_id, message_id=message.id, created_at=context.now
            )
        )
        context.record(
            EXAMPLE_MARKED, subject=("message", str(message.id)), project_id=payload.project_id
        )
    return ExampleItem(message_id=message.id, is_example=True)


@operation(
    "examples.unmark",
    summary="Remove the example mark from a message.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def unmark(context: Context, payload: MessageRef) -> ExampleItem:
    row = await context.session.scalar(
        select(ExampleMark).where(
            ExampleMark.project_id == payload.project_id,
            ExampleMark.message_id == payload.message_id,
        )
    )
    if row is not None:
        await context.session.delete(row)
        context.record(
            EXAMPLE_UNMARKED,
            subject=("message", str(payload.message_id)),
            project_id=payload.project_id,
        )
    return ExampleItem(message_id=payload.message_id, is_example=False)
