"""Attacks on the plan: scope, authority, readiness and who writes "met" (PLN-1, PLN-2,
PLN-3, PLN-10, INV-18, INV-19, section 7.2)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.attack.harness import assert_refused
from tests.attack.work_support import Squad
from tests.conftest import FakeClock
from tests.support import App, agent_call, live_run, running_project

SCOPE = {
    "text": "The pricing page shows the three plans.",
    "test_kind": "observable",
    "success_test": "A visitor sees three plans with prices.",
    "estimate_runs": 4,
}
CHAIRMAN_HOLDS = {"authority.accept_scope": "chairman", "authority.change_scope": "chairman"}


async def plan(squad: Squad) -> dict[int, dict[str, Any]]:
    shown = await squad.app.ok("plan.show", squad.owner, project_id=squad.project)
    return {item["id"]: item for item in shown["requirements"]}


async def propose(squad: Squad, **fields: Any) -> int:
    shown = await squad.ok("CEO", "agent.propose_requirement", **{**SCOPE, **fields})
    return shown["requirements"][-1]["id"]


async def chair(squad: Squad, name: str, requirement: int, **values: Any) -> dict[str, Any]:
    return await squad.app.ok(
        name, squad.owner, project_id=squad.project, requirement_id=requirement, **values
    )


@pytest.mark.attack("INV-18")
async def test_INV_18_no_task_is_created_under_scope_that_is_not_ready(app: App) -> None:
    """INV-18, PLN-1, PLN-2: a task names an accepted, estimated requirement whose
    dependencies are met. A proposed, unestimated, blocked, cut or foreign requirement
    gets no work, and cutting a requirement kills the open tasks under it."""
    squad = await Squad.start(app, settings=CHAIRMAN_HOLDS)
    assert_refused(
        await squad.call("CEO", "agent.create_task", requirement_id=None, team="build", **TASK),
        rule="INV-18", code="task_needs_a_requirement",
    )  # fmt: skip

    proposed = await propose(squad)
    refused = await squad.call(
        "CEO", "agent.create_task", requirement_id=proposed, team="build", **TASK
    )
    assert_refused(refused, rule="INV-18", code="requirement_not_accepted")

    bare = await squad.add_requirement(estimate_runs=None)
    refused = await squad.call(
        "CEO", "agent.create_task", requirement_id=bare, team="build", **TASK
    )
    assert_refused(refused, rule="INV-18", code="requirement_not_estimated")

    later = await squad.add_requirement(depends_on=[squad.requirement])
    refused = await squad.call(
        "CEO", "agent.create_task", requirement_id=later, team="build", **TASK
    )
    assert_refused(refused, rule="INV-18", code="dependencies_not_met")

    refused = await squad.call("CEO", "agent.create_task", requirement_id=999, team="build", **TASK)
    assert refused.status_code == 403
    assert refused.json()["code"] == "requirement_not_found"

    task = await squad.task()
    sub = await squad.call("build-1", "agent.claim_task", task_id=task["id"])
    assert sub.status_code == 200, sub.text
    assert (await plan(squad))[squad.requirement]["state"] == "in progress"
    cut = await chair(squad, "requirements.cut", squad.requirement, reason="No longer wanted.")
    assert cut["note"] == "1 open tasks under it were killed."
    assert (await squad.show(task["id"]))["state"] == "killed"
    refused = await squad.call("CEO", "agent.create_task", team="build", **TASK)
    assert_refused(refused, rule="INV-18", code="requirement_not_accepted")


TASK = {
    "title": "Draft the pricing page",
    "goal": "Write the pricing page with the three plans.",
    "success_test": "The page lists three plans with their prices.",
    "test_kind": "observable",
}


@pytest.mark.attack("INV-19")
async def test_INV_19_a_dependency_loop_is_refused_and_named_and_stages_go_in_order(
    app: App,
) -> None:
    """INV-19, PLN-2: an edge that would close a loop is refused with the loop named, by
    whoever asks. Work is never created ahead of the lowest stage with open scope."""
    squad = await Squad.start(app)
    first = squad.requirement
    second = await propose(squad, depends_on=[first])
    third = await propose(squad, depends_on=[second])
    loop = await squad.call(
        "CEO", "agent.change_requirement", requirement_id=second, depends_on=[first, third]
    )
    envelope = assert_refused(loop, rule="INV-19", code="dependency_loop")
    assert f"{second} -> {third} -> {second}" in envelope.message
    own = await squad.call(
        "CEO", "agent.change_requirement", requirement_id=third, depends_on=[third]
    )
    assert_refused(own, rule="INV-19", code="dependency_loop")
    by_chair = await app.call(
        "requirements.change", squad.owner, project_id=squad.project, requirement_id=first,
        depends_on=[third],
    )  # fmt: skip
    assert_refused(by_chair, rule="INV-19", code="dependency_loop")
    assert (await plan(squad))[first]["depends_on"] == []

    staged = await propose(squad, stage=2)
    await squad.ok("CEO", "agent.accept_requirement", requirement_id=staged)
    ahead = await squad.call(
        "CEO", "agent.create_task", requirement_id=staged, team="build", **TASK
    )
    envelope = assert_refused(ahead, rule="INV-19", code="stage_not_open")
    assert "stage 1 still has open scope" in envelope.message
    shown = (await plan(squad))[staged]
    assert (shown["ready"], shown["stage"]) == (False, 2)


@pytest.mark.attack("PLN-1")
async def test_PLN_1_the_ceo_cannot_take_authority_it_was_not_given(app: App) -> None:
    """PLN-1, P7, section 3: where the chairman holds plan and scope authority, the CEO
    proposes and nothing more. It never changes a requirement the chairman wrote, and no
    other seat touches the plan at all."""
    squad = await Squad.start(app, settings=CHAIRMAN_HOLDS)
    mine = await propose(squad)
    accept = await squad.call("CEO", "agent.accept_requirement", requirement_id=mine)
    assert_refused(accept, rule="PLN-1", code="needs_the_chairman")
    decline = await squad.call(
        "CEO", "agent.decline_requirement", requirement_id=mine, reason="I changed my mind."
    )
    assert_refused(decline, rule="PLN-1", code="needs_the_chairman")
    assert (await plan(squad))[mine]["state"] == "proposed"

    await chair(squad, "requirements.accept", mine)
    cut = await squad.call(
        "CEO", "agent.cut_requirement", requirement_id=mine, reason="It is too much work."
    )
    assert_refused(cut, rule="PLN-1", code="needs_the_chairman")
    shrink = await squad.call(
        "CEO", "agent.change_requirement", requirement_id=mine, estimate_runs=1
    )
    assert_refused(shrink, rule="PLN-1", code="needs_the_chairman")

    for seat in ("build-1", "build-2", "Reviewer"):
        for name, values in {
            "agent.propose_requirement": SCOPE,
            "agent.accept_requirement": {"requirement_id": mine},
            "agent.cut_requirement": {"requirement_id": mine, "reason": "Not needed at all."},
        }.items():
            assert (await squad.call(seat, name, **values)).status_code == 403, (seat, name)
    assert (await plan(squad))[mine]["state"] == "accepted"


@pytest.mark.attack("PLN-1")
async def test_PLN_1_a_chairman_authored_requirement_is_the_chairmans(app: App) -> None:
    """PLN-1, P7: with every authority the autonomous preset gives it, the CEO still cannot
    cut, reword, re-estimate, restage or reopen what the chairman wrote. It may give the
    first estimate when the chairman gave none."""
    squad = await Squad.start(app)
    theirs = squad.requirement
    attempts: dict[str, dict[str, Any]] = {
        "agent.cut_requirement": {"reason": "It is too much work."},
        "agent.change_requirement": {"text": "Something much easier to do."},
    }
    for name, values in attempts.items():
        refused = await squad.call("CEO", name, requirement_id=theirs, **values)
        assert_refused(refused, rule="PLN-1", code="chairman_authored")
    for field in ({"estimate_runs": 1}, {"stage": 3}, {"success_test": "It is done when I say."}):
        refused = await squad.call(
            "CEO", "agent.change_requirement", requirement_id=theirs, **field
        )
        assert_refused(refused, rule="PLN-1", code="chairman_authored")
    await chair(squad, "requirements.cut", theirs, reason="Not this quarter.")
    refused = await squad.call("CEO", "agent.reopen_requirement", requirement_id=theirs)
    assert_refused(refused, rule="PLN-1", code="chairman_authored")

    bare = await squad.add_requirement(estimate_runs=None)
    await squad.ok("CEO", "agent.change_requirement", requirement_id=bare, estimate_runs=6)
    again = await squad.call(
        "CEO", "agent.change_requirement", requirement_id=bare, estimate_runs=1
    )
    assert_refused(again, rule="PLN-1", code="chairman_authored")
    assert (await plan(squad))[bare]["estimate_runs"] == 6


async def test_PLN_1_the_chairman_accepts_scope_when_they_hold_it(app: App) -> None:
    """PLN-1, 7.2, INV-21: the chairman accepts one proposal and declines another with a
    reason. Each is recorded with the chairman as its actor, and the author stays the CEO."""
    squad = await Squad.start(app, settings=CHAIRMAN_HOLDS)
    wanted, unwanted = await propose(squad), await propose(squad, text="A second pricing page.")
    asked = (await app.ok("chat.history", squad.owner, project_id=squad.project))["items"]
    assert any(f"proposes requirement {wanted}" in line["body"] for line in asked)
    await chair(squad, "requirements.accept", wanted)
    short = await app.call(
        "requirements.decline", squad.owner, project_id=squad.project, requirement_id=unwanted,
        reason="No.",
    )  # fmt: skip
    assert_refused(short, rule="PLN-1", code="reason_too_short")
    await chair(squad, "requirements.decline", unwanted, reason="One pricing page is enough.")
    shown = await plan(squad)
    assert (shown[wanted]["state"], shown[wanted]["author"]) == ("accepted", "ceo")
    assert (shown[unwanted]["state"], shown[unwanted]["reason"]) == (
        "declined",
        "One pricing page is enough.",
    )
    changes = [
        (event["subject_id"], event["after"]["state"], event["actor_kind"])
        for event in await app.events(squad.owner, squad.project)
        if event["type"] == "requirement.state_changed" and event["actor_kind"] == "person"
    ][-2:]
    assert changes == [(str(wanted), "accepted", "person"), (str(unwanted), "declined", "person")]


@pytest.mark.attack("PLN-1")
async def test_PLN_1_an_explore_project_takes_no_requirements_from_the_ceo(app: App) -> None:
    """PLN-1: the CEO proposes requirements, but not in Explore, which has bets."""
    squad = await Squad.start(app, type="explore", team=False)
    refused = await squad.call("CEO", "agent.propose_requirement", **SCOPE)
    assert_refused(refused, rule="PLN-1", code="explore_has_bets")


@pytest.mark.attack("7.2")
async def test_7_2_a_requirement_only_moves_along_its_lifecycle(app: App) -> None:
    """Section 7.2: a declined requirement cannot be cut or accepted, a proposed one cannot
    be cut, and only a met or cut one is reopened. Nothing an agent sends writes a state."""
    squad = await Squad.start(app)
    proposed = await propose(squad)
    cut = await squad.call(
        "CEO", "agent.cut_requirement", requirement_id=proposed, reason="Never mind this one."
    )
    assert_refused(cut, rule="7.2")
    await squad.ok(
        "CEO", "agent.decline_requirement", requirement_id=proposed, reason="Never mind this one."
    )
    assert_refused(
        await squad.call("CEO", "agent.accept_requirement", requirement_id=proposed),
        rule="PLN-1", code="not_proposed",
    )  # fmt: skip
    again = await squad.call(
        "CEO", "agent.decline_requirement", requirement_id=proposed, reason="Never mind, again."
    )
    assert_refused(again, rule="7.2")
    accepted = await propose(squad)
    await squad.ok("CEO", "agent.accept_requirement", requirement_id=accepted)
    reopen = await squad.call("CEO", "agent.reopen_requirement", requirement_id=accepted)
    assert_refused(reopen, rule="PLN-1", code="not_met_or_cut")
    forged = await squad.call(
        "CEO", "agent.change_requirement", requirement_id=accepted, state="met"
    )
    assert forged.status_code in (200, 422)
    assert (await plan(squad))[accepted]["state"] == "accepted"


@pytest.mark.attack("PLN-3")
async def test_PLN_3_scope_that_does_not_fit_the_budget_is_refused_with_the_arithmetic(
    app: App,
) -> None:
    """PLN-3: plan tokens are the adjusted runs of open accepted scope times the median
    tokens per work run. Accepting past the tokens left before wrap-up is refused with
    those numbers. The chairman may accept anyway; the CEO may not."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"budget.tokens": 1_000_000})
    tool = {"name": "agent_propose_requirement", "arguments": SCOPE}
    accept = {"name": "agent_accept_requirement", "arguments": {"requirement_id": 1}}
    app.script(
        "CEO/work",
        {"tools": [tool], "usage": {"input": 100_000, "output": 0}},
        {"tools": [accept], "usage": {"input": 0, "output": 0}},
        {"text": "Planned.", "usage": {"input": 0, "output": 0}},
    )
    await app.ok("chat.command", owner, project_id=project, text="/do Plan the pricing page.")
    await app.work()
    shown = await app.ok("plan.show", owner, project_id=project)
    assert shown["requirements"][0]["state"] == "accepted"
    assert shown["numbers"]["tokens_per_run"] == 100_000
    assert shown["numbers"]["plan_tokens"] == 400_000
    assert shown["numbers"]["tokens_before_wrapup"] == 800_000

    live = await live_run(app, project)
    big = await agent_call(app, live.token, "agent.propose_requirement", **SCOPE | {
        "text": "Every page of the site is rewritten.", "estimate_runs": 5,
    })  # fmt: skip
    assert big.status_code == 200, big.text
    refused = await agent_call(app, live.token, "agent.accept_requirement", requirement_id=2)
    envelope = assert_refused(refused, rule="PLN-3", code="does_not_fit_budget")
    assert "900,000 tokens (9 runs x 100,000 tokens per run" in envelope.message
    assert "800,000 tokens are left before wrap-up" in envelope.message
    by_chair = await app.call("requirements.accept", owner, project_id=project, requirement_id=2)
    assert_refused(by_chair, rule="PLN-3", code="does_not_fit_budget")
    anyway = await app.ok(
        "requirements.accept", owner, project_id=project, requirement_id=2, anyway=True
    )
    assert anyway["requirements"][1]["state"] == "accepted"
    assert "900,000 tokens" in anyway["note"]


