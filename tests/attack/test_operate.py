"""Attacks on Operate: cycles, recurring requirements and metrics (PRJ-8, PLN-11,
section 7.13)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select

from crewmind.catalog.operation import CatalogError
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.registry import catalog
from crewmind.domain.planning import metrics
from crewmind.domain.planning.model import CYCLE_MACHINE
from crewmind.storage.models import Cycle
from tests.attack.delivery_support import SOLO, command_requirement, meet, set_states, view
from tests.attack.harness import assert_refused
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.site_support import Site
from tests.support import App


async def operation(app: App) -> Crew:
    """A solo Operate project whose only scope is one recurring command requirement."""
    crew = await Crew.start(app, type="operate", team=False, settings=SOLO)
    await set_states(app, {crew.requirement: "cut"})
    crew.requirement = await command_requirement(crew, "report", recurring=True)
    return crew


async def later(crew: Crew, clock: FakeClock, **delta: float) -> dict[str, Any]:
    """Move the clock, let the platform tick, and read the plan as the chairman."""
    clock.advance(**delta)
    await crew.finish_all()
    await crew.app.planning.tick()
    crew.owner = await crew.app.login(crew.owner.email)
    return await view(crew)


@pytest.mark.attack("PRJ-8")
@pytest.mark.attack("7.13")
async def test_PRJ_8_a_cycle_closes_completed_missed_or_skipped(app: App, clock: FakeClock) -> None:
    """PRJ-8, 7.13, INV-20: the platform rolls cycles; nobody else can. A cycle whose
    recurring scope was met on time is completed, and the recurring requirement opens
    again. One with scope left open is missed and gets a stub narrative. One with no work
    run because the project was held is skipped; a held project opens no cycle and
    resumes into exactly one, however many periods passed; two skipped in a row pause it."""
    crew = await operation(app)
    for name in ("cycles.roll", "cycles.close", "agent.roll_cycle", "agent.close_cycle"):
        with pytest.raises(CatalogError):
            catalog.get(name)
    await meet(crew, clock, crew.requirement, "report")
    shown = await view(crew)
    assert [(c["number"], c["state"]) for c in shown["cycles"]] == [(1, "open")]
    assert shown["cycles"][0]["ends_at"].startswith("2026-11-23T00:00")
    assert shown["requirements"][-1]["state"] == "met"

    token = (await crew.call("CEO", "agent.whoami")).request.headers["Authorization"][7:]
    due = {"due_at": "2026-11-22T12:00:00Z", "source": "The board meets on Sunday."}
    assert (
        await app.call("cycles.set_due", token, project_id=crew.project, **due)
    ).status_code in (
        401,
        403,
    )
    assert (
        await crew.call("Reviewer", "agent.write_cycle_narrative", text="All good, I promise you.")
    ).status_code == 403
    outside = await app.call(
        "cycles.set_due", crew.owner, project_id=crew.project,
        due_at="2026-12-25T00:00:00Z", source="A date after the cycle ends.",
    )  # fmt: skip
    assert_refused(outside, rule="PRJ-8", code="due_time_outside_the_cycle")
    moved = await app.ok("cycles.set_due", crew.owner, project_id=crew.project, **due)
    assert moved["cycles"][0]["due_at"].startswith("2026-11-22T12:00")
    await crew.ok(
        "CEO", "agent.write_cycle_narrative", text="The weekly report went out on Saturday."
    )

    shown = await later(crew, clock, days=2)
    first, second = shown["cycles"]
    assert (first["state"], first["narrative_by_ceo"]) == ("completed", True)
    assert first["narrative"] == "The weekly report went out on Saturday."
    assert (first["scorecard"]["recurring_met"], first["scorecard"]["recurring_total"]) == (1, 1)
    assert (second["number"], second["state"]) == (2, "open")
    assert shown["requirements"][-1]["state"] == "accepted"

    shown = await later(crew, clock, days=7)
    assert [c["state"] for c in shown["cycles"]] == ["completed", "missed", "open"]
    assert shown["cycles"][1]["narrative"].startswith(
        "No narrative was written. Cycle 2 was missed"
    )

    await crew.finish_all()
    await app.ok("projects.hold", crew.owner, project_id=crew.project)
    shown = await later(crew, clock, days=7)
    assert [c["state"] for c in shown["cycles"]] == ["completed", "missed", "skipped"]
    shown = await later(crew, clock, days=21)
    assert len(shown["cycles"]) == 3
    await app.ok("projects.resume", crew.owner, project_id=crew.project)
    shown = await later(crew, clock, minutes=1)
    assert [(c["number"], c["state"]) for c in shown["cycles"]][-1] == (4, "open")
    assert len(shown["cycles"]) == 4

    await app.ok("projects.hold", crew.owner, project_id=crew.project)
    shown = await later(crew, clock, days=7)
    assert [c["state"] for c in shown["cycles"]][-2:] == ["skipped", "skipped"]
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "paused"
    assert "skipped_cycles" in [hold["reason"] for hold in status["holds"]]
    await app.ok("projects.resume", crew.owner, project_id=crew.project)
    shown = await later(crew, clock, minutes=1)
    async with app.runtime.sessions() as session:
        still_open = await session.scalar(
            select(func.count()).select_from(Cycle).where(Cycle.state == "open")
        )
    assert (still_open, shown["cycles"][-1]["number"]) == (1, 5)
    pack = (await crew.ok("CEO", "agent.context"))["context_pack"]
    assert "Cycle 5 is open." in pack
    assert "Cycle 2 (missed): No narrative was written." in pack
    assert "Cycle 4 (skipped): No narrative was written." in pack
    assert "Cycle 1 (completed)" not in pack
    with pytest.raises(Refusal) as refused:
        CYCLE_MACHINE.check("completed", "open")
    assert refused.value.envelope.rule == "7.13"


@pytest.mark.attack("PLN-11")
async def test_PLN_11_the_platform_reads_a_metric_and_no_agent_writes_one(
    app: App, clock: FakeClock, site: Site
) -> None:
    """PLN-11, PLN-10, WRK-12: a metric requirement names a public page and a pattern. The
    platform reads it on a schedule and writes the requirement met when the number
    reaches its target. A page inside the network is never read, a bad pattern is refused,
    and no operation lets an agent write a reading or mark the metric met."""
    crew = await Crew.start(app, team=False, settings=SOLO)
    metric = {
        "text": "At least 5,000 orders are shown on the public orders page.",
        "test_kind": "metric", "estimate_runs": 3, "metric_url": site.url(),
        "metric_pattern": "Order ([0-9,]+) was", "metric_target": 5000,
    }  # fmt: skip
    for wrong, code in (
        ({"metric_url": "file:///etc/passwd"}, "metric_source_not_public"),
        ({"metric_pattern": "Order [0-9]+ was"}, "metric_pattern_invalid"),
        ({"metric_pattern": "Order ([0-9"}, "metric_pattern_invalid"),
        ({"metric_target": None}, "metric_needs_a_source"),
    ):
        refused = await crew.call("CEO", "agent.propose_requirement", **metric | wrong)
        assert_refused(refused, rule="PLN-11", code=code)
    for name in ("agent.record_reading", "agent.read_metric", "metrics.record"):
        with pytest.raises(CatalogError):
            catalog.get(name)

    inside = await crew.add_requirement(**metric | {"metric_url": "http://10.0.0.5/orders"})
    wanted = await crew.add_requirement(**metric)
    assert await app.planning.read_metrics() == 2
    shown = {item["id"]: item for item in (await view(crew))["requirements"]}
    assert shown[inside]["metric"]["latest"] is None
    assert "not a public address" in shown[inside]["metric"]["failure"]
    assert (shown[wanted]["state"], shown[wanted]["metric"]["latest"]) == ("accepted", 4411.0)
    assert shown[wanted]["success_test"].endswith("is at least 5000.")
    assert await app.planning.read_metrics() == 0

    site.page = b"Order 5,120 was delivered."
    clock.advance(hours=25)
    assert await app.planning.read_metrics() == 2
    crew.owner = await app.login(crew.owner.email)
    shown = {item["id"]: item for item in (await view(crew))["requirements"]}
    assert (shown[wanted]["state"], shown[wanted]["metric"]["latest"]) == ("met", 5120.0)
    assert shown[inside]["state"] == "accepted"
    met = [
        event
        for event in await app.events(crew.owner, crew.project)
        if event["type"] == "requirement.state_changed" and event["after"]["state"] == "met"
    ]
    assert [event["actor_kind"] for event in met] == ["platform"]


async def test_PLN_11_losing_ground_needs_a_full_window(
    app: App, clock: FakeClock, site: Site
) -> None:
    """PLN-11: the project is losing ground when the latest reading is further from
    target than the oldest in a 6-reading window. A single bad reading is not enough, and
    the CEO and the chairman are told once."""
    target = {"target": 100.0, "at_least": True}
    assert metrics.losing_ground([50, 10], target) is False
    assert metrics.losing_ground([50, 60, 60, 60, 60, 49], target) is True
    assert metrics.losing_ground([50, 10, 10, 10, 10, 50], target) is False
    assert metrics.losing_ground([150, 140, 130, 120, 110, 105], target) is False
    at_most = {"target": 10.0, "at_least": False}
    assert metrics.losing_ground([20, 20, 20, 20, 20, 30], at_most) is True

    crew = await Crew.start(app, team=False, settings=SOLO)
    wanted = await crew.add_requirement(
        text="At least 100 firms are listed on the public page.", test_kind="metric",
        estimate_runs=3, metric_url=site.url(), metric_pattern="([0-9]+) firms", metric_target=100,
    )  # fmt: skip
    for number in (50, 48, 47, 46, 45, 44, 43):
        site.page = f"{number} firms".encode()
        clock.advance(hours=24)
        assert await app.planning.read_metrics() == 1
    crew.owner = await app.login(crew.owner.email)
    shown = {item["id"]: item for item in (await view(crew))["requirements"]}
    assert shown[wanted]["metric"]["losing_ground"] is True
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    warnings = [line for line in lines if "is losing ground" in line["body"]]
    assert len(warnings) == 1
    assert "the latest reading is 44" in warnings[0]["body"]
