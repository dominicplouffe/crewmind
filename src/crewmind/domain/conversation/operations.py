"""The project chat, for people (CHAT-1, CHAT-2, MSG-1, MSG-13, IF-3.8)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Select, select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.pagination import PageRequest, fetch_page
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.accounts.people import person_or_refuse
from crewmind.domain.conversation import service
from crewmind.domain.conversation.service import MSG_1, Author
from crewmind.domain.projects.operations import ProjectRef
from crewmind.storage.events import event_type
from crewmind.storage.models import Channel, Message, Seat, Team

MESSAGE_POSTED = event_type("message.posted", "A message was posted (MSG-1).")
_MENTION = re.compile(r"@([\w][\w-]*)")


class SendInput(ProjectRef):
    body: str = Field(description="The message. `@name` addresses an agent, `@team` its lead.")
    reply_to: int | None = Field(None, description="The message this replies to.")


class MessageItem(BaseModel):
    id: int
    channel: str
    author_kind: str = Field(description="person, agent or platform.")
    author: str
    kind: str = Field(description="message, or status for a platform line.")
    body: str
    reply_to: int | None
    thread_id: int | None
    run_id: str | None
    detail: dict[str, Any] | None
    at: datetime


class HistoryInput(ProjectRef, PageRequest):
    channel: str = Field(service.PROJECT_CHAT, description="The channel to read.")
    thread_id: int | None = Field(None, description="Only this thread.")
    before: int | None = Field(None, description="Only messages older than this message id.")


class History(BaseModel):
    items: list[MessageItem]
    next: str | None = None
    earlier: int | None = Field(
        default=None, description="Pass as `before` to read older messages. Absent at the start."
    )


class ChannelList(BaseModel):
    items: list[str]


def item(message: Message, channel_name: str) -> MessageItem:
    return MessageItem(
        id=message.id,
        channel=channel_name,
        author_kind=message.author_kind,
        author=message.author_name,
        kind=message.kind,
        body=message.body,
        reply_to=message.reply_to,
        thread_id=message.thread_id,
        run_id=message.run_id,
        detail=message.detail,
        at=message.created_at,
    )


async def addressed_seats(context: Context, project_id: str, body: str) -> list[str]:
    """CHAT-2: `@name` addresses that agent; `@team` addresses the team's lead."""
    names = {name.lower() for name in _MENTION.findall(body)}
    if not names:
        return []
    seats = list(await context.session.scalars(select(Seat).where(Seat.project_id == project_id)))
    teams = {
        team.id: team.name.lower()
        for team in await context.session.scalars(select(Team).where(Team.project_id == project_id))
    }
    found: list[str] = []
    for seat in seats:
        leads_named_team = seat.is_lead and teams.get(seat.team_id or "") in names
        if seat.name.lower() in names or leads_named_team:
            found.append(seat.id)
    return found


@operation(
    "chat.send",
    summary="Send a message in the project chat. It goes to the CEO unless you @mention an agent.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def send(context: Context, payload: SendInput) -> MessageItem:
    """MSG-1, CHAT-2, P15: people post only in the project chat. A message is conversation,
    not a command: it changes nothing but the chat."""
    person = await person_or_refuse(context.session, context.caller.actor_id)
    target = await service.channel(context.session, payload.project_id, service.PROJECT_CHAT)
    message = await service.post(
        context.session,
        target,
        author=Author.PERSON,
        author_id=person.id,
        author_name=person.name,
        body=payload.body,
        now=context.now,
        reply_to=payload.reply_to,
        addressed=await addressed_seats(context, payload.project_id, payload.body),
    )
    context.record(
        MESSAGE_POSTED,
        subject=("message", str(message.id)),
        project_id=payload.project_id,
        after={"channel": target.name, "author": person.id},
    )
    return item(message, target.name)


@operation(
    "chat.history",
    summary="Read a channel's messages. People can read every channel.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def history(context: Context, payload: HistoryInput) -> History:
    """MSG-1: people read every channel but post only in the project chat."""
    target = await context.session.scalar(
        select(Channel).where(
            Channel.project_id == payload.project_id, Channel.name == payload.channel
        )
    )
    if target is None:
        raise Refusal(
            "channel_not_found",
            f"There is no channel named {payload.channel}.",
            kind=RefusalKind.NOT_FOUND,
            rule=MSG_1.id,
            hint="List the channels with `crewmind chat channels`.",
        )
    statement = select(Message).where(Message.channel_id == target.id)
    if payload.thread_id is not None:
        statement = statement.where(
            (Message.thread_id == payload.thread_id) | (Message.id == payload.thread_id)
        )
    if payload.after is not None:
        rows, cursor = await fetch_page(
            context.session, statement, payload, key=Message.id, at=Message.created_at
        )
        return History(items=[item(row, target.name) for row in rows], next=cursor)
    return await _newest(context, statement, payload, target.name)


async def _newest(
    context: Context, statement: Select[Message], payload: HistoryInput, channel: str
) -> History:
    """CHAT-2: without a cursor, a chat opens at its newest messages, oldest of them first.
    `earlier` pages back through the rest."""
    if payload.before is not None:
        statement = statement.where(Message.id < payload.before)
    if payload.since is not None:
        statement = statement.where(Message.created_at >= payload.since)
    if payload.until is not None:
        statement = statement.where(Message.created_at < payload.until)
    found = await context.session.scalars(
        statement.order_by(Message.id.desc()).limit(payload.limit + 1)
    )
    rows = list(found)
    more = len(rows) > payload.limit
    rows = rows[: payload.limit][::-1]
    return History(
        items=[item(row, channel) for row in rows],
        earlier=rows[0].id if more and rows else None,
    )


@operation(
    "chat.channels",
    summary="List a project's channels.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def channels(context: Context, payload: ProjectRef) -> ChannelList:
    rows = await context.session.scalars(
        select(Channel.name).where(Channel.project_id == payload.project_id).order_by(Channel.name)
    )
    return ChannelList(items=list(rows))
