"""Attacks on the desk (HUM-10)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.attack.harness import assert_refused
from tests.attack.test_planning import CHAIRMAN_HOLDS, propose
from tests.attack.work_support import Squad
from tests.conftest import FakeClock
from tests.support import Actor, App


@pytest.mark.attack("HUM-10")
async def test_HUM_10_the_desk_is_one_list_and_a_snooze_cannot_outlast_a_deadline(
    app: App, clock: FakeClock
) -> None:
    """HUM-10: the desk lists what waits on a person across their projects: here proposed
    scope and an expired bet. A snooze is that person's own, cannot pass the item's
    deadline, and ends by itself. A flag is not on the desk."""
    squad = await Squad.start(app, settings=CHAIRMAN_HOLDS)
    wanted = await propose(squad)
    explore = await Squad.start(app, type="explore", team=False, owner=squad.owner)
    clock.advance(hours=49)
    await squad.finish_all()
    await explore.finish_all()
    await app.planning.tick()
    owner = await app.login(squad.owner.email)

    desk = (await app.ok("desk.show", owner))["waiting"]
    assert sorted((entry["what"], entry["project_id"]) for entry in desk) == sorted(
        [("proposed scope", squad.project), ("expired bet", explore.project)]
    )
    scope = next(entry for entry in desk if entry["what"] == "proposed scope")
    assert scope["title"] == f"Proposed scope: requirement {wanted}, 4 runs"
    item = scope["item"]
    now = app.runtime.clock()
    far = await app.call(
        "items.snooze", owner, project_id=squad.project, item_id=item["id"],
        until=(now + timedelta(days=3)).isoformat(),
    )  # fmt: skip
    assert_refused(far, rule="HUM-10", code="snooze_too_long")
    await app.ok(
        "items.snooze", owner, project_id=squad.project, item_id=item["id"],
        until=(now + timedelta(hours=6)).isoformat(),
    )  # fmt: skip
    kinds = [entry["what"] for entry in (await app.ok("desk.show", owner))["waiting"]]
    assert kinds == ["expired bet"]
    listed = await app.ok("items.list", owner, project_id=squad.project)
    assert item["id"] in [entry["id"] for entry in listed["items"]]
    clock.advance(hours=7)
    kinds = [entry["what"] for entry in (await app.ok("desk.show", owner))["waiting"]]
    assert "proposed scope" in kinds


async def _header_count(app: App, actor: Actor, project: str) -> int:
    return (await app.ok("chat.header", actor, project_id=project))["waiting_on_you"]


async def _desk_count(app: App, actor: Actor, project: str) -> int:
    desk = (await app.ok("desk.show", actor))["waiting"]
    return sum(1 for entry in desk if entry["project_id"] == project)


@pytest.mark.attack("HUM-10")
async def test_HUM_10_CHAT_18_the_header_count_is_the_desk_count(
    app: App, clock: FakeClock
) -> None:
    """HUM-10, CHAT-18: the project header's "waiting on you" is the caller's desk for that
    project, in every state: empty, with proposed scope waiting, after a snooze, for a person
    who does not chair the project, and after the chairman decides. The header once counted
    only open action cards and said "nothing" while proposed scope waited."""
    squad = await Squad.start(app, settings=CHAIRMAN_HOLDS)
    owner = await app.login(squad.owner.email)
    observer = await app.person("observer@example.com")
    await app.ok(
        "members.add", owner, project_id=squad.project, email=observer.email, role="observer"
    )

    async def agree(expected_owner: int) -> None:
        assert await _header_count(app, owner, squad.project) == expected_owner
        assert await _desk_count(app, owner, squad.project) == expected_owner
        assert await _header_count(app, observer, squad.project) == 0
        assert await _desk_count(app, observer, squad.project) == 0

    await agree(0)
    await propose(squad)
    await agree(1)

    item = next(
        entry["item"]
        for entry in (await app.ok("desk.show", owner))["waiting"]
        if entry["what"] == "proposed scope"
    )
    now = app.runtime.clock()
    await app.ok(
        "items.snooze", owner, project_id=squad.project, item_id=item["id"],
        until=(now + timedelta(hours=6)).isoformat(),
    )  # fmt: skip
    await agree(0)
    clock.advance(hours=7)
    await agree(1)

    await app.ok(
        "items.decide", owner, project_id=squad.project, item_id=item["id"], action="accept"
    )
    await agree(0)
