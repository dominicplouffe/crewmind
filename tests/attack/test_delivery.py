"""Attacks on dates, the reserve, raises and finishing (PLN-6 to PLN-9, GOV-5, GOV-10,
PRJ-4 to PRJ-6, WRK-11, section 7.6)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from nightsquad.storage.models import Alarm
from tests.attack.delivery_support import (
    SOLO,
    command_requirement,
    meet,
    set_states,
    spend,
    view,
)
from tests.attack.harness import assert_refused
from tests.attack.test_planning import SCOPE, TASK
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App


async def solo(app: App, **settings: Any) -> Crew:
    """A solo Deliver project whose only finished run so far took one hour."""
    crew = await Crew.start(app, team=False, settings=SOLO | settings)
    crew.run_hours = 1
    await crew.ok("CEO", "agent.whoami")
    await crew.finish_all()
    return crew


@pytest.mark.attack("PLN-6")
async def test_PLN_6_a_commitment_has_no_date_field(app: App) -> None:
    """PLN-6, 7.6, INV-1: the CEO proposes a commitment once a projection exists, one at a
    time, and cannot give it a date. The date is the projection, or a later date the
    chairman chooses; never an earlier one, and never the CEO's."""
    crew = await solo(app, **{"authority.date": "chairman"})
    await set_states(app, {crew.requirement: "cut"})
    early = await crew.call("CEO", "agent.propose_commitment")
    assert_refused(early, rule="PLN-6", code="no_projection")
    await command_requirement(crew, "pricing", runs=8)

    proposed = await crew.ok("CEO", "agent.propose_commitment", date="2026-11-22T00:00:00Z")
    assert (proposed["commitment"]["state"], proposed["commitment"]["date"]) == ("proposed", None)
    assert proposed["pace"]["projection_kind"] == "best case"
    again = await crew.call("CEO", "agent.propose_commitment")
    assert_refused(again, rule="PLN-6", code="commitment_exists")
    own = await crew.call("CEO", "agent.accept_commitment")
    assert_refused(own, rule="PLN-1", code="needs_the_chairman")

    now = app.runtime.clock()
    sooner = await app.call(
        "commitments.accept", crew.owner, project_id=crew.project,
        date=(now + timedelta(hours=1)).isoformat(),
    )  # fmt: skip
    envelope = assert_refused(sooner, rule="PLN-6", code="date_before_projection")
    assert "the projection is 21 Nov 2026 11:00 UTC, 1.0 hours later" in envelope.message
    accepted = await app.ok("commitments.accept", crew.owner, project_id=crew.project)
    commitment = accepted["commitment"]
    assert commitment["state"] == "accepted"
    assert commitment["date"] == commitment["projected_at"] == accepted["pace"]["projected_at"]
    assert commitment["date"].startswith((now + timedelta(hours=2)).isoformat()[:16])

    late = await app.call(
        "commitments.decline", crew.owner, project_id=crew.project, reason="Too late to say no."
    )
    assert_refused(late, rule="7.6")


@pytest.mark.attack("7.6")
async def test_7_6_a_commitment_only_moves_along_its_lifecycle(app: App) -> None:
    """Section 7.6, PLN-6: under autonomous authority the CEO accepts its own proposal at
    the projection, whatever date it sends. It cannot decline an accepted commitment,
    reset one that is on track, or move its date; only a Deliver project has one."""
    crew = await solo(app)
    await crew.ok("CEO", "agent.propose_commitment")
    accepted = await crew.ok("CEO", "agent.accept_commitment", date="2026-11-21T10:00:00Z")
    commitment = accepted["commitment"]
    assert commitment["state"] == "accepted"
    assert commitment["date"] == accepted["pace"]["projected_at"]
    reset = await crew.call("CEO", "agent.reset_commitment")
    assert_refused(reset, rule="PLN-6", code="commitment_not_at_risk")
    for name in ("commitments.move", "commitments.decline"):
        token = (await crew.call("CEO", "agent.whoami")).request.headers["Authorization"][7:]
        answer = await app.call(
            name, token, project_id=crew.project, date="2030-01-01T00:00:00Z", reason="Later."
        )
        assert answer.status_code in (401, 403), name
    explore = await Crew.start(app, type="explore", team=False, owner=crew.owner)
    refused = await explore.call("CEO", "agent.propose_commitment")
    assert_refused(refused, rule="PLN-6", code="commitments_are_for_deliver")


