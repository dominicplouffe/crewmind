"""Chaos on leasing and liveness: racing runners, killed runners, late results
(INV-12, INV-13, INV-15, EXE-5, EXE-7, EXE-8, GOV-7)."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from crewmind.domain.execution import runs
from crewmind.storage.models import Notice, Run
from tests.conftest import FakeClock
from tests.support import App, live_run, run_state, running_project, wake


async def all_runs(app: App, project: str) -> list[Run]:
    async with app.runtime.sessions() as session:
        rows = await session.scalars(
            select(Run).where(Run.project_id == project).order_by(Run.queued_at, Run.attempt)
        )
        return list(rows)


async def test_INV_12_racing_runners_never_take_the_same_run(app: App) -> None:
    """INV-12, EXE-5: with many runners leasing at once, each run is leased exactly once
    and is never both queued and running."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"run.concurrency": 16, "teams.max": 2})
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="crew", role="Generalist", members=8
    )
    for seat in ["CEO", *[f"crew-{n}" for n in range(1, 9)]]:
        await wake(app, project, seat=seat)
    await app.dispatcher.tick()

    async def lease(runner: str) -> list[str]:
        async with app.runtime.sessions() as session, session.begin():
            leased = await runs.lease(session, app.runtime.settings, runner, 3, app.runtime.clock())
        return [item.run_id for item in leased]

    taken = await asyncio.gather(*(lease(f"runner-{n}") for n in range(6)), return_exceptions=True)
    ids = [run_id for result in taken if isinstance(result, list) for run_id in result]
    assert len(ids) == len(set(ids))
    rows = await all_runs(app, project)
    assert len(rows) == 9
    assert sorted(ids) == sorted(run.id for run in rows if run.state == "leased")
    for run in rows:
        assert (run.state == "leased") == (run.leased_by is not None)


async def test_INV_13_one_work_run_per_agent_and_no_lease_past_the_concurrency_limit(
    app: App,
) -> None:
    """INV-13, EXE-3, GOV-7: an agent has at most one queued or running work run; nothing
    is leased while the project is at `run.concurrency`; lowering the limit kills nothing."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"run.concurrency": 2})
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="crew", role="Generalist", members=3
    )
    for seat in ("CEO", "crew-1", "crew-2", "crew-3"):
        await wake(app, project, seat=seat)
        await wake(app, project, seat=seat, kind="second notice")
    await app.dispatcher.tick()
    await app.dispatcher.tick()
    assert len(await all_runs(app, project)) == 4

    async def lease() -> int:
        async with app.runtime.sessions() as session, session.begin():
            return len(
                await runs.lease(session, app.runtime.settings, "r", 10, app.runtime.clock())
            )

    assert await lease() == 2
    assert await lease() == 0
    await app.ok(
        "settings.change_project", owner, project_id=project,
        changes={"run.concurrency": 1}, reason="Slow down for now.",
    )  # fmt: skip
    assert await lease() == 0
    states = sorted(run.state for run in await all_runs(app, project))
    assert states == ["leased", "leased", "queued", "queued"]


async def test_EXE_7_a_killed_runner_is_reaped_and_its_late_result_changes_nothing(
    app: App, clock: FakeClock
) -> None:
    """EXE-7, EXE-8, INV-15: when a runner dies mid-run, the run is reaped after the lease
    runs out, its notices are given back, and a retry is queued with a backoff. A late
    finish from the dead worker changes nothing."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO", {"text": "thinking", "tools": [{"name": "agent_whoami"}]}, {"text": "done"})
    zombie = await live_run(app, project)
    clock.advance(seconds=80)
    await app.scheduler.tick()
    assert await run_state(app, zombie.run_id) == "running"
    clock.advance(seconds=15)
    await app.scheduler.tick()
    assert await run_state(app, zombie.run_id) == "reaped"

    async with app.runtime.sessions() as session, session.begin():
        late = await runs.finish(session, zombie.run_id, zombie.runner_id, clock.now, failed=False)
        beat = await runs.heartbeat(session, zombie.run_id, zombie.runner_id, clock.now)
    assert (late, beat) == (False, False)
    assert await run_state(app, zombie.run_id) == "reaped"

    first, retry = await all_runs(app, project)
    assert (retry.state, retry.attempt, retry.wake_id) == ("queued", 2, first.wake_id)
    assert retry.not_before is not None
    assert (retry.not_before - clock.now).total_seconds() == 30
    async with app.runtime.sessions() as session:
        notices = list(await session.scalars(select(Notice).where(Notice.project_id == project)))
    assert [notice.state for notice in notices] == ["pending"]

    runner = app.runner()
    assert await runner.step() == 0
    clock.advance(seconds=31)
    assert await runner.step() == 1
    await runner.idle()
    assert await run_state(app, retry.id) == "finished"
    async with app.runtime.sessions() as session:
        notices = list(await session.scalars(select(Notice).where(Notice.project_id == project)))
    assert [notice.state for notice in notices] == ["consumed"]


