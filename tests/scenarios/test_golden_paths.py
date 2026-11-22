"""The golden path for each project type (section 13, phase 5 exit demo)."""

from __future__ import annotations

from typing import Any

from tests.attack.delivery_support import set_states, view
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App

PAGE = {
    "title": "Write the pricing page",
    "goal": "Write the pricing page with the three plans and their prices.",
    "success_test": "pricing.md lists three plans with a price each.",
    "test_kind": "observable",
}


async def team_does(crew: Crew, clock: FakeClock, requirement: int, **fields: Any) -> None:
    """The lead claims a task, publishes its file and completes it; the reviewer passes
    it; then the platform asks for the verdict on the requirement and the reviewer gives it."""
    task = await crew.task(requirement_id=requirement, **fields)
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    await crew.ok(
        "build-1", "agent.publish_artifact", name="pricing.md",
        content=f"# Pricing\n\nThree plans. Revision for task {task['id']}.",
        purpose="The pricing page",
    )  # fmt: skip
    await crew.ok("build-1", "agent.complete_task", task_id=task["id"], evidence="See pricing.md.")
    await crew.ok(
        "Reviewer", "agent.review_task", task_id=task["id"], ok=True, notes="Three plans, priced."
    )
    clock.advance(minutes=5)
    await crew.app.planning.tick()
    await crew.ok("Reviewer", "agent.rule_requirement", requirement_id=requirement, passed=True)


async def test_scenario_a_deliver_project_ships_and_completes(app: App, clock: FakeClock) -> None:
    """Deliver golden path (PRJ-4, PLN-1, PLN-6, PLN-10, WRK-11): the CEO proposes scope
    and accepts it, commits to the projection, the team builds, a reviewer gives the
    verdict, the final gap review finds one must-fix gap which is closed, the project
    becomes ready with its deliverables posted, and the chairman's sign-off writes a
    receipt: estimate against actual, tokens by kind, where the time went, and that the
    commitment was kept."""
    crew = await Crew.start(app)
    crew.run_hours = 1
    await set_states(app, {crew.requirement: "cut"})
    plan = await crew.ok(
        "CEO", "agent.propose_requirement",
        text="The pricing page shows the three plans with prices.", test_kind="observable",
        success_test="A visitor sees three plans, each with a price.", estimate_runs=4,
    )  # fmt: skip
    wanted = plan["requirements"][-1]["id"]
    await crew.ok("CEO", "agent.accept_requirement", requirement_id=wanted)
    await crew.ok("CEO", "agent.propose_commitment")
    committed = await crew.ok("CEO", "agent.accept_commitment")
    assert committed["commitment"]["state"] == "accepted"

    await team_does(crew, clock, wanted)
    await app.planning.tick()
    shown = await view(crew)
    assert shown["requirements"][-1]["state"] == "met"
    assert shown["gap_review"] == "waiting for the reviewer"

    filed = await crew.ok(
        "Reviewer", "agent.file_gap_review",
        gaps=[{
            "text": "The page does not say which plan is recommended.", "must_fix": True,
            "reason": "The goal asks for a recommendation.",
        }],
    )  # fmt: skip
    gap = filed["requirements"][-1]["id"]
    await crew.ok("CEO", "agent.change_requirement", requirement_id=gap, estimate_runs=1)
    await crew.ok("CEO", "agent.accept_requirement", requirement_id=gap)
    await team_does(crew, clock, gap, title="Recommend a plan on the page")
    await crew.finish_all()
    await app.planning.tick()

    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "ready"
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    assert any("Deliverables: pricing.md" in line["body"] for line in lines)
    shown = await view(crew)
    assert shown["gaps"][0]["state"] == "closed"
    assert shown["commitment"]["state"] == "met"

    signed = await app.ok("projects.sign_off", crew.owner, project_id=crew.project)
    receipt = signed["receipt"]
    by_id = {row["id"]: row for row in receipt["requirements"]}
    assert (by_id[wanted]["estimate_runs"], by_id[wanted]["state"]) == (4, "met")
    assert by_id[wanted]["actual_runs"] >= 2
    assert by_id[gap]["estimate_runs"] == 1
    assert set(receipt["tokens"]) == {"input", "output", "cache_write", "cache_read", "counted"}
    assert receipt["reserve_drawn"] == 0
    assert receipt["commitment"]["kept"] is True
    assert receipt["wall_clock_seconds"] >= receipt["time"]["running"] > 0
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "completed"
    shown_again = await app.ok("projects.receipt", crew.owner, project_id=crew.project)
    assert shown_again["receipt"] == receipt