@pytest.mark.attack("PLN-8")
async def test_PLN_7_PLN_8_an_at_risk_commitment_freezes_new_scope(
    app: App, clock: FakeClock
) -> None:
    """PLN-7, PLN-8, PLN-6: scope the chairman adds re-projects the commitment at once. At
    risk, the CEO's proposals are refused with the dates, while existing work goes on. The
    CEO resets only to the projection, and each reset is counted. Past its date with
    scope open the commitment is breached and the chairman gets an alarm; the chairman
    moves the date; when all scope is met the commitment is met."""
    crew = await solo(app)
    await set_states(app, {crew.requirement: "cut"})
    first = await command_requirement(crew, "pricing", runs=8)
    await crew.ok("CEO", "agent.propose_commitment")
    await crew.ok("CEO", "agent.accept_commitment")
    assert (await view(crew))["commitment"]["state"] == "accepted"

    second = await command_requirement(crew, "signup", runs=40)
    shown = await view(crew)
    assert shown["commitment"]["state"] == "at risk"
    assert "10.0 hours later" in shown["commitment"]["beside_projection"]
    frozen = await crew.call("CEO", "agent.propose_requirement", **SCOPE)
    envelope = assert_refused(frozen, rule="PLN-8", code="scope_frozen")
    assert "The commitment is at risk" in envelope.message
    assert "the projection is" in envelope.message
    still = await crew.call("CEO", "agent.create_task", requirement_id=first, **TASK)
    assert still.status_code == 200, still.text
    await crew.ok(
        "CEO", "agent.kill_task", task_id=still.json()["id"], reason="Made only to show it can."
    )
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    assert any("The commitment is at risk" in line["body"] for line in lines)

    reset = await crew.ok("CEO", "agent.reset_commitment")
    assert reset["note"] == "This is reset number 1."
    assert reset["commitment"]["state"] == "accepted"
    assert reset["commitment"]["date"] == reset["pace"]["projected_at"]
    assert (await crew.call("CEO", "agent.propose_requirement", **SCOPE)).status_code == 200

    clock.advance(days=30)
    await crew.finish_all()
    await app.planning.tick()
    crew.owner = await app.login(crew.owner.email)
    assert (await view(crew))["commitment"]["state"] == "breached"
    async with app.runtime.sessions() as session:
        alarms = select(func.count()).select_from(Alarm).where(Alarm.level == "alarm")
        assert await session.scalar(alarms) == 1
    moved = await app.ok(
        "commitments.move", crew.owner, project_id=crew.project,
        date=(app.runtime.clock() + timedelta(days=60)).isoformat(),
    )  # fmt: skip
    assert moved["commitment"]["state"] == "accepted"

    for requirement, name in ((first, "pricing"), (second, "signup")):
        await meet(crew, clock, requirement, name)
    await app.planning.tick()
    done = await view(crew)
    assert done["commitment"]["state"] == "met"
    assert done["commitment"]["resets"] == 1


