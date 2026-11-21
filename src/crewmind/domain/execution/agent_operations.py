"""The agent API: the only way an agent affects anything (P3, IF-6.1 to IF-6.3).

Every operation here is called with a run token. The run decides the project and the
agent, so no call names either.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.conversation import service as conversation
from crewmind.domain.conversation import speaking
from crewmind.domain.conversation.operations import MESSAGE_POSTED, MessageItem, item
from crewmind.domain.conversation.service import MSG_1, MSG_2, Author, ChannelKind
from crewmind.domain.execution import context_pack, roster
from crewmind.domain.execution.agent import AgentView, agent_of
from crewmind.domain.execution.model import RunKind, SeatKind, TeamState
from crewmind.domain.execution.operations import RoleItem, RoleList, Roster
from crewmind.services import services_of
from crewmind.storage.models import Channel, Message, Role, Seat, Team

AGENT = frozenset({Principal.AGENT_RUN})

INV_23 = rules.register(
    Rule("INV-23", "A chat run changes no state except posting and carrying out a directive.")
)


class AgentIdentity(BaseModel):
    seat: str
    kind: str
    role: str
    project: str
    run_id: str
    run_kind: str


class ContextPack(BaseModel):
    system_prompt: str
    context_pack: str
    run_kind: str
    local_tools: list[str] = Field(description="Tools the role grants inside the sandbox.")
    message_max: int = Field(description="The most characters one message may have (MSG-1).")


class ReadInput(BaseModel):
    channel: str = Field(conversation.PROJECT_CHAT, description="One of your channels.")
    limit: int = Field(20, ge=1, le=100, description="How many recent messages.")


class Messages(BaseModel):
    items: list[MessageItem]


class PostInput(BaseModel):
    body: str = Field(description="The message, in plain words. Lead with the answer or the ask.")
    channel: str = Field(conversation.PROJECT_CHAT, description="One of your channels.")
    reply_to: int | None = Field(
        None, description="The message this answers. Default: the newest one addressed to you."
    )


class PostOutcome(BaseModel):
    """A message is posted, sent back once for a rewrite, or held for a reporting slot.
    None of these is a refusal (MSG-8, MSG-12, P1)."""

    posted: bool
    id: int | None = None
    body: str | None = None
    reply_to: int | None = None
    thread_id: int | None = None
    marker: str | None = Field(default=None, description="long or unclear, if it still is.")
    feedback: str | None = Field(default=None, description="What to change, or why it waits.")
    held_until: datetime | None = None


class HireInput(BaseModel):
    team: str = Field(min_length=1, max_length=60, description="A name for the team.")
    role: str = Field(description="The role its members take.")
    members: int = Field(1, description="How many members.")


class TeamInput(BaseModel):
    team: str = Field(description="The team's name.")


def work_run_only(view: AgentView) -> None:
    """CHAT-6, INV-23: a chat run answers and proposes; it does not change state."""
    if view.run.kind == RunKind.CHAT:
        raise Refusal(
            "chat_run_changes_nothing",
            "This is a chat run. It can answer, explain and propose, but it changes no state.",
            rule=INV_23.id,
            hint="Propose it to the chairman, who can issue a directive.",
        )


async def _channel(context: Context, view: AgentView, name: str) -> Channel:
    mine = await conversation.channels_of(context.session, view.seat)
    found = next((c for c in mine if c.name == name), None)
    if found is None:
        raise Refusal(
            "not_your_channel",
            f"{name} is not one of your channels: {', '.join(c.name for c in mine)}.",
            kind=RefusalKind.FORBIDDEN,
            rule=MSG_1.id,
            hint="Post in one of your own channels.",
        )
    return found


@operation(
    "agent.whoami",
    summary="Who you are: your seat, role, project and run.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def whoami(context: Context, payload: Empty) -> AgentIdentity:
    view = await agent_of(context)
    return AgentIdentity(
        seat=view.seat.name,
        kind=view.seat.kind,
        role=view.role.name,
        project=view.project.name,
        run_id=view.run.id,
        run_kind=view.run.kind,
    )


@operation(
    "agent.context",
    summary="Your context pack for this run: the goal, your messages, notices and situation.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def context(context: Context, payload: Empty) -> ContextPack:
    """EXE-15, EXE-11: built once per run and stored exactly as sent."""
    view = await agent_of(context)
    run = view.run
    if run.context_pack is None:
        run.system_prompt = context_pack.system_prompt(view)
        run.context_pack = await context_pack.build(
            context.session, services_of(context).settings, view, context.now
        )
    assert run.system_prompt is not None
    return ContextPack(
        system_prompt=run.system_prompt,
        context_pack=run.context_pack,
        run_kind=run.kind,
        local_tools=[] if run.kind == RunKind.CHAT else [str(tool) for tool in view.role.tools],
        message_max=conversation.MESSAGE_MAX,
    )


@operation(
    "agent.read_messages",
    summary="Read recent messages in one of your channels.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def read_messages(context: Context, payload: ReadInput) -> Messages:
    view = await agent_of(context)
    target = await _channel(context, view, payload.channel)
    rows = await context.session.scalars(
        select(Message)
        .where(Message.channel_id == target.id)
        .order_by(Message.id.desc())
        .limit(payload.limit)
    )
    return Messages(items=[item(row, target.name) for row in reversed(list(rows))])


@operation(
    "agent.post_message",
    summary="Post a message in one of your channels.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def post_message(context: Context, payload: PostInput) -> PostOutcome:
    """MSG-1, MSG-2, CHAT-11: in the project chat the CEO may post at any time; any other
    agent only when addressed, or in a thread it was addressed in. A reply is threaded to
    the message it answers."""
    view = await agent_of(context)
    seat = view.seat
    target = await _channel(context, view, payload.channel)
    reply_to = payload.reply_to
    if target.kind == ChannelKind.PROJECT:
        waiting = await conversation.unanswered_from_people(context.session, seat)
        if reply_to is None and waiting:
            reply_to = waiting[0].id
        if seat.kind != SeatKind.CEO and not await _was_addressed(context, seat, reply_to):
            raise Refusal(
                "not_addressed",
                "In the project chat you speak only when addressed, or in a thread you were "
                "addressed in.",
                rule=MSG_2.id,
                hint="Post in your team room, or leave a suggestion for the CEO.",
            )
    elif target.kind == ChannelKind.TEAM:
        others = await context.session.scalar(
            select(Seat.id).where(Seat.team_id == target.team_id, Seat.id != seat.id).limit(1)
        )
        if others is None and seat.kind != SeatKind.CEO:
            raise Refusal(
                "empty_room",
                "Nobody else is in this team room.",
                rule=MSG_1.id,
                hint="Post in leadership or reply in the project chat.",
            )
    from crewmind.domain.conversation.extras import check_pair

    thread_id = 0
    if reply_to is not None:
        parent = await context.session.get(Message, reply_to)
        thread_id = (parent.thread_id or parent.id) if parent is not None else 0
    await check_pair(
        context.session, services_of(context).settings, view.project, target, thread_id, context.now
    )
    prepared = await speaking.prepare(
        context.session,
        services_of(context).settings,
        view.project,
        seat,
        view.run,
        target,
        reply_to,
        payload.body,
        context.now,
    )
    if prepared.feedback is not None:
        return PostOutcome(posted=False, feedback=prepared.feedback)
    if prepared.hold_until is not None:
        speaking.hold(context.session, seat, view.run, prepared, context.now)
        return PostOutcome(
            posted=False,
            held_until=prepared.hold_until,
            feedback="Held, not refused: the chairman asked for status posts at set times. "
            f"This one goes out at {prepared.hold_until:%H:%M} UTC with any others. "
            "Do not post it again.",
        )
    message = await conversation.post(
        context.session,
        target,
        author=Author.AGENT,
        author_id=seat.id,
        author_name=seat.name,
        body=prepared.body,
        now=context.now,
        reply_to=reply_to,
        run_id=view.run.id,
        detail={"lint": prepared.marker} if prepared.marker else None,
    )
    context.record(
        MESSAGE_POSTED,
        subject=("message", str(message.id)),
        project_id=view.project.id,
        after={"channel": target.name, "author": seat.name},
    )
    return PostOutcome(
        posted=True,
        id=message.id,
        body=message.body,
        reply_to=message.reply_to,
        thread_id=message.thread_id,
        marker=prepared.marker,
    )


async def _was_addressed(context: Context, seat: Seat, reply_to: int | None) -> bool:
    if reply_to is None:
        return False
    parent = await context.session.get(Message, reply_to)
    if parent is None:
        return False
    thread = parent.thread_id or parent.id
    rows = await context.session.scalars(
        select(Message.addressed).where((Message.id == thread) | (Message.thread_id == thread))
    )
    return any(seat.id in addressed for addressed in rows)


async def _show(context: Context, view: AgentView) -> Roster:
    rows = await context.session.execute(
        select(Seat, Role, Team)
        .join(Role, Role.id == Seat.role_id)
        .outerjoin(Team, Team.id == Seat.team_id)
        .where(Seat.project_id == view.project.id)
        .order_by(Seat.created_at, Seat.name)
    )
    from crewmind.domain.execution.operations import SeatItem

    seats: list[Any] = [
        SeatItem(
            name=seat.name,
            kind=seat.kind,
            role=role.name,
            team=team.name if team else None,
            lead=seat.is_lead,
            state=seat.state,
            pause_reason=seat.pause_reason,
        )
        for seat, role, team in rows.all()
    ]
    return Roster(seats=seats, teams=sorted({s.team for s in seats if s.team}))


@operation(
    "agent.list_roles",
    summary="List the roles a team can be hired from.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def list_roles(context: Context, payload: Empty) -> RoleList:
    rows = await context.session.scalars(select(Role).order_by(Role.name, Role.version))
    return RoleList(
        items=[
            RoleItem(
                name=row.name,
                version=row.version,
                seat_kind=row.seat_kind,
                description=row.description,
                tools=[str(tool) for tool in row.tools],
            )
            for row in rows
        ]
    )


@operation(
    "agent.hire_team",
    summary="Hire a team from a role (CEO only).",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def hire_team(context: Context, payload: HireInput) -> Roster:
    """EXE-1: the CEO hires within `teams.max` without approval, by the same path as the
    chairman. The hire is announced in the chat."""
    view = await agent_of(context)
    work_run_only(view)
    await roster.hire_team(
        context.session,
        services_of(context).settings,
        view.project,
        name=payload.team,
        role_name=payload.role,
        members=payload.members,
        caller=context.caller,
        now=context.now,
    )
    return await _show(context, view)


@operation(
    "agent.stand_down_team",
    summary="Stand a team down (CEO only).",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def stand_down_team(context: Context, payload: TeamInput) -> Roster:
    view = await agent_of(context)
    work_run_only(view)
    await roster.set_team_state(
        context.session,
        view.project,
        payload.team,
        TeamState.STOOD_DOWN,
        caller=context.caller,
        now=context.now,
    )
    return await _show(context, view)


@operation(
    "agent.recall_team",
    summary="Recall a team that was stood down (CEO only).",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def recall_team(context: Context, payload: TeamInput) -> Roster:
    view = await agent_of(context)
    work_run_only(view)
    await roster.set_team_state(
        context.session,
        view.project,
        payload.team,
        TeamState.ACTIVE,
        caller=context.caller,
        now=context.now,
    )
    return await _show(context, view)
