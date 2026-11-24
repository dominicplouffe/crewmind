"""The golden path for each project type (section 13, phase 5 exit demo)."""

from __future__ import annotations

from typing import Any

from nightsquad.domain.planning import bets
from nightsquad.storage.models import Project
from tests.attack.delivery_support import SOLO, command_requirement, meet, set_states, view
from tests.attack.work_support import OBSERVABLE, Squad
from tests.conftest import FakeClock
from tests.site_support import Site
from tests.support import App

PAGE = {
    "title": "Write the pricing page",
    "goal": "Write the pricing page with the three plans and their prices.",
    "success_test": "pricing.md lists three plans with a price each.",
    "test_kind": "observable",
}


async def team_does(squad: Squad, clock: FakeClock, requirement: int, **fields: Any) -> None:
    """The lead claims a task, publishes its file and completes it; the reviewer passes
    it; then the platform asks for the verdict on the requirement and the reviewer gives it."""
    task = await squad.task(requirement_id=requirement, **fields)
    await squad.ok("build-1", "agent.claim_task", task_id=task["id"])
    await squad.ok(
        "build-1", "agent.publish_artifact", name="pricing.md",
        content=f"# Pricing\n\nThree plans. Revision for task {task['id']}.",
        purpose="The pricing page",
    )  # fmt: skip
    await squad.ok("build-1", "agent.complete_task", task_id=task["id"], evidence="See pricing.md.")
    await squad.ok(
        "Reviewer", "agent.review_task", task_id=task["id"], ok=True, notes="Three plans, priced."
    )
    clock.advance(minutes=5)
    await squad.app.planning.tick()
    await squad.ok("Reviewer", "agent.rule_requirement", requirement_id=requirement, passed=True)


async def test_scenario_a_deliver_project_ships_and_completes(app: App, clock: FakeClock) -> None:
    """Deliver golden path (PRJ-4, PLN-1, PLN-6, PLN-10, WRK-11): the CEO proposes scope
    and accepts it, commits to the projection, the team builds, a reviewer gives the
    verdict, the final gap review finds one must-fix gap which is closed, the project
    becomes ready with its deliverables posted, and the chairman's sign-off writes a
    receipt: estimate against actual, tokens by kind, where the time went, and that the
    commitment was kept."""
    squad = await Squad.start(app)
    squad.run_hours = 1
    await set_states(app, {squad.requirement: "cut"})
    plan = await squad.ok(
        "CEO", "agent.propose_requirement",
        text="The pricing page shows the three plans with prices.", test_kind="observable",
        success_test="A visitor sees three plans, each with a price.", estimate_runs=4,
    )  # fmt: skip
    wanted = plan["requirements"][-1]["id"]
    await squad.ok("CEO", "agent.accept_requirement", requirement_id=wanted)
    await squad.ok("CEO", "agent.propose_commitment")
    committed = await squad.ok("CEO", "agent.accept_commitment")
    assert committed["commitment"]["state"] == "accepted"

    await team_does(squad, clock, wanted)
    await app.planning.tick()
    shown = await view(squad)
    assert shown["requirements"][-1]["state"] == "met"
    assert shown["gap_review"] == "waiting for the reviewer"

    filed = await squad.ok(
        "Reviewer", "agent.file_gap_review",
        gaps=[{
            "text": "The page does not say which plan is recommended.", "must_fix": True,
            "reason": "The goal asks for a recommendation.",
        }],
    )  # fmt: skip
    gap = filed["requirements"][-1]["id"]
    await squad.ok("CEO", "agent.change_requirement", requirement_id=gap, estimate_runs=1)
    await squad.ok("CEO", "agent.accept_requirement", requirement_id=gap)
    await team_does(squad, clock, gap, title="Recommend a plan on the page")
    await squad.finish_all()
    await app.planning.tick()

    status = await app.ok("projects.status", squad.owner, project_id=squad.project)
    assert status["state"] == "ready"
    lines = (await app.ok("chat.history", squad.owner, project_id=squad.project))["items"]
    assert any("Deliverables: pricing.md" in line["body"] for line in lines)
    shown = await view(squad)
    assert shown["gaps"][0]["state"] == "closed"
    assert shown["commitment"]["state"] == "met"

    signed = await app.ok("projects.sign_off", squad.owner, project_id=squad.project)
    receipt = signed["receipt"]
    by_id = {row["id"]: row for row in receipt["requirements"]}
    assert (by_id[wanted]["estimate_runs"], by_id[wanted]["state"]) == (4, "met")
    assert by_id[wanted]["actual_runs"] >= 2
    assert by_id[gap]["estimate_runs"] == 1
    assert set(receipt["tokens"]) == {"input", "output", "cache_write", "cache_read", "counted"}
    assert receipt["reserve_drawn"] == 0
    assert receipt["commitment"]["kept"] is True
    time = receipt["time"]
    assert set(time["where"]) == {
        "working",
        "waiting on the chairman",
        "waiting on a limit or the budget",
        "waiting on a provider",
        "reviewing",
    }
    assert 0 < sum(time["where"].values()) <= receipt["wall_clock_seconds"]
    assert time["to_first_task_seconds"] is not None
    assert time["to_first_deliverable_seconds"] is not None
    assert time["to_done_seconds"] == receipt["wall_clock_seconds"]
    status = await app.ok("projects.status", squad.owner, project_id=squad.project)
    assert status["state"] == "completed"
    shown_again = await app.ok("projects.receipt", squad.owner, project_id=squad.project)
    assert shown_again["receipt"] == receipt


