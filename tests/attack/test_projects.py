"""Attacks on the project lifecycle (section 7.1, PRJ-1, PRJ-2, PRJ-10)."""

from __future__ import annotations

import pytest

from crewmind.catalog.caller import platform_job
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.model import PROJECT_MACHINE, Hold
from crewmind.jobs.scheduler import Scheduler
from crewmind.storage.models import Project
from tests.attack.harness import assert_refused
from tests.conftest import FakeClock
from tests.support import Actor, App

WALL = platform_job("test: budget wall")
LIFECYCLE = {
    "projects.start": "running",
    "projects.hold": "held",
    "projects.resume": "running",
    "projects.stop": "stopped",
    "projects.cancel_delete": None,
}


async def add_platform_hold(app: App, project_id: str, hold: Hold, **detail: int) -> None:
    """Add a platform hold reason the way a later phase's job will."""
    async with app.runtime.sessions() as session, session.begin():
        project = await session.get(Project, project_id)
        assert project is not None
        await lifecycle.add_hold(
            session, project, hold, caller=WALL, now=app.runtime.clock(), detail=detail or None
        )


async def lift_platform_hold(app: App, project_id: str, hold: Hold) -> None:
    async with app.runtime.sessions() as session, session.begin():
        project = await session.get(Project, project_id)
        assert project is not None
        await lifecycle.lift_holds(
            session,
            project,
            frozenset({hold}),
            caller=WALL,
            now=app.runtime.clock(),
            cause="test",
        )


async def delete(app: App, owner: Actor, project: str, name: str = "Atlas") -> None:
    code = (await app.ok("projects.delete", owner, project_id=project))["confirmation"]
    await app.ok("projects.confirm_delete", owner, project_id=project, confirmation=code, name=name)


async def in_state(app: App, owner: Actor, state: str) -> str:
    project = await app.project(owner)
    if state in ("running", "held", "paused", "stopped"):
        await app.ok("projects.start", owner, project_id=project)
    if state == "held":
        await app.ok("projects.hold", owner, project_id=project)
    if state == "paused":
        await add_platform_hold(app, project, Hold.SKIPPED_CYCLES)
    if state == "stopped":
        await app.ok("projects.stop", owner, project_id=project)
    if state == "deleting":
        await delete(app, owner, project)
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == state
    return project


@pytest.mark.attack("7.1")
@pytest.mark.attack("PRJ-1")
@pytest.mark.parametrize("state", ["draft", "running", "held", "paused", "stopped", "deleting"])
async def test_7_1_a_project_changes_state_only_as_listed(app: App, state: str) -> None:
    """Section 7.1, PRJ-1: from every state, each lifecycle operation either makes a listed
    transition or is refused. Start is refused for anything but a draft."""
    owner = await app.person("owner@example.com")
    for name, target in LIFECYCLE.items():
        project = await in_state(app, owner, state)
        response = await app.call(name, owner, project_id=project)
        after = (await app.ok("projects.status", owner, project_id=project))["state"]
        if response.status_code == 200:
            assert after == state or PROJECT_MACHINE.allows(state, after), (name, state, after)
        else:
            assert response.status_code == 403, response.text
            assert response.json()["rule"] in ("7.1", "PRJ-1", "PRJ-2"), response.text
            assert after == state, name
        if name == "projects.start":
            assert (response.status_code == 200) == (state == "draft")
        if target == "stopped" and response.status_code == 200:
            assert after == "stopped"


