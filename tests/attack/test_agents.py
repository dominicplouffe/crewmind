"""Attacks an agent would try through the agent API (P3, INV-4, EXE-10, INV-23, MSG-1, MSG-2)."""

from __future__ import annotations

import pytest

from crewmind.catalog import Surface, catalog
from crewmind.catalog.surfaces import exposed_on
from tests.attack.harness import assert_refused
from tests.support import App, agent_call, live_run, run_state, running_project, wake


@pytest.mark.attack("P3")
async def test_P3_a_run_token_works_only_for_its_own_live_run(app: App) -> None:
    """P3, INV-4: the token names one run, one agent and one project. It is useless on the
    human API, without a run, when forged, and after the run ends."""
    owner = await app.person("owner@example.com")
    first = await running_project(app, owner)
    second = await running_project(app, owner)
    run = await live_run(app, first)
    other = await live_run(app, second)

    me = (await agent_call(app, run.token, "agent.whoami")).json()
    assert me["run_id"] == run.run_id
    assert me["project"] == "Atlas"
    assert (await agent_call(app, other.token, "agent.whoami")).json()["run_id"] == other.run_id

    for credential in (None, "cm_run_forged", owner.token):
        assert (await agent_call(app, credential, "agent.whoami")).status_code == 401
    for name in ("auth.whoami", "projects.list"):
        assert (await app.call(name, run.token)).status_code == 401
    stolen = await app.call("projects.status", run.token, project_id=second)
    assert stolen.status_code == 401

    from crewmind.domain.execution import runs

    async with app.runtime.sessions() as session, session.begin():
        await runs.finish(session, run.run_id, run.runner_id, app.runtime.clock(), failed=False)
    assert (await agent_call(app, run.token, "agent.whoami")).status_code == 401
    assert (await agent_call(app, other.token, "agent.whoami")).status_code == 200


@pytest.mark.attack("P3")
@pytest.mark.attack("7.7")
async def test_INV_4_a_hold_revokes_work_run_tokens_at_once(app: App) -> None:
    """INV-4, EXE-9, INV-20, section 7.7: holding the project kills its live work runs and
    their tokens. A killed run cannot be finished afterwards."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    run = await live_run(app, project)
    await app.ok("projects.hold", owner, project_id=project)
    assert await run_state(app, run.run_id) == "killed"
    assert (await agent_call(app, run.token, "agent.whoami")).status_code == 401

    from crewmind.domain.execution import runs

    async with app.runtime.sessions() as session, session.begin():
        alive = await runs.heartbeat(session, run.run_id, run.runner_id, app.runtime.clock())
        finished = await runs.finish(
            session, run.run_id, run.runner_id, app.runtime.clock(), failed=False
        )
    assert (alive, finished) == (False, False)
    assert await run_state(app, run.run_id) == "killed"


@pytest.mark.attack("EXE-10")
async def test_EXE_10_the_refusal_cap_ends_the_run_and_revokes_its_token(app: App) -> None:
    """EXE-10: at `refusal.cap` refusals the run is terminated and the final refusal says
    so. Rephrasing does not help: every refusal counts, whatever was tried."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"refusal.cap": 3})
    run = await live_run(app, project)
    attempts = [
        ("agent.post_message", {"body": "hi", "channel": "team nowhere"}),
        ("agent.hire_team", {"team": "a", "role": "No such role"}),
        ("agent.post_message", {"body": "", "channel": "project chat"}),
    ]
    last = None
    for name, values in attempts:
        last = await agent_call(app, run.token, name, **values)
        assert last.status_code == 403
    assert last is not None
    envelope = assert_refused(last, rule="EXE-10")
    assert "refusal 3 of 3" in envelope.message
    assert "Rephrasing is not a strategy" in envelope.message
    assert await run_state(app, run.run_id) == "terminated"
    assert (await agent_call(app, run.token, "agent.whoami")).status_code == 401
    trace = await app.ok("runs.trace", owner, project_id=project, run_id=run.run_id)
    refused = [step for step in trace["steps"] if step.get("outcome", {}).get("code")]
    assert len(refused) == 3