async def test_scenario_explore_confirms_one_bet_and_kills_another(app: App, site: Site) -> None:
    """Explore golden path (PRJ-7, SPD-7, WRK-12): the CEO opens two bets. One gets
    outside evidence that the platform verifies, and is confirmed on it. The other is
    killed. Each finding is published as an artifact. The chairman ends the project, the
    platform assembles the findings report, and promoting it creates a draft Deliver
    project whose goal carries the findings."""
    squad = await Squad.start(app, type="explore", team=False, settings=SOLO)
    second = await squad.open_bet(
        statement="Agencies will switch from their current tool within a month.",
        kill_condition="No agency agrees to a trial start date.",
    )
    task = await squad.ok("CEO", "agent.create_task", **OBSERVABLE | {"outside_evidence": True})
    await squad.ok("CEO", "agent.claim_task", task_id=task["id"])
    filed = await squad.ok(
        "CEO", "agent.file_evidence", url=site.url(), task_id=task["id"],
        quote="Order 4411 was delivered",
    )  # fmt: skip
    assert await app.work_jobs.verify_evidence() == 1

    confirmed = await squad.ok(
        "CEO", "agent.publish_finding", bet_id=squad.bet, result="confirmed",
        text="A firm placed a paid order, shown on its public order page.",
        evidence=[filed["id"]],
    )  # fmt: skip
    killed = await squad.ok(
        "CEO", "agent.publish_finding", bet_id=second, result="killed",
        text="None of the six agencies asked would name a trial start date.",
    )  # fmt: skip
    assert [bet["state"] for bet in killed["bets"]] == ["confirmed", "killed"]
    assert confirmed["bets"][0]["finding"] == f"finding-bet-{squad.bet}.md"

    await squad.finish_all()
    ended = await app.ok("projects.end", squad.owner, project_id=squad.project)
    receipt = ended["receipt"]
    assert [(bet["id"], bet["state"]) for bet in receipt["bets"]] == [
        (squad.bet, "confirmed"),
        (second, "killed"),
    ]
    assert receipt["findings_report"] == "findings-report.md"
    status = await app.ok("projects.status", squad.owner, project_id=squad.project)
    assert status["state"] == "completed"
    async with app.runtime.sessions() as session:
        project = await session.get(Project, squad.project)
        assert project is not None
        report = await bets.report_text(session, app.runtime.services.blobs, project)
    assert report is not None
    assert f"## Bet {squad.bet}: confirmed" in report
    assert f"## Bet {second}: killed" in report
    assert "Order 4411 was delivered" in report

    promoted = await app.ok("projects.promote", squad.owner, project_id=squad.project)
    drafting = await app.ok("founder.show", squad.owner, drafting_id=promoted["drafting_id"])
    assert (drafting["state"], drafting["waiting_for"]) == ("drafting", "the Founder")
    assert "found worth building" in drafting["lines"][0]["body"]
    async with app.runtime.sessions() as session:
        from nightsquad.storage.models import Drafting

        row = await session.get(Drafting, promoted["drafting_id"])
        assert row is not None
        assert "A firm placed a paid order" in (row.document or "")


async def test_scenario_operate_meets_a_recurring_requirement(app: App, clock: FakeClock) -> None:
    """Operate golden path (PRJ-8, PLN-10): a recurring requirement is met in each of
    three weekly cycles. Each roll writes a scorecard and opens the requirement again.
    The chairman then completes the operation, and its receipt carries every cycle and
    the final scorecard."""
    squad = await Squad.start(app, type="operate", team=False, settings=SOLO)
    await set_states(app, {squad.requirement: "cut"})
    weekly = await command_requirement(squad, "report", recurring=True)

    for cycle in (1, 2, 3):
        (squad.workspace / "report.txt").unlink(missing_ok=True)
        await meet(squad, clock, weekly, "report")
        shown = await view(squad)
        assert (shown["cycles"][-1]["number"], shown["cycles"][-1]["state"]) == (cycle, "open")
        assert shown["requirements"][-1]["state"] == "met"
        clock.advance(days=7)
        await squad.finish_all()
        await app.planning.tick()
        squad.owner = await app.login(squad.owner.email)
        shown = await view(squad)
        assert shown["cycles"][cycle - 1]["state"] == "completed"
        assert shown["requirements"][-1]["state"] == "accepted"

    done = await app.ok("projects.complete", squad.owner, project_id=squad.project)
    receipt = done["receipt"]
    assert [(c["number"], c["state"]) for c in receipt["cycles"]] == [
        (1, "completed"),
        (2, "completed"),
        (3, "completed"),
        (4, "missed"),
    ]
    assert receipt["final_scorecard"]["cycle"] == 4
    status = await app.ok("projects.status", squad.owner, project_id=squad.project)
    assert status["state"] == "completed"
