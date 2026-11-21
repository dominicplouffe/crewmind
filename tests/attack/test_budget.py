"""Attacks on the token budget (GOV-2, GOV-3, GOV-6, INV-8, INV-9, INV-11)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from crewmind.storage.models import LedgerLine, Run
from tests.attack.harness import assert_refused
from tests.conftest import FakeClock
from tests.support import App, agent_call, live_run, run_state, running_project, wake

BIG = {"input": 500_000, "output": 100_000, "cache_read": 2_000_000}


async def ledger(app: App, project: str) -> list[LedgerLine]:
    async with app.runtime.sessions() as session:
        rows = await session.scalars(
            select(LedgerLine).where(LedgerLine.project_id == project).order_by(LedgerLine.id)
        )
        return list(rows)


async def complete(app: App, token: str) -> tuple[int, dict[str, object]]:
    body = {"system": "s", "messages": [{"role": "user", "content": "go"}], "tools": []}
    async with app.client() as client:
        response = await client.post(
            "/gateway/v1/complete", json=body, headers={"Authorization": f"Bearer {token}"}
        )
    return response.status_code, response.json()


@pytest.mark.attack("GOV-3")
async def test_GOV_3_at_the_wall_the_project_pauses_and_nothing_new_starts(
    app: App, clock: FakeClock
) -> None:
    """GOV-2, GOV-3, INV-9, PRJ-2: only non-cached tokens count. At the wall the project
    pauses, in-flight runs finish, nothing new is leased (chat included), chat gets a status
    card, `/resume` is refused with the arithmetic, and a budget raise lifts the wall."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"budget.tokens": 1_000_000})
    app.script(
        "CEO",
        {"text": "working", "tools": [{"name": "agent_whoami"}], "usage": BIG},
        {"text": "more", "usage": BIG},
    )
    await wake(app, project)
    assert await app.work() == 1

    budget = await app.ok("budget.show", owner, project_id=project)
    assert budget["spent"] == 1_200_000
    assert budget["by_kind"]["cache_read"] == 4_000_000
    assert budget["at_wall"] is True
    status = await app.ok("projects.status", owner, project_id=project)
    assert status["state"] == "paused"
    assert [hold["reason"] for hold in status["holds"]] == ["budget_wall"]
    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert [run["state"] for run in runs] == ["finished"]
    assert runs[0]["tokens_counted"] == 1_200_000

    asked = await app.ok("chat.send", owner, project_id=project, body="How is it going?")
    await wake(app, project)
    assert await app.work() == 0
    await app.dispatcher.tick()
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    cards = [m for m in history if m["reply_to"] == asked["id"]]
    assert len(cards) == 1
    assert cards[0]["kind"] == "status"
    assert "budget wall (1,200,000 of 1,000,000 tokens used" in cards[0]["body"]
    assert len(await ledger(app, project)) == 2

    refused = await app.call("projects.resume", owner, project_id=project)
    envelope = assert_refused(refused, rule="PRJ-2", code="at_budget_wall")
    assert "1200000 tokens spent of a wall of 1000000" in envelope.message

    await app.ok(
        "settings.change_project",
        owner,
        project_id=project,
        changes={"budget.tokens": 5_000_000},
        reason="Raise the budget to finish.",
    )
    await app.scheduler.tick()
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "running"
    app.script("CEO/chat", {"text": "Back on it."})
    await app.work()
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert history[-1]["body"] == "Back on it."
    assert history[-1]["reply_to"] == asked["id"]


