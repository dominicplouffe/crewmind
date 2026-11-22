"""The live event stream (IF-3.6, CHAT-3, CHAT-4)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from crewmind.surfaces.api.stream import project_stream
from tests.attack.harness import assert_refused
from tests.support import App, live_run, run_state, running_project


def parse(raw: str) -> tuple[str, dict[str, Any]]:
    lines = dict(line.split(": ", 1) for line in raw.strip().splitlines() if ": " in line)
    return lines["event"], json.loads(lines["data"])


Seen = list[tuple[str, dict[str, Any]]]


async def collect(app: App, project: str, until: int | str, **cursors: int) -> Seen:
    """Read the stream until `until` events have arrived, or a message with that body."""
    stop = asyncio.Event()
    seen: Seen = []
    stream = project_stream(app.runtime.executor, app.runtime.hub, project, stop=stop, **cursors)
    async for raw in stream:
        if raw.startswith(":"):
            continue
        kind, data = parse(raw)
        seen.append((kind, data))
        arrived = kind == "message" and data["body"] == until
        if arrived or (isinstance(until, int) and len(seen) >= until):
            stop.set()
    return seen


async def test_IF_3_6_the_stream_carries_messages_changes_and_the_words_of_a_reply(
    app: App,
) -> None:
    """IF-3.6, CHAT-3: a client sees the chairman's message, the words of the reply as they
    are produced, then the stored reply, and the state changes around them. The streamed
    words add up to the reply."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"text": "The plan is ready and costs little."})
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    events = (await app.ok("record.list", owner, project_id=project, limit=200))["items"]
    after = {"after_message": len(history), "after_event": events[-1]["id"]}

    async def talk() -> None:
        await asyncio.sleep(0.1)
        await app.ok("chat.send", owner, project_id=project, body="Is the plan ready?")
        await app.work()

    talking = asyncio.create_task(talk())
    reply = "The plan is ready and costs little."
    seen = await asyncio.wait_for(collect(app, project, reply, **after), timeout=20)
    await talking
    kinds = [kind for kind, _ in seen]
    messages = [data for kind, data in seen if kind == "message"]
    words = [data["text"] for kind, data in seen if kind == "reply"]
    assert [m["body"] for m in messages] == [
        "Is the plan ready?",
        "The plan is ready and costs little.",
    ]
    assert "".join(words) == "The plan is ready and costs little."
    assert len(words) == 7
    assert kinds.index("reply") < len(kinds) - 1 - kinds[::-1].index("message")
    assert {data["type"] for kind, data in seen if kind == "change"} == {
        "run.state_changed",
        "chat_session.state_changed",
    }
    assert len([kind for kind in kinds if kind == "change"]) >= 3
    assert all(data["seat"] == "CEO" for kind, data in seen if kind == "reply")


async def test_IF_3_6_a_client_resumes_from_where_it_stopped_and_polling_still_works(
    app: App,
) -> None:
    """IF-3.6: with the ids of the last message and change it saw, a client gets only what
    is newer. Everything on the stream is also in the read operations."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    for body in ("one", "two", "three"):
        await app.ok("chat.send", owner, project_id=project, body=body)
    everything = await asyncio.wait_for(collect(app, project, 3, after_event=10**9), timeout=10)
    assert [data["body"] for _, data in everything] == ["one", "two", "three"]
    second = everything[1][1]["id"]
    rest = await asyncio.wait_for(
        collect(app, project, 1, after_message=second, after_event=10**9), timeout=10
    )
    assert [data["body"] for _, data in rest] == ["three"]
    polled = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert [m["body"] for m in polled] == ["one", "two", "three"]


async def test_CHAT_4_a_reply_in_progress_can_be_interrupted(app: App) -> None:
    """CHAT-4, EXE-9: interrupting kills the run and revokes its token. Only a chair may."""
    owner = await app.person("owner@example.com")
    observer = await app.person("observer@example.com")
    project = await running_project(app, owner)
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")
    run = await live_run(app, project)
    refused = await app.call("runs.interrupt", observer, project_id=project, run_id=run.run_id)
    assert_refused(refused, rule="ACC-5")
    done = await app.ok("runs.interrupt", owner, project_id=project, run_id=run.run_id)
    assert done["state"] == "killed"
    assert await run_state(app, run.run_id) == "killed"
    again = await app.call("runs.interrupt", owner, project_id=project, run_id=run.run_id)
    assert_refused(again, rule="7.7")


async def test_CHAT_4_a_stopped_reply_does_not_start_again_by_itself(app: App) -> None:
    """CHAT-4, P8: after a person stops a reply, no new run starts for the same message,
    so no more tokens are spent on it. The chat says the reply was stopped, and the next
    message is answered as usual."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    asked = await app.ok("chat.send", owner, project_id=project, body="Write a long plan.")
    await app.dispatcher.tick()
    (run,) = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert run["kind"] == "chat"
    await app.ok("runs.interrupt", owner, project_id=project, run_id=run["run_id"])

    assert await app.work() == 0
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    (note,) = [m for m in history if m["kind"] == "status"]
    assert note["reply_to"] == asked["id"]
    assert "stopped" in note["body"]

    await app.ok("chat.send", owner, project_id=project, body="A short one, please.")
    assert await app.work() == 1