@pytest.mark.attack("GOV-10")
async def test_GOV_10_the_reserve_is_drawn_once_when_nearly_done(app: App) -> None:
    """GOV-10, GOV-3: the CEO draws the reserve only after wrap-up, only when at least
    `budget.reserve_min_done` of accepted requirements are met and the rest fits inside
    it, and only once. A half-finished project is refused with the arithmetic. The draw
    raises the wall but funds no new scope. The chairman can cancel it, and the project
    pauses if spend is already past the budget."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"budget.tokens": 1_000_000})
    ids = [crew.requirement] + [await command_requirement(crew, f"page{n}") for n in (2, 3, 4)]
    app.script("CEO/work", {"text": "Planning.", "usage": {"input": 20_000, "output": 0}})
    await app.ok("chat.command", crew.owner, project_id=crew.project, text="/do Plan it.")
    await app.work()

    async def draw() -> Any:
        return await crew.call("CEO", "agent.draw_reserve", reason="One page is left to finish.")

    await set_states(app, {ids[0]: "met", ids[1]: "met"})
    envelope = assert_refused(await draw(), rule="GOV-10", code="not_in_wrap_up")
    assert "wrap-up at 900,000 tokens" in envelope.message
    await spend(app, crew.project, 900_000)
    envelope = assert_refused(await draw(), rule="GOV-10", code="not_nearly_done")
    assert "2 of 4 accepted requirements are met (50%; `budget.reserve_min_done` is 75%)" in (
        envelope.message
    )
    assert (await view(crew))["reserve"]["can_draw"] is False

    await set_states(app, {ids[2]: "met"})
    drawn = await crew.ok("CEO", "agent.draw_reserve", reason="One page is left to finish.")
    assert drawn["reserve"]["draws"][0]["state"] == "drawn"
    assert drawn["reserve"]["draws"][0]["tokens"] == 100_000
    assert "3 of 4 accepted requirements are met (75%" in drawn["reserve"]["draws"][0]["arithmetic"]
    assert "so it fits" in drawn["reserve"]["draws"][0]["arithmetic"]
    assert (await app.ok("budget.show", crew.owner, project_id=crew.project))["wall"] == 1_100_000
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    assert any("The CEO drew the CEO reserve of 100,000 tokens" in m["body"] for m in lines)
    assert_refused(await draw(), rule="GOV-10", code="reserve_already_drawn")
    new_scope = await crew.call("CEO", "agent.propose_requirement", **SCOPE)
    assert_refused(new_scope, rule="GOV-3", code="wrap_up_mode")

    await spend(app, crew.project, 120_000)
    cancelled = await app.ok(
        "reserve.cancel", crew.owner, project_id=crew.project,
        draw_id=drawn["reserve"]["draws"][0]["id"],
    )  # fmt: skip
    assert cancelled["reserve"]["draws"][0]["state"] == "cancelled"
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "paused"
    budget = await app.ok("budget.show", crew.owner, project_id=crew.project)
    assert budget["wall"] == 1_000_000


@pytest.mark.attack("GOV-10")
async def test_GOV_10_plan_tokens_unknown_refuses_a_deliver_draw(app: App) -> None:
    """GOV-10, R-46: while no work run has finished anywhere, plan tokens are unknown, so
    a Deliver draw is refused even with three of four requirements met."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"budget.tokens": 1_000_000})
    ids = [crew.requirement] + [await command_requirement(crew, f"page{n}") for n in (2, 3, 4)]
    await set_states(app, dict.fromkeys(ids[:3], "met"))
    await spend(app, crew.project, 950_000)
    refused = await crew.call("CEO", "agent.draw_reserve", reason="One page is left to finish.")
    envelope = assert_refused(refused, rule="GOV-10", code="plan_tokens_unknown")
    assert "plan tokens are unknown" in envelope.message