@pytest.mark.attack("INV-23")
async def test_INV_23_a_chat_run_changes_no_state(app: App) -> None:
    """INV-23, CHAT-6, P15: a chat message is talk. The chat run it starts can post a reply
    but cannot hire, stand down or recall a team."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script(
        "CEO/chat",
        {
            "tools": [
                {"name": "agent_hire_team", "arguments": {"team": "ops", "role": "Generalist"}}
            ]
        },
        {"text": "I cannot do that from chat. Shall I propose it?\nNeed from you: yes or no."},
    )
    await app.ok("chat.send", owner, project_id=project, body="Hire an ops team right now.")
    await app.work()
    roster = await app.ok("roster.show", owner, project_id=project)
    assert roster["teams"] == []
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert (
        history[-1]["body"]
        == "I cannot do that from chat. Shall I propose it?\nNeed from you: yes or no."
    )
    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    trace = await app.ok("runs.trace", owner, project_id=project, run_id=runs[0]["run_id"])
    refusal = next(s for s in trace["steps"] if s.get("tool") == "agent.hire_team")
    assert refusal["outcome"]["rule"] == "INV-23"


@pytest.mark.attack("EXE-1")
@pytest.mark.attack("7.12-team")
@pytest.mark.attack("7.12-seat")
async def test_EXE_1_the_roster_is_one_ceo_plus_teams_within_the_limit(app: App) -> None:
    """EXE-1, section 7.12, IF-3.2: only the CEO hires; no second CEO; `teams.max` holds for
    the CEO and the chairman alike; a team is stood down and recalled only as listed."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"teams.max": 2})
    ceo = await live_run(app, project)
    hired = await agent_call(
        app, ceo.token, "agent.hire_team", team="research", role="Generalist", members=2
    )
    assert hired.status_code == 200, hired.text
    seats = {seat["name"]: seat for seat in hired.json()["seats"]}
    assert seats["research-1"]["lead"] is True
    assert seats["research-2"]["lead"] is False
    assert_refused(
        await agent_call(app, ceo.token, "agent.hire_team", team="bosses", role="CEO"),
        rule="EXE-1",
        code="second_ceo",
    )
    assert_refused(
        await agent_call(app, ceo.token, "agent.hire_team", team="research", role="Generalist"),
        rule="EXE-1",
        code="team_exists",
    )
    await app.ok("roster.hire_team", owner, project_id=project, team="review", role="Reviewer")
    for attempt in (
        await agent_call(app, ceo.token, "agent.hire_team", team="third", role="Generalist"),
        await app.call(
            "roster.hire_team", owner, project_id=project, team="third", role="Generalist"
        ),
    ):
        envelope = assert_refused(attempt, rule="EXE-1", code="too_many_teams")
        assert "2 active teams and `teams.max` is 2" in envelope.message

    worker = await live_run(app, project, seat="research-1")
    not_ceo = await agent_call(app, worker.token, "agent.hire_team", team="x", role="Generalist")
    assert_refused(not_ceo, rule="IF-3.2", code="ceo_only")
    busy = await app.call("roster.stand_down_team", owner, project_id=project, team="research")
    assert_refused(busy, rule="EXE-1", code="team_holds_work")

    down = await app.ok("roster.stand_down_team", owner, project_id=project, team="review")
    assert next(s for s in down["seats"] if s["name"] == "review")["state"] == "stood down"
    assert_refused(
        await app.call("roster.stand_down_team", owner, project_id=project, team="review"),
        rule="7.12-team",
    )
    await app.ok("roster.recall_team", owner, project_id=project, team="review")
    assert_refused(
        await app.call("roster.recall_team", owner, project_id=project, team="review"),
        rule="7.12-team",
    )
    from crewmind.catalog.refusal import Refusal
    from crewmind.domain.execution.model import SEAT_MACHINE

    with pytest.raises(Refusal) as refused:
        SEAT_MACHINE.check("stood down", "paused")
    assert refused.value.envelope.rule == "7.12-seat"


@pytest.mark.attack("MSG-1")
@pytest.mark.attack("MSG-2")
async def test_MSG_2_only_the_ceo_speaks_unaddressed_in_the_project_chat(app: App) -> None:
    """MSG-1, MSG-2: a worker cannot post in the project chat unless addressed, cannot post
    in a channel that is not its own, and cannot talk to an empty room. People post only
    in the project chat."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("roster.hire_team", owner, project_id=project, team="research", role="Generalist")
    worker = await live_run(app, project, seat="research")

    unasked = await agent_call(app, worker.token, "agent.post_message", body="Hello, chairman!")
    assert_refused(unasked, rule="MSG-2", code="not_addressed")
    foreign = await agent_call(
        app, worker.token, "agent.post_message", body="Hello", channel="no such room"
    )
    assert_refused(foreign, rule="MSG-1", code="not_your_channel")
    alone = await agent_call(
        app, worker.token, "agent.post_message", body="Anyone here?", channel="team research"
    )
    assert_refused(alone, rule="MSG-1", code="empty_room")
    too_long = await agent_call(
        app, worker.token, "agent.post_message", body="x" * 20_001, channel="leadership"
    )
    assert_refused(too_long, rule="MSG-1", code="message_length")

    asked = await app.ok(
        "chat.send", owner, project_id=project, body="@research what did you find?"
    )
    answer = await agent_call(app, worker.token, "agent.post_message", body="Three sources so far.")
    assert answer.status_code == 200, answer.text
    assert answer.json()["reply_to"] == asked["id"]

    ceo = await live_run(app, project)
    assert (
        await agent_call(app, ceo.token, "agent.post_message", body="Status: on track.")
    ).status_code == 200
    history = await app.ok("chat.history", owner, project_id=project, channel="leadership")
    assert history["items"] == []
    no_room = await app.call("chat.history", owner, project_id=project, channel="nowhere")
    assert no_room.status_code == 404
    await wake(app, project)


def test_IF_6_1_every_agent_operation_is_only_on_the_agent_api(app: App) -> None:
    """IF-6.1, P3: agent operations have no route on the human API, the CLI or MCP."""
    agent_operations = [o for o in catalog if exposed_on(o, Surface.AGENT_API)]
    assert len(agent_operations) >= 8
    for operation in agent_operations:
        for surface in (Surface.API, Surface.CLI, Surface.MCP, Surface.SLACK):
            assert not exposed_on(operation, surface), operation.name
