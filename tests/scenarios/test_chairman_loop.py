"""The chairman loop (phase 6 exit demo): never left in silence, and the desk, the brief,
since-you-were-away, the agenda and the alerts agree with the event log (INV-24, HUM-10,
HUM-11, HUM-12, CHAT-15, INT-7, INV-22)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from nightsquad.storage.models import BriefRun
from tests.attack.delivery_support import SOLO, command_requirement, meet, set_states, spend
from tests.attack.test_planning import CHAIRMAN_HOLDS, propose
from tests.attack.work_support import Squad
from tests.conftest import FakeClock
from tests.push_support import BROWSER, FakePushService, sender
from tests.support import App, running_project, shown_as, wake


async def ask(app: App, owner: Any, project: str, body: str) -> int:
    sent = await app.ok("chat.send", owner, project_id=project, body=body)
    return sent["id"]


async def answers(app: App, owner: Any, project: str, message: int) -> list[dict[str, Any]]:
    history = (await app.ok("chat.history", owner, project_id=project, limit=200))["items"]
    return [m for m in history if m["reply_to"] == message and m["author_kind"] != "person"]


async def one_minute(app: App, clock: FakeClock) -> None:
    """Let 58 seconds pass, with the platform and one runner working throughout."""
    for _ in range(29):
        clock.advance(seconds=2)
        await app.work()


async def test_INV_24_with_the_provider_down_a_message_still_gets_an_answer(
    app: App, clock: FakeClock
) -> None:
    """Never silent (section 13, INV-24, P17): with the provider down, a chairman message
    gets a reply or a platform status within 60 seconds."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"fail": "The provider is down."})
    asked = await ask(app, owner, project, "Are you there?")
    await one_minute(app, clock)
    assert len(await answers(app, owner, project, asked)) >= 1


async def test_INV_24_at_the_budget_wall_the_platform_answers(app: App, clock: FakeClock) -> None:
    """Never silent (INV-24, GOV-3, CHAT-3): at the budget wall no chat run is leased, and
    the platform answers the message itself, once."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"budget.tokens": 1_000_000})
    await spend(app, project, 1_000_000)
    await app.scheduler.tick()
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "paused"
    asked = await ask(app, owner, project, "Why did you stop?")
    await one_minute(app, clock)
    replies = await answers(app, owner, project, asked)
    assert [reply["author_kind"] for reply in replies] == ["platform"]


async def test_INV_24_a_held_project_still_answers(app: App, clock: FakeClock) -> None:
    """Never silent (INV-24, INV-20, PRJ-2): a held project still chats."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("projects.hold", owner, project_id=project)
    app.script("CEO/chat", {"text": "Held, and still here."})
    asked = await ask(app, owner, project, "Can you still hear me?")
    await one_minute(app, clock)
    replies = await answers(app, owner, project, asked)
    assert [reply["body"] for reply in replies] == ["Held, and still here."]


async def test_INV_24_a_crash_mid_reply_is_followed_by_a_status(app: App, clock: FakeClock) -> None:
    """Never silent (INV-24, EXE-7): the runner dies while the agent is answering, and the
    chairman still gets a reply or a platform status within 60 seconds."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"text": "A very slow answer indeed.", "word_delay_ms": 60_000})
    asked = await ask(app, owner, project, "What is the plan?")
    await app.dispatcher.tick()
    doomed = app.runner(heartbeat_seconds=30)
    assert await doomed.step() == 1
    for _ in range(100):
        await asyncio.sleep(0.02)
        started = (await app.ok("runs.list", owner, project_id=project))["items"]
        if any(run["state"] == "running" for run in started):
            break
    await doomed.crash()
    for _ in range(29):
        clock.advance(seconds=2)
        await app.dispatcher.tick()
        await app.scheduler.tick()
    assert len(await answers(app, owner, project, asked)) >= 1


async def test_INV_24_an_agent_that_answers_with_nothing_is_not_asked_in_a_loop(
    app: App, clock: FakeClock
) -> None:
    """Never silent (INV-24, P8): a chat run that ends with no reply is not queued again
    for the same message. The platform says once that no reply came."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"text": ""})
    asked = await ask(app, owner, project, "Anything to report?")
    await one_minute(app, clock)
    replies = await answers(app, owner, project, asked)
    ceo = await shown_as(app, owner, project)
    assert [reply["body"] for reply in replies] == [
        f"{ceo} ran and gave no reply to this message. Ask again in other words."
    ]
    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert [run["kind"] for run in runs] == ["chat"]


