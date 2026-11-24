"""Chaos: the server recovers after every pooled database connection drops (NFR-9)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from nightsquad.jobs.scheduler import Scheduler
from nightsquad.storage.engine import Database
from tests.conftest import FakeClock
from tests.support import App


async def drop_every_connection(app: App) -> None:
    """Kill the pool's connections from under it, as a database restart or a network cut would."""
    if app.runtime.config.database is Database.POSTGRES:
        async with app.runtime.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        admin = app.runtime.engine.execution_options(isolation_level="AUTOCOMMIT")
        async with admin.connect() as connection:
            with pytest.raises(Exception):  # noqa: B017, PT011 - the killer dies with the rest
                await connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = current_database()"
                    )
                )
    else:
        await app.runtime.engine.dispose()


async def test_NFR_9_the_api_and_the_scheduler_recover_after_connections_drop(
    app: App, clock: FakeClock
) -> None:
    """NFR-9: after every pooled connection is dropped, the next API call and the next
    scheduler tick succeed without a restart."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    await app.ok("projects.start", owner, project_id=project)
    scheduler = Scheduler(app.runtime.sessions, clock)
    for _ in range(3):
        await drop_every_connection(app)
        assert (await app.ok("projects.status", owner, project_id=project))["state"] == "running"
        await drop_every_connection(app)
        assert await scheduler.tick() == []
        await drop_every_connection(app)
        await app.ok("projects.hold", owner, project_id=project)
        await app.ok("projects.resume", owner, project_id=project)
