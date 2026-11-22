"""Channels and messages: the one conversation model (MSG-1, MSG-2, MSG-10, MSG-13).

Every surface and every lane reads and writes through these functions, so there is one
copy of the conversation and one set of read positions.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.storage.models import Channel, Message, ReadPosition, Seat

PROJECT_CHAT = "project chat"
LEADERSHIP = "leadership"

MESSAGE_MIN, MESSAGE_MAX = 1, 20_000  # MSG-1
UNREAD_PER_CHANNEL = 10  # MSG-10

MSG_1 = rules.register(
    Rule("MSG-1", "People post only in the project chat; agents in their channels.")
)
MSG_2 = rules.register(
    Rule(
        "MSG-2",
        "In the project chat, only the CEO speaks unaddressed; others answer when addressed.",
    )
)


class ChannelKind(StrEnum):
    PROJECT = "project"
    LEADERSHIP = "leadership"
    TEAM = "team"


class Author(StrEnum):
    PERSON = "person"
    AGENT = "agent"
    PLATFORM = "platform"


class MessageKind(StrEnum):
    MESSAGE = "message"
    STATUS = "status"
    """A platform line: a status card, a hold notice, a budget line. Costs no tokens."""


async def channel(session: AsyncSession, project_id: str, name: str) -> Channel:
    """The channel called `name`, created on first use."""
    found = await session.scalar(
        select(Channel).where(Channel.project_id == project_id, Channel.name == name)
    )
    if found is not None:
        return found
    raise LookupError(f"no channel {name} in project {project_id}")


async def ensure_channel(
    session: AsyncSession,
    project_id: str,
    name: str,
    kind: ChannelKind,
    now: datetime,
    team_id: str | None = None,
) -> Channel:
    found = await session.scalar(
        select(Channel).where(Channel.project_id == project_id, Channel.name == name)
    )
    if found is None:
        found = Channel(
            project_id=project_id, kind=kind, name=name, team_id=team_id, created_at=now
        )
        session.add(found)
        await session.flush()
    return found


async def channels_of(session: AsyncSession, seat: Seat) -> list[Channel]:
    """The channels an agent reads and posts in (MSG-1): the project chat for the CEO, and for
    others only where addressed; leadership for the CEO and leads; its own team room."""
    rows = list(await session.scalars(select(Channel).where(Channel.project_id == seat.project_id)))
    mine: list[Channel] = []
    for row in rows:
        leads = seat.kind == "ceo" or seat.is_lead
        in_leadership = row.kind == ChannelKind.LEADERSHIP and leads
        in_own_team = row.kind == ChannelKind.TEAM and row.team_id == seat.team_id
        if row.kind == ChannelKind.PROJECT or in_leadership or in_own_team:
            mine.append(row)
    return mine


async def post(
    session: AsyncSession,
    target: Channel,
    *,
    author: Author,
    author_id: str,
    author_name: str,
    body: str,
    now: datetime,
    kind: MessageKind = MessageKind.MESSAGE,
    reply_to: int | None = None,
    addressed: list[str] | None = None,
    run_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> Message:
    if not MESSAGE_MIN <= len(body) <= MESSAGE_MAX:
        raise Refusal(
            "message_length",
            f"A message has {MESSAGE_MIN} to {MESSAGE_MAX} characters; this one has {len(body)}.",
            rule=MSG_1.id,
            hint="Link an artifact instead of pasting a long document.",
        )
    thread_id: int | None = None
    if reply_to is not None:
        parent = await session.get(Message, reply_to)
        if parent is None or parent.channel_id != target.id:
            raise Refusal(
                "reply_target_missing",
                "The message being replied to is not in this channel.",
                rule=MSG_1.id,
            )
        thread_id = parent.thread_id or parent.id
    message = Message(
        project_id=target.project_id,
        channel_id=target.id,
        author_kind=author,
        author_id=author_id,
        author_name=author_name,
        kind=kind,
        body=body,
        reply_to=reply_to,
        thread_id=thread_id,
        addressed=addressed or [],
        run_id=run_id,
        detail=detail,
        created_at=now,
    )
    session.add(message)
    await session.flush()
    return message


async def platform_line(
    session: AsyncSession,
    project_id: str,
    body: str,
    now: datetime,
    *,
    reply_to: int | None = None,
    detail: dict[str, Any] | None = None,
) -> Message:
    """A status line the platform posts in the project chat, at 0 tokens (CHAT-3, EXE-4)."""
    target = await channel(session, project_id, PROJECT_CHAT)
    return await post(
        session,
        target,
        author=Author.PLATFORM,
        author_id="platform",
        author_name="crewmind",
        body=body,
        now=now,
        kind=MessageKind.STATUS,
        reply_to=reply_to,
        detail=detail,
    )


async def read_position(session: AsyncSession, channel_id: str, kind: str, reader_id: str) -> int:
    found = await session.scalar(
        select(ReadPosition.last_read).where(
            ReadPosition.channel_id == channel_id,
            ReadPosition.reader_kind == kind,
            ReadPosition.reader_id == reader_id,
        )
    )
    return found or 0


async def mark_read(
    session: AsyncSession, channel_id: str, kind: str, reader_id: str, message_id: int
) -> None:
    row = await session.scalar(
        select(ReadPosition).where(
            ReadPosition.channel_id == channel_id,
            ReadPosition.reader_kind == kind,
            ReadPosition.reader_id == reader_id,
        )
    )
    if row is None:
        session.add(
            ReadPosition(
                channel_id=channel_id, reader_kind=kind, reader_id=reader_id, last_read=message_id
            )
        )
    elif message_id > row.last_read:
        row.last_read = message_id


def _wakes(seat: Seat, target: Channel, message: Message) -> bool:
    """Whether a message is for this agent to act on. In the project chat, a person's message
    is for whoever it addresses, the CEO by default (CHAT-2); agents' lines there are not
    work. Elsewhere, every message from another member counts."""
    if message.author_kind == Author.PLATFORM:
        return False
    if message.author_kind == Author.AGENT and message.author_id == seat.id:
        return False
    if target.kind != ChannelKind.PROJECT:
        return True
    if message.author_kind != Author.PERSON:
        return seat.id in message.addressed
    return seat.id in message.addressed or (not message.addressed and seat.kind == "ceo")


async def unread_for(
    session: AsyncSession, seat: Seat, *, from_agents_only: bool = False
) -> list[tuple[Channel, Message]]:
    """Every unread message that is for this agent, oldest first per channel (EXE-2).
    A person's message in the project chat is answered by a chat run (MSG-11), so the work
    lane asks for agents' messages only: one lane answers each message, never two."""
    unread: list[tuple[Channel, Message]] = []
    for target in await channels_of(session, seat):
        position = await read_position(session, target.id, Author.AGENT, seat.id)
        rows = await session.scalars(
            select(Message)
            .where(Message.channel_id == target.id, Message.id > position)
            .order_by(Message.id)
        )
        for row in rows:
            if from_agents_only and row.author_kind == Author.PERSON:
                continue
            if _wakes(seat, target, row):
                unread.append((target, row))
    return unread


