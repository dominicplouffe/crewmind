"""The scheduler and its jobs (BG-1, BG-3, BG-4, section 7.1, 7.9, 7.10, PRJ-10)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.jobs import scheduler as jobs
from nightsquad.jobs.scheduler import Scheduler
from nightsquad.storage.models import Event, Project
from tests.attack.test_projects import delete
from tests.conftest import FakeClock
from tests.support import App


async def event_count(app: App) -> int:
    async with app.runtime.sessions() as session:
        return await session.scalar(select(func.count()).select_from(Event)) or 0


async def test_7_1_a_hold_lifts_at_its_resume_time_and_names_the_job(
    app: App, clock: FakeClock
) -> None:
    """Section 7.1, PRJ-2, BG-4: at the resume time the platform lifts the hold, and the
    events name the job as their actor."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    await app.ok("projects.start", owner, project_id=project)
    until = clock.now + timedelta(hours=48)
    held = await app.ok("projects.hold", owner, project_id=project, until=until.isoformat())
    assert held["holds"][0]["lifts_at"] is not None
    scheduler = Scheduler(app.runtime.sessions, clock)

    clock.advance(hours=47)
    await scheduler.tick()
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "held"
    clock.advance(hours=2)
    await scheduler.tick()
    status = await app.ok("projects.status", owner, project_id=project)
    assert status["state"] == "running"
    assert status["holds"] == []

    automatic = (await app.events(owner, project))[-2:]
    assert [event["type"] for event in automatic] == [
        "project.hold_lifted",
        "project.state_changed",
    ]
    for event in automatic:
        assert event["actor_kind"] == "platform"
        assert event["actor"] == "scheduler: resume times"
        assert event["via"] == "platform"
    assert automatic[1]["before"] == {"state": "held"}
    assert automatic[1]["after"] == {"state": "running"}


async def test_BG_3_every_job_is_safe_to_run_twice(app: App, clock: FakeClock) -> None:
    """BG-3: a second tick with nothing new due changes nothing and writes no event."""
    owner = await app.person("owner@example.com")
    held = await app.project(owner, name="Held")
    await app.ok("projects.start", owner, project_id=held)
    await app.ok(
        "projects.hold", owner, project_id=held, until=(clock.now + timedelta(hours=1)).isoformat()
    )
    doomed = await app.project(owner, name="Doomed")
    await delete(app, owner, doomed, name="Doomed")
    await app.ok("tokens.mint", owner, name="short", expires_in_days=1)
    await app.ok("people.invite", await app.admin(), email="late@example.com", name="Late")
    scheduler = Scheduler(app.runtime.sessions, clock)

    clock.advance(days=8)
    assert await scheduler.tick() == []
    after_first = await event_count(app)
    assert await scheduler.tick() == []
    assert await scheduler.tick() == []
    assert await event_count(app) == after_first

    record = await app.ok("record.list_install", await app.admin(), limit=200)
    by_type = {event["type"]: event for event in record["items"]}
    for expected in ("project.purged", "token.expired", "link.expired", "session.expired"):
        assert by_type[expected]["actor_kind"] == "platform", expected
    assert by_type["project.purged"]["subject_id"] == doomed
    assert by_type["project.purged"]["actor"] == "scheduler: purge deleted projects"


async def test_PRJ_10_a_purge_removes_everything_the_project_owned(
    app: App, clock: FakeClock
) -> None:
    """PRJ-10, NFR-15: after `delete.grace`, the project, its members, settings and events
    are gone. One install event records the purge, with the project's id only."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner, name="Secret plan")
    await delete(app, owner, project, name="Secret plan")
    clock.advance(days=7, seconds=1)
    await Scheduler(app.runtime.sessions, clock).tick()
    async with app.runtime.sessions() as session:
        for table in ("events", "memberships", "project_hold_reasons", "projects"):
            column = "id" if table == "projects" else "project_id"
            rows = await session.execute(
                __import__("sqlalchemy").text(f"SELECT count(*) FROM {table} WHERE {column} = :p"),
                {"p": project},
            )
            assert rows.scalar_one() == 0, table
        settings = await session.execute(
            __import__("sqlalchemy").text(
                "SELECT count(*) FROM setting_values WHERE subject_id = :p"
            ),
            {"p": project},
        )
        assert settings.scalar_one() == 0
        purged = (await session.scalars(select(Event).where(Event.type == "project.purged"))).one()
    assert purged.project_id is None
    assert "Secret plan" not in str(vars(purged))


async def test_BG_1_one_broken_project_does_not_stall_the_others(
    app: App, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BG-1: each project runs in its own transaction. A job that fails for one project
    rolls back only that project; the rest are processed in the same tick."""
    owner = await app.person("owner@example.com")
    until = (clock.now + timedelta(hours=1)).isoformat()
    projects: list[str] = []
    for name in ("One", "Two", "Three"):
        project = await app.project(owner, name=name)
        await app.ok("projects.start", owner, project_id=project)
        await app.ok("projects.hold", owner, project_id=project, until=until)
        projects.append(project)
    broken = sorted(projects)[0]

    async def failing(session: AsyncSession, project: Project, now: datetime) -> None:
        if project.id == broken:
            raise RuntimeError("this project is broken")

    monkeypatch.setattr(
        Scheduler, "project_jobs", (jobs.lift_due_holds, failing, jobs.purge_deleted)
    )
    clock.advance(hours=2)
    assert await Scheduler(app.runtime.sessions, clock).tick() == [broken]
    states = {
        project: (await app.ok("projects.status", owner, project_id=project))["state"]
        for project in projects
    }
    assert states == {p: ("held" if p == broken else "running") for p in projects}
