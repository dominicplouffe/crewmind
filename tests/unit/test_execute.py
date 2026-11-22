"""The shared call path: one transaction, idempotency, pagination (NFR-10, IF-3.5, INV-21)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select

from crewmind.catalog import Catalog, Reversibility
from crewmind.catalog.caller import ANONYMOUS, Authority
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.runtime import Runtime
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Event, Person
from tests.conftest import FakeClock
from tests.support import App

TEST_EVENT = event_type("test.happened", "An event written by a test.")


class Fail(BaseModel):
    fail: bool


class Done(BaseModel):
    done: bool = True


async def test_NFR_10_a_failed_handler_leaves_neither_the_change_nor_its_event(
    runtime: Runtime,
) -> None:
    """NFR-10, INV-21: state and event are written in one transaction, so both exist or
    neither does."""
    source = Catalog()

    @operation(
        "sample.change",
        summary="Change state, then maybe fail.",
        authority=Authority.ANYONE,
        reversibility=Reversibility.REVERSIBLE,
        into=source,
    )
    async def change(context: Context, payload: Fail) -> Done:  # pyright: ignore[reportUnusedFunction]
        context.session.add(
            Person(
                email=f"{payload.fail}@example.com",
                name="x",
                role="member",
                state="invited",
                password_hash=None,
                created_at=context.now,
            )
        )
        context.record(TEST_EVENT, subject=("person", "x"))
        if payload.fail:
            raise RuntimeError("after the change")
        return Done()

    sample = source.get("sample.change")

    async def counts() -> tuple[int, int]:
        async with runtime.sessions() as session:
            people = await session.scalar(select(func.count()).select_from(Person))
            events = await session.scalar(select(func.count()).select_from(Event))
            return people or 0, events or 0

    with pytest.raises(RuntimeError):
        await runtime.executor.execute(sample, ANONYMOUS, Fail(fail=True))
    assert await counts() == (0, 0)
    await runtime.executor.execute(sample, ANONYMOUS, Fail(fail=False))
    assert await counts() == (1, 1)


async def test_INV_21_only_declared_event_types_can_be_written(runtime: Runtime) -> None:
    """INV-21: events are typed. An undeclared type cannot be written."""
    async with runtime.sessions() as session:
        with pytest.raises(ValueError, match="not declared"):
            append_event(
                session, type="made.up", caller=ANONYMOUS, at=runtime.clock(), subject=("x", "y")
            )


async def test_IF_3_5_a_write_with_an_idempotency_key_happens_once(app: App) -> None:
    """IF-3.5: repeating a write with the same key returns the first result and does
    nothing more. Another key, or another person, is a new write."""
    owner = await app.person("owner@example.com")
    other = await app.person("other@example.com")
    body = {"name": "Atlas", "type": "deliver", "goal": "Ship it."}

    async def create(token: str, key: str) -> str:
        async with app.client() as client:
            response = await client.post(
                "/v1/projects/create",
                json=body,
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
            )
        assert response.status_code == 200
        return response.json()["project_id"]

    first = await create(owner.token, "key-1")
    assert await create(owner.token, "key-1") == first
    assert await create(owner.token, "key-2") != first
    assert await create(other.token, "key-1") != first
    assert len((await app.ok("projects.list", owner))["items"]) == 2


async def test_IF_3_5_lists_are_cursor_paginated_and_filter_by_time(
    app: App, clock: FakeClock
) -> None:
    """IF-3.5: a list returns a cursor for the next page, and a time window narrows it."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    await app.ok("projects.start", owner, project_id=project)
    start = clock.now
    for _ in range(3):
        clock.advance(hours=1)
        await app.ok("projects.hold", owner, project_id=project)
        await app.ok("projects.resume", owner, project_id=project)

    seen: list[int] = []
    cursor = None
    while True:
        extra = {"after": cursor} if cursor else {}
        page = await app.ok("record.list", owner, project_id=project, limit=4, **extra)
        assert len(page["items"]) <= 4
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next"]
        if cursor is None:
            break
    everything = await app.events(owner, project)
    assert seen == [item["id"] for item in everything]
    assert seen == sorted(seen)
    assert len(seen) == 18

    window = await app.ok(
        "record.list",
        owner,
        project_id=project,
        since=(start + timedelta(hours=2)).isoformat(),
        until=(start + timedelta(hours=3)).isoformat(),
    )
    assert len(window["items"]) == 4
    assert (await app.call("record.list", owner, project_id=project, limit=201)).status_code == 422
    holds = await app.ok("record.list", owner, project_id=project, type="project.hold_added")
    assert len(holds["items"]) == 3