async def unanswered_from_people(session: AsyncSession, seat: Seat) -> list[Message]:
    """Messages from people, addressed to this agent, that no agent has replied to yet,
    newest first (CHAT-11, MSG-10). An upload's line in the chat is not a question, so it
    starts no reply and costs nothing (P8); the agent sees the file when next addressed."""
    target = await channel(session, seat.project_id, PROJECT_CHAT)
    replied = select(Message.reply_to).where(
        Message.channel_id == target.id,
        Message.reply_to.is_not(None),
        Message.author_kind != Author.PERSON,
        Message.kind == MessageKind.MESSAGE,
    )
    rows = await session.scalars(
        select(Message)
        .where(
            Message.channel_id == target.id,
            Message.author_kind == Author.PERSON,
            Message.kind == MessageKind.MESSAGE,
            Message.id.not_in(replied),
        )
        .order_by(Message.id.desc())
    )
    stopped = await _stopped_replies(session, target)
    return [row for row in rows if row.id not in stopped and _wakes(seat, target, row)]


REPLY_STOPPED = "reply stopped"
NO_REPLY = "no reply"
"""A chat run finished without answering. The platform says so once, and the message is
not answered again unasked (INV-24)."""


async def _stopped_replies(session: AsyncSession, target: Channel) -> set[int]:
    """Messages whose reply a person stopped. They are not answered again unasked."""
    lines = await session.scalars(
        select(Message).where(
            Message.channel_id == target.id,
            Message.author_kind == Author.PLATFORM,
            Message.reply_to.is_not(None),
        )
    )
    return {
        line.reply_to
        for line in lines
        if line.reply_to is not None
        and (line.detail or {}).get("kind") in (REPLY_STOPPED, NO_REPLY)
    }


async def stop_reply(session: AsyncSession, seat: Seat, now: datetime) -> None:
    """CHAT-4: when a person stops a reply, the messages it was answering are marked, so
    the same reply does not start again by itself. A new message is answered as usual."""
    for message in await unanswered_from_people(session, seat):
        await platform_line(
            session,
            seat.project_id,
            "This reply was stopped. Send a new message to ask again.",
            now,
            reply_to=message.id,
            detail={"kind": REPLY_STOPPED},
        )


async def message_count(session: AsyncSession, project_id: str) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Message).where(Message.project_id == project_id)
        )
        or 0
    )