@pytest.mark.attack("PLN-10")
async def test_PLN_10_only_the_platform_writes_met(app: App, clock: FakeClock) -> None:
    """PLN-10, P5, INV-21: nobody marks scope met. When the work under a requirement is
    done the platform asks a reviewer seat; the CEO and the workers cannot give the
    verdict, a rejection needs a note and sticks until more work is done, and the change
    to met is the platform's, recorded with who ruled."""
    squad = await Squad.start(app)
    requirement = squad.requirement

    async def do_a_task() -> None:
        task = await squad.task()
        await squad.ok("build-1", "agent.claim_task", task_id=task["id"])
        await squad.ok(
            "build-1", "agent.complete_task", task_id=task["id"], evidence="See summary.md."
        )
        await squad.ok(
            "Reviewer", "agent.review_task", task_id=task["id"], ok=True, notes="Read it all."
        )
        clock.advance(minutes=1)
        await app.planning.tick()

    early = await squad.call(
        "Reviewer", "agent.rule_requirement", requirement_id=requirement, passed=True
    )
    assert_refused(early, rule="PLN-10", code="no_verdict_wanted")
    await do_a_task()
    assert (await plan(squad))[requirement]["state"] == "checking"
    for seat in ("CEO", "build-1", "build-2"):
        own = await squad.call(
            seat, "agent.rule_requirement", requirement_id=requirement, passed=True
        )
        assert_refused(own, rule="PLN-10", code="not_a_reviewer")
    bare = await squad.call(
        "Reviewer", "agent.rule_requirement", requirement_id=requirement, passed=False
    )
    assert_refused(bare, rule="PLN-10", code="rejection_needs_a_note")
    await squad.ok(
        "Reviewer", "agent.rule_requirement", requirement_id=requirement, passed=False,
        note="Two of the interviews are missing.",
    )  # fmt: skip
    shown = (await plan(squad))[requirement]
    assert (shown["state"], shown["failures"], shown["ruling"]) == ("in progress", 1, "failed")
    assert shown["ruling_note"] == "Two of the interviews are missing."

    clock.advance(minutes=5)
    await app.planning.tick()
    assert (await plan(squad))[requirement]["state"] == "in progress"

    await do_a_task()
    assert (await plan(squad))[requirement]["state"] == "checking"
    await squad.ok("Reviewer", "agent.rule_requirement", requirement_id=requirement, passed=True)
    shown = (await plan(squad))[requirement]
    assert (shown["state"], shown["ruling"]) == ("met", "passed")
    assert shown["actual_runs"] >= 2
    met = [
        event
        for event in await app.events(squad.owner, squad.project)
        if event["type"] == "requirement.state_changed" and event["after"]["state"] == "met"
    ]
    assert [event["actor_kind"] for event in met] == ["platform"]
    assert met[0]["detail"]["ruling"] == "passed"


