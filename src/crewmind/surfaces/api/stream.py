"""The live event stream: server-sent events for a project (IF-3.6, CHAT-3).

It carries new messages and state changes as they are committed, and the words of a chat
reply as the model produces them. It holds no rules: it only tells clients sooner what
the read operations would tell them anyway, so polling still works.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from crewmind.catalog.caller import Authority, Caller, CallerKind
from crewmind.catalog.execute import Executor, unauthenticated
from crewmind.domain.accounts.credentials import Authenticator
from crewmind.domain.conversation.operations import item
from crewmind.domain.projects.access import MembershipAccess
from crewmind.live import StreamHub
from crewmind.storage.models import Channel, Event, Message
from crewmind.surfaces.api.app import SESSION_COOKIE

STREAM_PREFIX = "/stream/v1"
POLL_SECONDS = 0.5
KEEPALIVE_SECONDS = 15


def sse(kind: str, data: dict[str, Any], event_id: str | None = None) -> str:
    lines = [f"event: {kind}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"


async def project_stream(
    executor: Executor,
    hub: StreamHub,
    project_id: str,
    *,
    after_message: int = 0,
    after_event: int = 0,
    stop: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    """Yield server-sent events for one project until `stop` is set or the client leaves.
    `message` and `change` events are stored things and carry ids to resume from;
    `reply` and `activity` events are live only."""
    queue = hub.subscribe(project_id)
    idle = 0.0
    try:
        while stop is None or not stop.is_set():
            sent = False
            async with executor.sessions() as session:
                messages = await session.execute(
                    select(Message, Channel.name)
                    .join(Channel, Channel.id == Message.channel_id)
                    .where(Message.project_id == project_id, Message.id > after_message)
                    .order_by(Message.id)
                )
                for message, channel_name in messages.all():
                    after_message = message.id
                    data = item(message, channel_name).model_dump(mode="json")
                    yield sse("message", data, f"m{message.id}")
                    sent = True
                events = await session.scalars(
                    select(Event)
                    .where(
                        Event.project_id == project_id,
                        Event.id > after_event,
                        Event.type != "message.posted",
                    )
                    .order_by(Event.id)
                )
                for event in events:
                    after_event = event.id
                    data = {"id": event.id, "type": event.type, "at": event.at.isoformat()}
                    yield sse("change", data, f"e{event.id}")
                    sent = True
            try:
                live = await asyncio.wait_for(queue.get(), timeout=POLL_SECONDS)
            except TimeoutError:
                idle = 0.0 if sent else idle + POLL_SECONDS
                if idle >= KEEPALIVE_SECONDS:
                    idle = 0.0
                    yield ": keep-alive\n\n"
                continue
            yield sse(str(live.get("type", "reply")), live)
            while not queue.empty():
                live = queue.get_nowait()
                yield sse(str(live.get("type", "reply")), live)
    finally:
        hub.unsubscribe(project_id, queue)


def add_stream_route(
    app: FastAPI, executor: Executor, authenticator: Authenticator, hub: StreamHub
) -> None:
    access = MembershipAccess()

    async def stream(
        project_id: str, request: Request, after_message: int = 0, after_event: int = 0
    ) -> StreamingResponse:
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else None
        caller: Caller = await authenticator.authenticate(
            token or request.cookies.get(SESSION_COOKIE)
        )
        if caller.kind is not CallerKind.PERSON:
            raise unauthenticated()
        async with executor.sessions() as session:
            await access.resolve(session, caller, project_id, Authority.PROJECT_OBSERVER)
        return StreamingResponse(
            project_stream(
                executor, hub, project_id, after_message=after_message, after_event=after_event
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.add_api_route(f"{STREAM_PREFIX}/projects/{{project_id}}", stream, methods=["GET"])
