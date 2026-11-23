"""Attacks on connections: needs, holds and the start check (CON-5, PRJ-1, LLM-6, 7.18)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select

from crewmind.catalog.refusal import Refusal
from crewmind.domain.connections import holds, needs
from crewmind.domain.connections.needs import NEED_MACHINE, NeedState
from crewmind.domain.execution import runs
from crewmind.domain.execution.model import RunKind
from crewmind.storage.models import Event, Project, ProjectNeed, Run, Seat
from tests.attack.harness import assert_refused
from tests.support import Actor, App, quiet_start

BLOG_WRITER = "Marketing Blog Writer"


async def blog_project(app: App, owner: Actor) -> str:
    """A project with a CEO and one blog writer, whose role needs the wordpress secret."""
    project = await app.project(owner)
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="Desk", role=BLOG_WRITER, members=1
    )
    return project


async def seats(app: App, project: str) -> dict[str, Seat]:
    async with app.runtime.sessions() as session:
        rows = await session.scalars(select(Seat).where(Seat.project_id == project))
        return {row.name: row for row in rows}


async def need_rows(app: App, project: str) -> dict[str, ProjectNeed]:
    async with app.runtime.sessions() as session:
        rows = await session.scalars(select(ProjectNeed).where(ProjectNeed.project_id == project))
        return {row.name: row for row in rows}


@pytest.mark.attack("CON-5")
@pytest.mark.attack("7.18")
async def test_CON_5_a_seat_never_runs_while_its_role_needs_something_missing(app: App) -> None:
    """CON-5, PRJ-1, EXE-4, INV-21: start names what is missing and who needs it. Started
    without it, exactly the seats that need it are held, with the reason on the seat; the
    others work. A run queued for a held seat by any path is never leased. When the role
    leaves the roster, the need is dropped and nothing is held; every change is recorded."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)

    refused = await app.call("projects.start", owner, project_id=project)
    assert_refused(refused, rule="CON-5", code="start_blocked")
    said = refused.json()["message"]
    assert "wordpress" in said
    assert "blog-writer" in said
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "draft"

    await app.ok("projects.start", owner, project_id=project, without_missing=True)
    await quiet_start(app, project)
    found = await seats(app, project)
    writer = next(seat for name, seat in found.items() if name != "CEO" and seat.kind != "reviewer")
    assert (writer.state, writer.held_for) == ("paused", ["secret:wordpress"])
    assert writer.pause_reason is not None
    assert "wordpress" in writer.pause_reason
    assert found["CEO"].state == "active"
    assert (await need_rows(app, project))["wordpress"].state == NeedState.WAIVED

    # An attacker who queues a run for the held seat directly gets no lease and no tokens.
    async with app.runtime.sessions() as session, session.begin():
        held = await session.get(Seat, writer.id)
        assert held is not None
        await runs.queue(session, held, RunKind.WORK, ["forced"], app.runtime.clock())
    await app.work()
    async with app.runtime.sessions() as session:
        states = list(await session.scalars(select(Run.state).where(Run.seat_id == writer.id)))
    assert "leased" not in states
    assert "running" not in states
    assert "finished" not in states

    # The periodic job keeps the hold; standing the team down drops the need and the hold.
    await app.work_jobs.keep_work_moving()
    assert (await seats(app, project))[writer.name].state == "paused"
    await app.ok("roster.stand_down_team", owner, project_id=project, team="Desk")
    await app.work_jobs.keep_work_moving()
    assert (await need_rows(app, project))["wordpress"].state == NeedState.DROPPED
    async with app.runtime.sessions() as session:
        changes = list(
            await session.scalars(
                select(Event).where(Event.type == "need.state_changed").order_by(Event.id)
            )
        )
    assert [(change.after or {}).get("state") for change in changes] == [
        "open",
        "waived",
        "dropped",
    ]


@pytest.mark.attack("CON-5")
async def test_CON_5_a_need_met_releases_the_seats_it_held(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CON-5: once a need is met, its seats go back to work by themselves, and only seats
    the platform held are released: a seat paused for another reason stays paused."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    await app.ok("projects.start", owner, project_id=project, without_missing=True)
    writer = next(s for n, s in (await seats(app, project)).items() if n != "CEO" and s.held_for)

    async def met(*_: Any) -> bool:
        return True

    monkeypatch.setattr(needs, "meets", [met])
    await app.work_jobs.keep_work_moving()
    released = (await seats(app, project))[writer.name]
    assert (released.state, released.held_for, released.pause_reason) == ("active", [], None)
    assert (await need_rows(app, project))["wordpress"].state == NeedState.MET

    async with app.runtime.sessions() as session, session.begin():
        row = await session.get(Seat, writer.id)
        assert row is not None
        row.state, row.pause_reason = "paused", "Paused by hand for this test."
    monkeypatch.setattr(needs, "meets", [])
    async with app.runtime.sessions() as session, session.begin():
        held_project = await session.get(Project, project)
        assert held_project is not None
        await holds.apply(session, held_project, app.runtime.clock())
    kept = (await seats(app, project))[writer.name]
    assert (kept.state, kept.pause_reason) == ("paused", "Paused by hand for this test.")


@given(path=st.lists(st.sampled_from(sorted(NEED_MACHINE.states - {"(new)"})), max_size=10))
def test_7_18_a_need_moves_only_by_listed_transitions(path: list[str]) -> None:
    """7.18: any sequence of needs states either follows the table or is refused."""
    state = "open"
    for target in path:
        if target == state:
            continue
        if NEED_MACHINE.allows(state, target):
            state = target
        else:
            with pytest.raises(Refusal):
                NEED_MACHINE.check(state, target)


@pytest.mark.attack("CON-5")
async def test_CON_5_readiness_lists_what_is_missing_without_changing_anything(app: App) -> None:
    """CON-5, PRJ-1: readiness shows what start would refuse on, and who would wait, and
    writes nothing: no need row, no event, no hold."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    async with app.runtime.sessions() as session:
        before = len(list(await session.scalars(select(Event.id))))

    found = await app.ok("projects.readiness", owner, project_id=project)
    assert found["ready"] is False
    [item] = found["waiting"]
    assert "wordpress" in item["text"]
    assert len(item["seats"]) == 1

    assert await need_rows(app, project) == {}
    async with app.runtime.sessions() as session:
        assert len(list(await session.scalars(select(Event.id)))) == before
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "draft"
    stranger = await app.person("stranger@example.com")
    assert (await app.call("projects.readiness", stranger, project_id=project)).status_code in (
        403,
        404,
    )
