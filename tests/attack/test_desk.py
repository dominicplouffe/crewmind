"""Attacks on the desk (HUM-10)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.attack.harness import assert_refused
from tests.attack.test_planning import CHAIRMAN_HOLDS, propose
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App


@pytest.mark.attack("HUM-10")
async def test_HUM_10_the_desk_is_one_list_and_a_snooze_cannot_outlast_a_deadline(
    app: App, clock: FakeClock
) -> None:
    """HUM-10: the desk lists what waits on a person across their projects: here proposed
    scope and an expired bet. A snooze is that person's own, cannot pass the item's
    deadline, and ends by itself. A flag is not on the desk."""
    crew = await Crew.start(app, settings=CHAIRMAN_HOLDS)
    wanted = await propose(crew)
    explore = await Crew.start(app, type="explore", team=False, owner=crew.owner)
    clock.advance(hours=49)
    await crew.finish_all()
    await explore.finish_all()
    await app.planning.tick()
    owner = await app.login(crew.owner.email)

    desk = (await app.ok("desk.show", owner))["waiting"]
    assert sorted((entry["what"], entry["project_id"]) for entry in desk) == sorted(
        [("proposed scope", crew.project), ("expired bet", explore.project)]
    )
    scope = next(entry for entry in desk if entry["what"] == "proposed scope")
    assert scope["title"] == f"Proposed scope: requirement {wanted}, 4 runs"
    item = scope["item"]
    now = app.runtime.clock()
    far = await app.call(
        "items.snooze", owner, project_id=crew.project, item_id=item["id"],
        until=(now + timedelta(days=3)).isoformat(),
    )  # fmt: skip
    assert_refused(far, rule="HUM-10", code="snooze_too_long")
    await app.ok(
        "items.snooze", owner, project_id=crew.project, item_id=item["id"],
        until=(now + timedelta(hours=6)).isoformat(),
    )  # fmt: skip
    kinds = [entry["what"] for entry in (await app.ok("desk.show", owner))["waiting"]]
    assert kinds == ["expired bet"]
    listed = await app.ok("items.list", owner, project_id=crew.project)
    assert item["id"] in [entry["id"] for entry in listed["items"]]
    clock.advance(hours=7)
    kinds = [entry["what"] for entry in (await app.ok("desk.show", owner))["waiting"]]
    assert "proposed scope" in kinds