@pytest.mark.attack("PLN-10")
async def test_PLN_10_under_supervised_the_verdict_is_the_chairmans(
    app: App, clock: FakeClock
) -> None:
    """PLN-10, section 3: where `authority.verdict` is chairman, a reviewer seat's verdict
    on a requirement is refused and the chairman is asked in the chat. The chairman's
    verdict is recorded with the chairman named."""
    squad = await Squad.start(app, settings={"authority.verdict": "chairman"})
    requirement = squad.requirement
    task = await squad.task()
    await squad.ok("build-1", "agent.claim_task", task_id=task["id"])
    await squad.ok("build-1", "agent.complete_task", task_id=task["id"], evidence="See summary.md.")
    await squad.ok(
        "Reviewer", "agent.review_task", task_id=task["id"], ok=True, notes="Read it all."
    )
    clock.advance(minutes=1)
    await app.planning.tick()
    refused = await squad.call(
        "Reviewer", "agent.rule_requirement", requirement_id=requirement, passed=True
    )
    assert_refused(refused, rule="PLN-10", code="verdict_is_the_chairmans")
    lines = (await app.ok("chat.history", squad.owner, project_id=squad.project))["items"]
    assert any(f"Requirement {requirement} is ready for a verdict" in m["body"] for m in lines)
    await chair(squad, "requirements.rule", requirement, passed=True)
    assert (await plan(squad))[requirement]["state"] == "met"
    met = [
        event
        for event in await app.events(squad.owner, squad.project)
        if event["type"] == "requirement.state_changed" and event["after"]["state"] == "met"
    ]
    assert met[0]["detail"]["ruled_by"] == squad.owner.person_id