@pytest.mark.attack("GOV-3")
async def test_INV_9_spend_past_the_wall_is_bounded_by_the_runs_in_flight(app: App) -> None:
    """INV-9, GOV-3: with several runs in flight when the wall is crossed, each may finish,
    but nothing new is leased, so the overspend is at most those runs' own calls."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"budget.tokens": 1_000_000})
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="crew", role="Generalist", members=3
    )
    in_flight = [await live_run(app, project, seat=seat) for seat in ("CEO", "crew-1", "crew-2")]
    app.script("*", {"text": "x", "usage": {"input": 400_000, "output": 0}})
    for run in in_flight:
        code, _ = await complete(app, run.token)
        assert code == 200
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "paused"
    for run in in_flight:
        assert await run_state(app, run.run_id) == "running"
        assert (await agent_call(app, run.token, "agent.whoami")).status_code == 200

    await wake(app, project, seat="crew-3")
    await app.dispatcher.tick()
    assert await app.runner().step() == 0
    spent = (await app.ok("budget.show", owner, project_id=project))["spent"]
    assert spent == 1_200_000
    assert spent - 1_000_000 <= len(in_flight) * 400_000


@pytest.mark.attack("GOV-6")
async def test_GOV_6_the_gateway_refuses_calls_past_the_per_run_cap(app: App) -> None:
    """GOV-6, LLM-9: the gateway warns at 80% of `run.max_tokens` and refuses the next call
    at the cap. The harness cannot talk its way past it, and every call made is metered."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"run.max_tokens": 100_000})
    run = await live_run(app, project)
    app.script("*", *[{"text": "x", "usage": {"input": 30_000, "output": 10_000}}] * 5)
    warnings: list[object] = []
    for _ in range(3):
        code, body = await complete(app, run.token)
        assert code == 200
        warnings.append(body["warning"])
    assert warnings[0] is None
    assert warnings[1] is not None
    assert "80,000 of its 100,000 token cap" in str(warnings[1])
    for _ in range(2):
        code, body = await complete(app, run.token)
        assert code == 403
        assert body["rule"] == "GOV-6"
        assert "120,000 tokens and its cap is 100,000" in str(body["message"])
    assert len(await ledger(app, project)) == 3


async def test_INV_8_every_model_call_is_metered_whatever_the_runs_ending(
    app: App, clock: FakeClock
) -> None:
    """INV-8, P9: calls made by runs that are then killed, reaped or failed stay on the
    ledger, attributed to run, seat, provider and model."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="crew", role="Generalist", members=2
    )
    app.script(
        "*",
        {
            "text": "x",
            "usage": {"input": 1_000, "output": 200, "cache_write": 50, "cache_read": 9_000},
        },
    )
    killed, reaped, failed = [
        await live_run(app, project, seat=s) for s in ("CEO", "crew-1", "crew-2")
    ]
    for run in (killed, reaped, failed):
        assert (await complete(app, run.token))[0] == 200

    from crewmind.domain.execution import runs

    async with app.runtime.sessions() as session, session.begin():
        await runs.finish(session, failed.run_id, failed.runner_id, clock.now, failed=True)
    clock.advance(seconds=120)
    await app.scheduler.tick()
    await app.ok("projects.hold", owner, project_id=project)
    states = {await run_state(app, run.run_id) for run in (killed, reaped, failed)}
    assert states <= {"killed", "reaped", "failed"}
    assert "failed" in states
    assert "reaped" in states

    lines = await ledger(app, project)
    assert {line.run_id for line in lines} == {killed.run_id, reaped.run_id, failed.run_id}
    for line in lines:
        assert (line.input_tokens, line.output_tokens) == (1_000, 200)
        assert (line.cache_write_tokens, line.cache_read_tokens) == (50, 9_000)
        assert line.counted == 1_250
        assert (line.provider, line.model, line.unit) == ("mock", "mock-1", "tokens")
        assert line.seat_id is not None


async def test_INV_11_an_idle_project_spends_nothing(app: App, clock: FakeClock) -> None:
    """INV-11, P8, NFR-16: with no wake trigger and no message, many dispatcher and
    scheduler ticks start no run and make no model call. The CEO's first heartbeat after
    the start is a trigger; once it has run and nothing has changed, none follows."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    runner = app.runner()
    for _ in range(3):
        clock.advance(minutes=30)
        await app.dispatcher.tick()
        assert await runner.step() == 0
    clock.advance(hours=6)
    app.script("CEO", {"text": "Nothing to do.", "usage": {"input": 0, "output": 0}})
    assert await app.work(runner) == 1
    for _ in range(40):
        clock.advance(minutes=30)
        await app.dispatcher.tick()
        await app.scheduler.tick()
        assert await runner.step() == 0
    async with app.runtime.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Run)) == 1
    assert len(await ledger(app, project)) == 1
    assert (await app.ok("budget.show", owner, project_id=project))["spent"] == 0