async def test_HUM_11_the_brief_and_the_away_summary_agree_with_the_event_log(
    app: App, clock: FakeClock
) -> None:
    """HUM-11, CHAT-15: the brief is built from the record at 0 tokens. It counts
    requirements settled apart from tasks closed, and what it says moved, what the CEO
    handled and what decided itself are the events of the stretch, counted again here
    from the event log. Opening the chat after `brief.away_after` gives the same."""
    squad = await Squad.start(app, team=False, settings=SOLO)
    await set_states(app, {squad.requirement: "cut"})
    opened = await app.ok("chat.opened", squad.owner, project_id=squad.project)
    assert opened == {"away": False, "summary": None}
    clock.advance(minutes=1)
    spent = (await app.ok("budget.show", squad.owner, project_id=squad.project))["spent"]

    first = await command_requirement(squad, "pricing")
    second = await command_requirement(squad, "signup")
    await meet(squad, clock, first, "pricing")
    await meet(squad, clock, second, "signup")
    mine = await squad.ok(
        "CEO", "agent.propose_requirement", text="An about page is published.",
        test_kind="observable", success_test="A visitor can open the about page.",
        estimate_runs=2,
    )  # fmt: skip
    await squad.ok("CEO", "agent.accept_requirement", requirement_id=mine["requirements"][-1]["id"])
    await squad.ok("CEO", "agent.post_heads_up", text="I added an about page to the scope.")
    clock.advance(hours=5)
    await squad.finish_all()
    squad.owner = await app.login(squad.owner.email)

    events = await app.events(squad.owner, squad.project)
    met = [
        e for e in events
        if e["type"] == "requirement.state_changed" and e["after"]["state"] == "met"
    ]  # fmt: skip
    done = [
        e for e in events if e["type"] == "task.state_changed" and e["after"]["state"] == "done"
    ]
    assert (len(met), len(done)) == (2, 2)
    brief = await app.ok("brief.show", squad.owner)
    (entry,) = brief["projects"]
    sections = entry["sections"]
    assert sections["what moved"][:2] == [
        "2 requirements were settled as met.",
        "2 tasks were closed as done.",
    ]
    assert sections["what the CEO handled itself"] == [
        f"The CEO moved requirement {mine['requirements'][-1]['id']} to accepted.",
        "Heads-up: I added an about page to the scope.",
    ]
    assert sections["what decided itself"] == []
    assert any("heartbeat" in line for line in sections["what happens next"])

    away = await app.ok("chat.opened", squad.owner, project_id=squad.project)
    assert away["away"] is True
    assert away["summary"]["what moved"][:2] == sections["what moved"][:2]
    again = await app.ok("chat.opened", squad.owner, project_id=squad.project)
    assert again["away"] is False
    assert (await app.ok("budget.show", squad.owner, project_id=squad.project))["spent"] == spent


async def test_HUM_11_the_daily_brief_is_built_once_per_local_day(
    app: App,
    clock: FakeClock,
    service: FakePushService,
) -> None:
    """HUM-11, INT-7: at `brief.time` in the person's timezone the platform builds their
    brief, once per local day, and tells them. A person who turned it off gets none."""
    squad = await Squad.start(app, team=False, settings=SOLO)
    await app.ok("push.public_key", squad.owner)
    await app.ok("push.subscribe", squad.owner, **BROWSER)
    quiet = await app.person("quiet@example.com")
    await app.ok("settings.change_mine", quiet, changes={"brief.time": "off"})
    await running_project(app, quiet)

    async def briefs() -> int:
        async with app.runtime.sessions() as session:
            return await session.scalar(select(func.count()).select_from(BriefRun)) or 0

    clock.now = datetime(2026, 11, 21, 7, 30, tzinfo=clock.now.tzinfo)
    assert await app.planning.send_briefs() == 0
    clock.advance(hours=1)
    assert await app.planning.send_briefs() == 1
    assert await app.planning.send_briefs() == 0
    clock.advance(hours=10)
    assert await app.planning.send_briefs() == 0
    clock.advance(hours=14)
    assert await app.planning.send_briefs() == 1
    assert await briefs() == 2
    await sender(app).tick()
    assert "Your daily brief" in [push["title"] for push in service.sent]


@pytest.mark.parametrize("every", [3600, 21_600])
async def test_INV_22_the_agendas_next_wake_is_the_dispatchers(
    app: App, clock: FakeClock, every: int
) -> None:
    """INV-22, HUM-12, R-48: the agenda's next time-based wake is the moment the
    dispatcher wakes the CEO for its heartbeat: not a second before, and exactly then.
    With nothing changed since the CEO last ran, the agenda says the heartbeat will skip."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"heartbeat.every": every})
    app.script("CEO/work", {"text": "Nothing to do."})
    await wake(app, project)
    assert await app.work() == 1
    agenda = await app.ok("agenda.show", owner, project_id=project)
    assert agenda["next_wake"] is None
    assert "It will skip" in agenda["lines"][0]["consequence"]

    await app.ok(
        "requirements.add", owner, project_id=project, text="The site has a home page.",
        test_kind="observable", success_test="A visitor can open the home page.",
    )  # fmt: skip
    app.script("CEO/work", {"text": "Looked at it."})
    assert await app.work() == 1
    ran_at = app.runtime.clock()
    clock.advance(seconds=30)
    await app.ok("plan.set_target", owner, project_id=project, date="2027-01-01T00:00:00Z",
                 source="A wish.")  # fmt: skip
    agenda = await app.ok("agenda.show", owner, project_id=project)
    due = datetime.fromisoformat(agenda["next_wake"])
    assert due == ran_at + timedelta(seconds=every)
    clock.now = due - timedelta(seconds=1)
    assert await app.work() == 0
    clock.now = due
    assert await app.work() == 1
    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert "heartbeat" in max(runs, key=lambda run: run["queued_at"])["reasons"]


async def test_INT_7_the_alert_level_decides_what_is_pushed(
    app: App,
    service: FakePushService,
) -> None:
    """INT-7: with "alarms only" a decision is not pushed; with "decisions and alarms" an
    item that waits on the chairman is, and a heads-up is not; with "everything" both
    are. An alarm is never held back."""
    squad = await Squad.start(app, settings=CHAIRMAN_HOLDS)
    await app.ok("push.public_key", squad.owner)
    await app.ok("push.subscribe", squad.owner, **BROWSER)

    async def pushed(level: str) -> list[str]:
        service.sent.clear()
        await app.ok("settings.change_mine", squad.owner, changes={"alerts.level": level})
        await propose(squad)
        await squad.ok("CEO", "agent.post_heads_up", text="I hired the build team.")
        await sender(app).tick()
        return [push["body"].split(":")[0] for push in service.sent]

    assert await pushed("alarms_only") == []
    assert await pushed("decisions_and_alarms") == ["Proposed scope"]
    assert await pushed("everything") == ["Proposed scope", "Heads-up from the CEO"]