@pytest.mark.attack("PLN-3")
async def test_PLN_3_the_ceo_cannot_bring_scope_back_by_reopening_it(app: App) -> None:
    """PLN-1, PLN-3, GOV-3: a CEO that reopens a cut requirement is held to the same
    limits as one proposing it: refused when the plan would not fit, and refused in
    wrap-up mode. The chairman may reopen regardless."""
    from tests.attack.delivery_support import spend

    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"budget.tokens": 1_000_000})
    propose_it = {"name": "agent_propose_requirement", "arguments": SCOPE | {"estimate_runs": 6}}
    accept = {"name": "agent_accept_requirement", "arguments": {"requirement_id": 1}}
    cut = {
        "name": "agent_cut_requirement",
        "arguments": {"requirement_id": 1, "reason": "Parked for a later quarter."},
    }
    app.script(
        "CEO/work",
        {"tools": [propose_it], "usage": {"input": 100_000, "output": 0}},
        {"tools": [accept], "usage": {"input": 0, "output": 0}},
        {"tools": [cut], "usage": {"input": 0, "output": 0}},
        {"text": "Planned.", "usage": {"input": 0, "output": 0}},
    )
    await app.ok("chat.command", owner, project_id=project, text="/do Plan the pricing page.")
    await app.work()
    await spend(app, project, 300_000)

    live = await live_run(app, project)
    refused = await agent_call(app, live.token, "agent.reopen_requirement", requirement_id=1)
    envelope = assert_refused(refused, rule="PLN-3", code="does_not_fit_budget")
    assert "600,000 tokens (6 runs x 100,000 tokens per run" in envelope.message
    assert "500,000 tokens are left before wrap-up" in envelope.message
    await spend(app, project, 510_000)
    late = await agent_call(app, live.token, "agent.reopen_requirement", requirement_id=1)
    assert_refused(late, rule="GOV-3", code="wrap_up_mode")
    by_chair = await app.ok("requirements.reopen", owner, project_id=project, requirement_id=1)
    assert by_chair["requirements"][0]["state"] == "accepted"


