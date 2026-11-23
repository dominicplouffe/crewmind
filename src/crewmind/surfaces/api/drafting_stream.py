"""The live stream of one drafting conversation: its lines as they are stored, and the
Founder's words as the model produces them (FND-1, IF-3.6). It holds no rules; `founder
show` tells a client the same, later."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from crewmind.catalog.caller import Caller, CallerKind
from crewmind.catalog.execute import Executor, unauthenticated
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.accounts.credentials import Authenticator
from crewmind.live import StreamHub
from crewmind.storage.models import Drafting, DraftingMessage
from crewmind.surfaces.api.app import SESSION_COOKIE
from crewmind.surfaces.api.stream import KEEPALIVE_SECONDS, POLL_SECONDS, STREAM_PREFIX, sse


def topic(drafting_id: str) -> str:
    return f"drafting:{drafting_id}"


def live_event(told: dict[str, Any]) -> str:
    """The Founder's words as it writes them (`reply`), or what it is doing while it
    works (`working`). Both are live only: neither is stored (FND-1, P17)."""
    return sse("working" if "working" in told else "reply", told)


async def drafting_stream(
    executor: Executor,
    hub: StreamHub,
    drafting_id: str,
    *,
    after_line: int = 0,
    stop: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    """`line` events are stored lines and carry ids to resume from; `reply` events are
    the Founder's words, live only; `state` says the conversation changed."""
    queue = hub.subscribe(topic(drafting_id))
    idle, seen = 0.0, ""
    try:
        while stop is None or not stop.is_set():
            stored: list[str] = []
            async with executor.sessions() as session:
                rows = await session.scalars(
                    select(DraftingMessage)
                    .where(
                        DraftingMessage.drafting_id == drafting_id,
                        DraftingMessage.id > after_line,
                    )
                    .order_by(DraftingMessage.id)
                )
                for row in rows:
                    after_line = row.id
                    data = {
                        "id": row.id,
                        "author": row.author,
                        "body": row.body,
                        "detail": row.detail,
                        "at": row.at.isoformat(),
                    }
                    stored.append(sse("line", data, f"l{row.id}"))
                drafting = await session.get(Drafting, drafting_id)
                now = f"{drafting.state}/{drafting.turn}/{drafting.updated_at}" if drafting else ""
                if now != seen:
                    seen = now
                    stored.append(sse("state", {"state": drafting.state if drafting else "gone"}))
            while not queue.empty():
                yield live_event(queue.get_nowait())
            for line in stored:
                yield line
            try:
                live = await asyncio.wait_for(queue.get(), timeout=POLL_SECONDS)
            except TimeoutError:
                idle = 0.0 if stored else idle + POLL_SECONDS
                if idle >= KEEPALIVE_SECONDS:
                    idle = 0.0
                    yield ": keep-alive\n\n"
                continue
            yield live_event(live)
    finally:
        hub.unsubscribe(topic(drafting_id), queue)


def add_drafting_stream_route(
    app: FastAPI, executor: Executor, authenticator: Authenticator, hub: StreamHub
) -> None:
    async def stream(drafting_id: str, request: Request, after_line: int = 0) -> StreamingResponse:
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else None
        caller: Caller = await authenticator.authenticate(
            token or request.cookies.get(SESSION_COOKIE)
        )
        if caller.kind is not CallerKind.PERSON:
            raise unauthenticated()
        async with executor.sessions() as session:
            drafting = await session.get(Drafting, drafting_id)
            if drafting is None or drafting.person_id != caller.actor_id:
                raise Refusal(
                    "drafting_not_found",
                    "There is no such drafting conversation.",
                    kind=RefusalKind.NOT_FOUND,
                )
        return StreamingResponse(
            drafting_stream(executor, hub, drafting_id, after_line=after_line),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.add_api_route(f"{STREAM_PREFIX}/draftings/{{drafting_id}}", stream, methods=["GET"])