@pytest.mark.attack("PRJ-2")
@pytest.mark.attack("7.1")
async def test_PRJ_2_resume_is_refused_at_the_budget_wall_with_the_arithmetic(app: App) -> None:
    """PRJ-2, GOV-9, section 7.1: `/resume` cannot lift the budget wall. The refusal gives
    the numbers and what does lift it. Each hold reason lifts by its own trigger."""
    owner = await app.person("owner@example.com")
    project = await in_state(app, owner, "held")
    await add_platform_hold(app, project, Hold.BUDGET_WALL, spent=20_100_000, wall=20_000_000)
    status = await app.ok("projects.status", owner, project_id=project)
    assert status["state"] == "paused"
    assert {hold["reason"] for hold in status["holds"]} == {"chairman", "budget_wall"}

    refused = await app.call("projects.resume", owner, project_id=project)
    envelope = assert_refused(refused, rule="PRJ-2", code="at_budget_wall")
    assert "20100000 tokens spent of a wall of 20000000" in envelope.message
    assert "budget raise" in (envelope.hint or "")
    unchanged = await app.ok("projects.status", owner, project_id=project)
    assert {hold["reason"] for hold in unchanged["holds"]} == {"chairman", "budget_wall"}

    await lift_platform_hold(app, project, Hold.BUDGET_WALL)
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "held"
    resumed = await app.ok("projects.resume", owner, project_id=project)
    assert resumed["state"] == "running"
    assert resumed["holds"] == []

    await add_platform_hold(app, project, Hold.AUTH_FAILURES)
    failing = await app.call("projects.resume", owner, project_id=project)
    assert_refused(failing, rule="PRJ-2", code="credential_failing")


@pytest.mark.attack("PRJ-2")
async def test_PRJ_2_a_hold_cannot_be_doubled_or_set_in_the_past(
    app: App, clock: FakeClock
) -> None:
    """PRJ-2: a second chairman hold and a resume time in the past are refused."""
    owner = await app.person("owner@example.com")
    project = await in_state(app, owner, "held")
    assert_refused(
        await app.call("projects.hold", owner, project_id=project),
        rule="PRJ-2",
        code="already_held",
    )
    await app.ok("projects.resume", owner, project_id=project)
    past = (clock.now).isoformat()
    assert_refused(
        await app.call("projects.hold", owner, project_id=project, until=past),
        rule="PRJ-2",
        code="lift_time_past",
    )
    assert_refused(
        await app.call("projects.resume", owner, project_id=project), rule="7.1", code="not_held"
    )


@pytest.mark.attack("PRJ-10")
async def test_PRJ_10_deleting_takes_two_steps_and_waits_for_the_grace_period(
    app: App, clock: FakeClock
) -> None:
    """PRJ-10: no one-step delete, no delete of a running project, no reused or wrong code,
    no purge before `delete.grace`, and a cancel restores the prior state."""
    owner = await app.person("owner@example.com")
    running = await in_state(app, owner, "running")
    assert_refused(await app.call("projects.delete", owner, project_id=running), rule="7.1")

    project = await in_state(app, owner, "stopped")
    guess = await app.call(
        "projects.confirm_delete", owner, project_id=project, confirmation="guess", name="Atlas"
    )
    assert_refused(guess, rule="PRJ-10", code="delete_not_confirmed")
    code = (await app.ok("projects.delete", owner, project_id=project))["confirmation"]
    wrong_name = await app.call(
        "projects.confirm_delete", owner, project_id=project, confirmation=code, name="atlas"
    )
    assert_refused(wrong_name, rule="PRJ-10")
    await app.ok(
        "projects.confirm_delete", owner, project_id=project, confirmation=code, name="Atlas"
    )
    again = await app.call(
        "projects.confirm_delete", owner, project_id=project, confirmation=code, name="Atlas"
    )
    assert again.status_code == 403

    scheduler = Scheduler(app.runtime.sessions, clock)
    clock.advance(days=6, hours=23)
    await scheduler.tick()
    owner = await app.login(owner.email)
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "deleting"
    restored = await app.ok("projects.cancel_delete", owner, project_id=project)
    assert restored["state"] == "stopped"
    assert restored["delete_at"] is None

    await delete(app, owner, project)
    clock.advance(days=7, minutes=1)
    await scheduler.tick()
    owner = await app.login(owner.email)
    assert (await app.call("projects.status", owner, project_id=project)).status_code == 404