@pytest.mark.attack("PLN-10")
async def test_PLN_10_a_reviewer_that_did_the_work_does_not_rule_on_it(
    app: App, clock: FakeClock
) -> None:
    """PLN-10, P5, INV-3: a reviewer seat that held a task under a requirement cannot give
    the verdict on that requirement. An Explore project takes no requirement, even from
    the chairman."""
    squad = await Squad.start(app, team=False, settings={"review.independent": False})
    task = await squad.ok("CEO", "agent.create_task", **TASK)
    await squad.ok("CEO", "agent.claim_task", task_id=task["id"])
    await squad.ok("CEO", "agent.complete_task", task_id=task["id"], evidence="The page is up.")
    clock.advance(minutes=1)
    await app.planning.tick()
    assert (await plan(squad))[squad.requirement]["state"] == "checking"
    async with app.runtime.sessions() as session, session.begin():
        from sqlalchemy import select, update

        from nightsquad.storage.models import Seat, Task

        reviewer = await session.scalar(select(Seat.id).where(Seat.name == "Reviewer"))
        await session.execute(update(Task).values(claimant_id=reviewer))
    own = await squad.call(
        "Reviewer", "agent.rule_requirement", requirement_id=squad.requirement, passed=True
    )
    assert_refused(own, rule="PLN-10", code="you_did_this_work")

    explore = await Squad.start(app, type="explore", team=False, owner=squad.owner)
    refused = await app.call("requirements.add", explore.owner, project_id=explore.project, **SCOPE)
    assert_refused(refused, rule="PLN-1", code="explore_has_bets")