async def test_EXE_8_a_run_is_retried_three_times_then_given_up_in_the_open(
    app: App, clock: FakeClock
) -> None:
    """EXE-8, P17: a failing run gets 3 attempts with a growing backoff and counts as one
    wake. Then the platform says so in the chat; it does not retry for ever."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO", {"fail": "the provider returned an error"})
    await wake(app, project)
    await app.dispatcher.tick()
    runner = app.runner()
    for _ in range(5):
        await runner.step()
        await runner.idle()
        clock.advance(seconds=100)
        await app.dispatcher.tick()
    rows = await all_runs(app, project)
    assert [(run.attempt, run.state) for run in rows] == [
        (1, "failed"),
        (2, "failed"),
        (3, "failed"),
    ]
    assert len({run.wake_id for run in rows}) == 1
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert "failed 3 times and was given up" in history[-1]["body"]


async def test_runner_crash_mid_run_breaks_no_execution_invariant(
    app: App, clock: FakeClock
) -> None:
    """Phase 2 exit: killing a runner mid-run violates none of INV-8, INV-12, INV-13 and
    INV-15. Another runner finishes the work after the reap."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script(
        "CEO", {"text": "step one", "tools": [{"name": "agent_whoami"}]}, {"text": "finished"}
    )
    await wake(app, project)
    await app.dispatcher.tick()
    doomed = app.runner(heartbeat_seconds=30)
    assert await doomed.step() == 1
    await asyncio.sleep(0.05)
    await doomed.crash()

    survivor = app.runner()
    assert await survivor.step() == 0
    clock.advance(seconds=100)
    await app.scheduler.tick()
    clock.advance(seconds=40)
    assert await survivor.step() == 1
    await survivor.idle()
    rows = await all_runs(app, project)
    assert [(run.attempt, run.state) for run in rows] == [(1, "reaped"), (2, "finished")]
    assert rows[0].leased_by != rows[1].leased_by
    budget = await app.ok("budget.show", owner, project_id=project)
    assert budget["spent"] > 0


async def test_EXE_5_a_task_cancelled_mid_query_does_not_keep_the_write_lock(app: App) -> None:
    """EXE-5, NFR-9: on SQLite every transaction takes the write lock. A task cancelled at
    any point inside a transaction (a killed runner, a dropped live stream) must release
    it at once, or every other transaction stalls. Cancelled at many different moments,
    the next transaction always starts promptly. On Postgres this passes trivially."""
    from sqlalchemy import text

    sessions = app.runtime.sessions
    # A query with many rows, so a cancellation can land while its statement is unfinished.
    many_rows = (
        "WITH RECURSIVE counted(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM counted "
        "WHERE n < 2000) SELECT n FROM counted"
    )

    cancel_step_seconds = 0.0002  # spreads the cancellations across a transaction

    async def reader() -> None:
        async with sessions() as session, session.begin():
            for _ in range(50):
                await session.execute(text(many_rows))

    async def next_transaction() -> None:
        async with sessions() as session, session.begin():
            await session.execute(text("SELECT 1"))

    await app.person("owner@example.com")
    for moment in range(60):
        task = asyncio.create_task(reader())
        await asyncio.sleep(moment * cancel_step_seconds)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.wait_for(next_transaction(), 2)
