"""Attacks on chat sessions (MSG-11, section 7.17, P8)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.conversation.sessions import CHAT_SESSION_MACHINE, SessionState
from nightsquad.storage.models import ChatSession
from tests.conftest import FakeClock
from tests.support import Actor, App, running_project


async def chat_session(app: App) -> ChatSession:
    async with app.runtime.sessions() as session:
        rows = list(await session.scalars(select(ChatSession).order_by(ChatSession.id)))
    return rows[-1]


async def ask(app: App, owner: Actor, project: str, body: str) -> int:
    await app.ok("chat.send", owner, project_id=project, body=body)
    return await app.work()


@pytest.mark.attack("7.17-chat-session")
async def test_MSG_11_a_session_holds_many_runs_and_closes_when_idle(
    app: App, clock: FakeClock
) -> None:
    """MSG-11, section 7.17, P8: the first message opens a session; later replies are new
    chat runs in the same session; it closes after `chat.keep_warm` with no message and the
    next message opens a new one. A closed session cannot be warmed again."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"text": "First answer."})
    assert await ask(app, owner, project, "One?") == 1
    first = await chat_session(app)
    assert (first.state, first.generation) == ("warm", 1)

    clock.advance(minutes=5)
    assert await ask(app, owner, project, "Two?") == 1
    same = await chat_session(app)
    assert same.id == first.id
    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert [run["kind"] for run in runs] == ["chat", "chat"]

    clock.advance(minutes=11)
    await app.scheduler.tick()
    closed = await chat_session(app)
    assert (closed.id, closed.state) == (first.id, "closed")
    with pytest.raises(Refusal):
        CHAT_SESSION_MACHINE.check(SessionState.CLOSED, SessionState.WARM)

    assert await ask(app, owner, project, "Three?") == 1
    assert (await chat_session(app)).id != first.id


async def test_MSG_11_a_session_restarts_when_what_the_agent_runs_on_changes(app: App) -> None:
    """MSG-11: a new standing order changes what every reply must follow, so the session
    moves to a new generation and a warm process is replaced. Nothing else restarts it."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"text": "An answer."})
    await ask(app, owner, project, "One?")
    await ask(app, owner, project, "Two?")
    assert (await chat_session(app)).generation == 1

    await app.ok("orders.pin", owner, project_id=project, what="Answer in one sentence.")
    await ask(app, owner, project, "Three?")
    restarted = await chat_session(app)
    assert (restarted.state, restarted.generation, restarted.restarts) == ("warm", 2, [])


async def test_MSG_11_a_failing_chat_is_held_and_stops_costing(app: App, clock: FakeClock) -> None:
    """MSG-11, P8, EXE-4: three involuntary restarts in ten minutes hold the session. The
    chairman is told why, no more runs start for the same message, and the next message
    after the hold warms it again."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"fail": "the provider is down"})
    await app.ok("chat.send", owner, project_id=project, body="Are you there?")
    for _ in range(3):
        await app.work()
        clock.advance(seconds=100)
    held = await chat_session(app)
    assert held.state == "held"
    assert len(held.restarts) == 3
    history: list[dict[str, Any]] = (await app.ok("chat.history", owner, project_id=project))[
        "items"
    ]
    notice = next(m for m in history if m["detail"] == {"kind": "chat session held"})
    assert "failed 3 times in 10 minutes" in notice["body"]
    spent = (await app.ok("budget.show", owner, project_id=project))["spent"]

    clock.advance(minutes=3)
    assert await app.work() == 0
    assert (await app.ok("budget.show", owner, project_id=project))["spent"] == spent

    app.script("CEO/chat", {"text": "Back now."})
    assert await ask(app, owner, project, "And now?") == 1
    warm = await chat_session(app)
    assert (warm.id, warm.state, warm.restarts) == (held.id, "warm", [])