@pytest.mark.attack("GOV-10")
async def test_GOV_10_under_supervised_the_chairman_answers_a_draw(app: App) -> None:
    """GOV-10, section 3: where `authority.reserve_draw` is chairman, the CEO's draw only
    asks. Nothing is drawn, at the wall the project pauses, and the chairman's approval
    draws it and lifts the wall. Other seats cannot draw at all."""
    crew = await Crew.start(
        app, settings={"budget.tokens": 1_000_000, "authority.reserve_draw": "chairman"}
    )
    ids = [crew.requirement] + [await command_requirement(crew, f"page{n}") for n in (2, 3, 4)]
    await crew.finish_all()
    app.script("CEO/work", {"text": "Planning.", "usage": {"input": 20_000, "output": 0}})
    await app.ok("chat.command", crew.owner, project_id=crew.project, text="/do Plan it.")
    await app.work()
    await set_states(app, dict.fromkeys(ids[:3], "met"))
    await spend(app, crew.project, 900_000)
    for seat in ("build-1", "Reviewer"):
        refused = await crew.call(seat, "agent.draw_reserve", reason="I would like more tokens.")
        assert refused.status_code == 403, seat
    asked = await crew.ok("CEO", "agent.draw_reserve", reason="One page is left to finish.")
    assert asked["reserve"]["draws"][0]["state"] == "requested"
    assert asked["note"] == "The chairman has been asked. Nothing is drawn until they approve."
    assert (await app.ok("budget.show", crew.owner, project_id=crew.project))["wall"] == 1_000_000

    app.script("CEO/work", {"text": "Working.", "usage": {"input": 90_000, "output": 0}})
    await crew.finish_all()
    await app.ok("chat.command", crew.owner, project_id=crew.project, text="/do Carry on.")
    await app.work()
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "paused"
    approved = await app.ok(
        "reserve.answer", crew.owner, project_id=crew.project,
        draw_id=asked["reserve"]["draws"][0]["id"], approve=True,
    )  # fmt: skip
    assert approved["reserve"]["draws"][0]["state"] == "drawn"
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "running"


