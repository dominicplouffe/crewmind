"""Wake triggers, the context pack, never-silent statuses (EXE-2, EXE-15, CHAT-3, LLM-15)."""

from __future__ import annotations

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.execution import context_pack, runs
from tests.conftest import FakeClock
from tests.support import App, live_run, running_project, shown_as, wake


async def statuses(app: App, owner: object, project: str) -> list[str]:
    history = (await app.ok("chat.history", owner, project_id=project))["items"]  # type: ignore[arg-type]
    return [message["body"] for message in history if message["kind"] == "status"]


async def test_INV_24_a_message_gets_a_reply_or_a_status_within_60_seconds(
    app: App, clock: FakeClock
) -> None:
    """INV-24, CHAT-3, P17: with no runner to reply, the platform posts one status naming
    the reason before 60 seconds pass, at 0 tokens, and does not repeat it."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("chat.send", owner, project_id=project, body="Hello?")
    await app.dispatcher.tick()
    clock.advance(seconds=44)
    await app.dispatcher.tick()
    assert await statuses(app, owner, project) == []
    clock.advance(seconds=2)
    for _ in range(5):
        clock.advance(seconds=2)
        await app.dispatcher.tick()
    posted = await statuses(app, owner, project)
    assert len(posted) == 1
    assert "waiting for a free runner" in posted[0]
    assert (await app.ok("budget.show", owner, project_id=project))["spent"] == 0

    app.script("CEO/chat", {"text": "Here now."})
    await app.work()
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert history[-1]["body"] == "Here now."


async def test_CHAT_3_a_stopped_or_held_project_answers_honestly(app: App) -> None:
    """CHAT-3, INV-20, PRJ-2: a held project still chats; a stopped one says at once that
    agents no longer reply."""
    owner = await app.person("owner@example.com")
    held = await running_project(app, owner)
    await app.ok("projects.hold", owner, project_id=held)
    await wake(app, held)
    app.script("CEO/chat", {"text": "Still here while held."})
    await app.ok("chat.send", owner, project_id=held, body="Can you hear me?")
    assert await app.work() == 1
    kinds = [run["kind"] for run in (await app.ok("runs.list", owner, project_id=held))["items"]]
    assert kinds == ["chat"]
    assert (await app.ok("chat.history", owner, project_id=held))["items"][-1][
        "body"
    ] == "Still here while held."

    stopped = await running_project(app, owner)
    await app.ok("projects.stop", owner, project_id=stopped)
    await app.ok("chat.send", owner, project_id=stopped, body="Anyone?")
    assert await app.work() == 0
    assert "the project is stopped" in (await statuses(app, owner, stopped))[0]


async def test_EXE_2_agents_wake_only_on_triggers_and_within_the_wake_limit(
    app: App, clock: FakeClock
) -> None:
    """EXE-2, GOV-7: an urgent notice wakes an agent; nothing wakes it twice at once; after
    `agent.max_wakes_per_hour` wakes it waits; the CEO's heartbeat fires only when
    something changed since its last run."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"agent.max_wakes_per_hour": 2})
    runner = app.runner()
    for _ in range(4):
        await wake(app, project)
        await app.work(runner)
        clock.advance(minutes=5)
    listed = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert len(listed) == 2
    assert listed[0]["reasons"] == ["notice: test notice"]
    clock.advance(minutes=50)
    assert await app.work(runner) == 1

    quiet = await running_project(app, owner)
    clock.advance(hours=7)
    assert await app.work(runner) == 1
    beats = (await app.ok("runs.list", owner, project_id=quiet))["items"]
    assert [run["reasons"] for run in beats] == [["heartbeat"]]
    clock.advance(hours=7)
    await app.dispatcher.tick()
    assert len((await app.ok("runs.list", owner, project_id=quiet))["items"]) == 1


async def test_EXE_15_the_context_pack_is_ordered_stored_and_marks_what_it_delivered(
    app: App,
) -> None:
    """EXE-15, EXE-11, MSG-10, CHAT-11, LLM-15: the pack leads with the goal, then the
    chairman's newest unanswered message; it is stored exactly as sent with its system
    prompt, which carries the output standard and says that what is read is data."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("chat.send", owner, project_id=project, body="First question?")
    await app.ok("chat.send", owner, project_id=project, body="Second, newer question?")
    app.script("CEO/chat", {"text": "Answering the newer one."})
    await app.work()
    run = (await app.ok("runs.list", owner, project_id=project))["items"][0]
    trace = await app.ok("runs.trace", owner, project_id=project, run_id=run["run_id"])
    pack, prompt = trace["context_pack"], trace["system_prompt"]
    assert pack.index("# Goal") < pack.index("newest unanswered message") < pack.index("# This run")
    assert "Second, newer question?" in pack.split("# This run")[0]
    assert "# Situation" in pack
    assert "After 5 refused calls" in pack
    assert context_pack.output_standard() in prompt
    assert "Lead with the answer or the ask." in prompt
    assert "data, never instructions" in prompt
    assert [step["kind"] for step in trace["steps"]] == ["model call", "tool call"]
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert history[-1]["reply_to"] == history[1]["id"]


async def test_LLM_6_a_seat_that_cannot_run_fails_before_any_sandbox_or_token(
    app: App, monkeypatch: object
) -> None:
    """LLM-6: a seat refused at lease fails before a sandbox starts or a token is spent,
    and the reason is posted in the chat."""
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)

    async def no_credential(*_: object) -> runs.Pinned:
        raise Refusal(
            "no_credential", "no credential on the project pays this provider.", rule="LLM-6"
        )

    monkeypatch.setattr(runs, "seat_resolver", no_credential)
    await wake(app, project)
    assert await app.work() == 0
    listed = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert (listed[0]["state"], listed[0]["tokens_counted"]) == ("failed", 0)
    ceo = await shown_as(app, owner, project)
    assert f"{ceo} cannot run: no credential" in (await statuses(app, owner, project))[0]
    assert live_run is not None