@pytest.mark.parametrize(("met", "state", "draws"), [(3, "running", 1), (2, "paused", 0)])
async def test_GOV_10_at_the_wall_the_platform_draws_for_a_nearly_finished_project(
    app: App, met: int, state: str, draws: int
) -> None:
    """GOV-3, GOV-10 (the phase 5 exit demo): when the wall arrives, a project with three
    of four requirements met has its reserve drawn by the platform and keeps running. A
    half-finished one is not eligible, so it pauses."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"budget.tokens": 1_000_000})
    ids = [crew.requirement] + [await command_requirement(crew, f"page{n}") for n in (2, 3, 4)]
    app.script("CEO/work", {"text": "Planning.", "usage": {"input": 20_000, "output": 0}})
    await app.ok("chat.command", crew.owner, project_id=crew.project, text="/do Plan it.")
    await app.work()
    await set_states(app, dict.fromkeys(ids[:met], "met"))
    await spend(app, crew.project, 950_000)
    app.script("CEO/work", {"text": "Finishing.", "usage": {"input": 40_000, "output": 0}})
    await app.ok("chat.command", crew.owner, project_id=crew.project, text="/do Finish it.")
    await app.work()
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == state
    shown = await view(crew)
    assert len(shown["reserve"]["draws"]) == draws
    if draws:
        assert shown["reserve"]["draws"][0]["drawn_by"] == "platform"
        budget = await app.ok("budget.show", crew.owner, project_id=crew.project)
        assert budget["wall"] == 1_100_000


@pytest.mark.attack("GOV-5")
async def test_GOV_5_only_the_ceo_asks_for_a_raise(app: App) -> None:
    """GOV-5: only the CEO asks for a higher budget or concurrency. A budget raise is
    refused while less than half is used and the plan fits. The request carries its
    arithmetic and what happens if declined. Approving applies the change at the number
    the chairman grants, and a yes never lowers anything."""
    crew = await Crew.start(app, settings={"budget.tokens": 1_000_000})
    ask = {"what": "budget", "amount": 2_000_000, "if_declined": "The last page is not built."}
    for seat in ("build-1", "Reviewer"):
        assert (await crew.call(seat, "agent.request_raise", **ask)).status_code == 403, seat
    lower = await crew.call("CEO", "agent.request_raise", **ask | {"amount": 500_000})
    assert_refused(lower, rule="GOV-5", code="not_a_raise")
    early = await crew.call("CEO", "agent.request_raise", **ask)
    envelope = assert_refused(early, rule="GOV-5", code="raise_not_needed")
    assert "Less than half the budget is used" in envelope.message

    await spend(app, crew.project, 600_000)
    asked = await crew.ok("CEO", "agent.request_raise", **ask)
    request = asked["raises"][0]
    assert request["state"] == "pending"
    assert "600,000 of 1,000,000 tokens used (60%)" in request["arithmetic"]
    assert "Asked: 2,000,000 tokens." in request["arithmetic"]
    twice = await crew.call("CEO", "agent.request_raise", **ask)
    assert_refused(twice, rule="GOV-5", code="raise_already_asked")
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    assert any("If declined: The last page is not built." in m["body"] for m in lines)

    less = await app.call(
        "raises.answer", crew.owner, project_id=crew.project, request_id=request["id"],
        approve=True, amount=900_000,
    )  # fmt: skip
    assert_refused(less, rule="GOV-5", code="a_yes_never_lowers")
    granted = await app.ok(
        "raises.answer", crew.owner, project_id=crew.project, request_id=request["id"],
        approve=True, amount=1_500_000,
    )  # fmt: skip
    assert (granted["raises"][0]["state"], granted["raises"][0]["granted"]) == (
        "approved",
        1_500_000,
    )
    assert (await app.ok("budget.show", crew.owner, project_id=crew.project))["wall"] == 1_500_000

    more = await crew.ok(
        "CEO", "agent.request_raise", what="concurrency", amount=8,
        if_declined="The work takes twice as long.",
    )  # fmt: skip
    declined = await app.ok(
        "raises.answer", crew.owner, project_id=crew.project, request_id=more["raises"][1]["id"],
        approve=False,
    )  # fmt: skip
    assert declined["raises"][1]["state"] == "declined"
    events = [e for e in await app.events(crew.owner, crew.project) if e["type"] == "raise.changed"]
    assert [e["after"]["state"] for e in events] == ["pending", "approved", "pending", "declined"]


@pytest.mark.attack("WRK-11")
async def test_WRK_11_the_final_gap_review_blocks_readiness(app: App, clock: FakeClock) -> None:
    """WRK-11, PRJ-4: with all scope met, a Deliver project is not ready until a reviewer
    seat that wrote none of the deliverables has filed the final gap review. Nobody else
    can file it. A must-fix gap becomes a proposed, CEO-authored requirement and blocks
    readiness until it is met or the chairman waives it; a nice-to-have gap does not."""
    crew = await Crew.start(app, team=False, settings=SOLO)
    await set_states(app, {crew.requirement: "cut"})
    wanted = await command_requirement(crew, "pricing")
    await crew.ok(
        "CEO", "agent.publish_artifact", name="pricing.md", content="# Pricing",
        purpose="The pricing page",
    )  # fmt: skip
    await meet(crew, clock, wanted, "pricing")
    await app.planning.tick()
    shown = await view(crew)
    assert shown["requirements"][1]["state"] == "met"
    assert shown["gap_review"] == "waiting for the reviewer"
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "running"

    gaps = [
        {"text": "The page has no prices on it.", "must_fix": True, "reason": "The goal asks."},
        {"text": "The page could use a table.", "must_fix": False, "reason": "Easier to read."},
    ]
    own = await crew.call("CEO", "agent.file_gap_review", gaps=[])
    assert_refused(own, rule="WRK-11", code="not_your_review")
    vague = await crew.call(
        "Reviewer", "agent.file_gap_review", gaps=[gaps[0] | {"reason": "Because."}]
    )
    assert_refused(vague, rule="WRK-11", code="gap_needs_a_reason")
    filed = await crew.ok("Reviewer", "agent.file_gap_review", gaps=gaps)
    assert [(g["must_fix"], g["state"]) for g in filed["gaps"]] == [
        (True, "open"),
        (False, "noted"),
    ]
    born = filed["requirements"][-1]
    assert (born["state"], born["author"]) == ("proposed", "ceo")
    assert filed["gaps"][0]["requirement_id"] == born["id"]
    twice = await crew.call("Reviewer", "agent.file_gap_review", gaps=[])
    assert_refused(twice, rule="WRK-11", code="not_your_review")

    clock.advance(minutes=1)
    await app.planning.tick()
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "running"
    token = (await crew.call("CEO", "agent.whoami")).request.headers["Authorization"][7:]
    waive = {"gap_id": filed["gaps"][0]["id"], "reason": "Prices are set next quarter."}
    by_agent = await app.call("gaps.waive", token, project_id=crew.project, **waive)
    assert by_agent.status_code in (401, 403)
    waived = await app.ok("gaps.waive", crew.owner, project_id=crew.project, **waive)
    assert waived["gaps"][0]["state"] == "waived"
    assert waived["requirements"][-1]["state"] == "declined"
    await crew.finish_all()
    await app.planning.tick()
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "ready"
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    assert any("Deliverables: pricing.md" in line["body"] for line in lines)


@pytest.mark.attack("PRJ-6")
async def test_PRJ_6_a_completed_project_reopens_only_in_its_window(
    app: App, clock: FakeClock
) -> None:
    """PRJ-4, PRJ-5, PRJ-6: a ready project leases no work run and completes by itself
    after `completion.auto_after`. It is reopened within `reopen.window`; after that the
    answer is to clone it. Only the chairman signs off or reopens."""
    crew = await Crew.start(app, team=False, settings=SOLO)
    await set_states(app, {crew.requirement: "cut"})
    wanted = await command_requirement(crew, "pricing")
    await meet(crew, clock, wanted, "pricing")
    await app.planning.tick()
    await crew.ok("Reviewer", "agent.file_gap_review", gaps=[])
    await crew.finish_all()
    await app.planning.tick()
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "ready"

    from tests.support import wake

    await wake(app, crew.project, "CEO")
    app.script("*", {"text": "Nothing."})
    assert await app.work() == 0
    clock.advance(hours=23)
    await app.planning.tick()
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "ready"
    clock.advance(hours=2)
    await app.planning.tick()
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "completed"
    receipt = await app.ok("projects.receipt", crew.owner, project_id=crew.project)
    assert receipt["completed"] is True
    assert receipt["receipt"]["requirements"][-1]["estimate_runs"] == 2

    clock.advance(days=13)
    crew.owner = await app.login(crew.owner.email)
    await app.ok("projects.reopen", crew.owner, project_id=crew.project)
    status = await app.ok("projects.status", crew.owner, project_id=crew.project)
    assert status["state"] == "running"
    await app.planning.tick()
    await app.ok("projects.sign_off", crew.owner, project_id=crew.project)
    clock.advance(days=15)
    crew.owner = await app.login(crew.owner.email)
    late = await app.call("projects.reopen", crew.owner, project_id=crew.project)
    envelope = assert_refused(late, rule="PRJ-6", code="reopen_window_passed")
    assert envelope.hint == "Clone it into a new project instead."


async def test_PLN_9_a_target_date_reaches_the_ceo_beside_the_projection(app: App) -> None:
    """PLN-9, PLN-1: a chairman target date is stored with its source and is not a
    commitment. The CEO's context pack shows it beside the platform's projection and the
    gap, with the plan it needs to create work. A target without a source is refused."""
    crew = await solo(app)
    await set_states(app, {crew.requirement: "cut"})
    await command_requirement(crew, "pricing", runs=8)
    bare = await app.call(
        "plan.set_target", crew.owner, project_id=crew.project, date="2026-11-21T10:00:00Z"
    )
    assert bare.status_code == 422
    shown = await app.ok(
        "plan.set_target", crew.owner, project_id=crew.project, date="2026-11-21T10:00:00Z",
        source="The trade fair opens then.",
    )  # fmt: skip
    assert shown["commitment"] is None
    assert shown["target"]["source"] == "The trade fair opens then."
    beside = "21 Nov 2026 10:00 UTC; the projection is 21 Nov 2026 11:00 UTC, 1.0 hours later"
    assert shown["target"]["beside_projection"] == beside
    pack = (await crew.ok("CEO", "agent.context"))["context_pack"]
    assert f"The chairman's target date (The trade fair opens then.): {beside}." in pack
    assert "A target is a wish, not a pace" in pack
    assert "- 2 (accepted, stage 1, by the chairman, 8 runs, ready for work)" in pack
    cleared = await app.ok("plan.set_target", crew.owner, project_id=crew.project)
    assert cleared["target"] is None
