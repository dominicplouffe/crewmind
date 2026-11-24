"""Attacks on Explore: bets, the time box and findings (PRJ-7, SPD-7, GOV-10, INV-18,
section 7.4)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.attack.delivery_support import spend, view
from tests.attack.harness import assert_refused
from tests.attack.work_support import OBSERVABLE, Squad
from tests.conftest import FakeClock
from tests.support import App

BET = {
    "statement": "Agencies will pay for a weekly summary of their reviews.",
    "kill_condition": "Fewer than two of ten agencies agree to a paid pilot.",
}
EVIDENCE_TASK = OBSERVABLE | {"outside_evidence": True}


@pytest.mark.attack("SPD-7")
async def test_SPD_7_no_new_bet_in_the_final_fifth_of_the_time_box(
    app: App, clock: FakeClock
) -> None:
    """SPD-7, 7.4, PRJ-7: only the CEO opens a bet, only in an Explore project, with a
    kill date inside the time box. In the final 20% of the time box a new bet is refused
    with the dates."""
    squad = await Squad.start(app, type="explore", team=False)
    assert (await view(squad))["time_box"]["ends_at"].startswith("2026-11-28T09:00")
    assert (await squad.call("Reviewer", "agent.open_bet", **BET)).status_code == 403
    long = await squad.call("CEO", "agent.open_bet", window_hours=200, **BET)
    assert_refused(long, rule="SPD-7", code="bet_outlives_the_time_box")
    opened = await squad.ok("CEO", "agent.open_bet", window_hours=24, **BET)
    assert [bet["state"] for bet in opened["bets"]] == ["active", "active"]

    clock.advance(days=5, hours=15)
    await squad.finish_all()
    late = await squad.call("CEO", "agent.open_bet", window_hours=4, **BET)
    envelope = assert_refused(late, rule="SPD-7", code="time_box_nearly_over")
    assert "The time box ends on 28 Nov 2026 09:00 UTC" in envelope.message
    assert "its final 20% began on 26 Nov 2026 23:24 UTC" in envelope.message

    deliver = await Squad.start(app, team=False, owner=await app.login(squad.owner.email))
    wrong = await deliver.call("CEO", "agent.open_bet", **BET)
    assert_refused(wrong, rule="PRJ-7", code="bets_are_for_explore")


@pytest.mark.attack("PRJ-7")
@pytest.mark.attack("7.4")
async def test_PRJ_7_a_bet_expires_and_is_extended_once(app: App, clock: FakeClock) -> None:
    """PRJ-7, 7.4, INV-18: a task in an Explore project serves an active bet. At its kill
    date a bet expires and its open tasks block. Only the chairman extends it, once, with
    a reason. A confirmed finding needs verified evidence, and a bet that has its finding
    takes no other."""
    squad = await Squad.start(app, type="explore", team=False)
    bare = await squad.call("CEO", "agent.create_task", bet_id=None, **EVIDENCE_TASK)
    assert_refused(bare, rule="INV-18", code="task_needs_a_bet")
    task = await squad.ok("CEO", "agent.create_task", **EVIDENCE_TASK)
    assert task["bet_id"] == squad.bet

    clock.advance(hours=49)
    await squad.finish_all()
    await app.planning.tick()
    squad.owner = await app.login(squad.owner.email)
    assert (await view(squad))["bets"][0]["state"] == "expired"
    assert (await squad.show(task["id"]))["state"] == "blocked"
    more = await squad.call("CEO", "agent.create_task", **EVIDENCE_TASK)
    assert_refused(more, rule="INV-18", code="bet_not_active")

    until = (app.runtime.clock() + timedelta(hours=12)).isoformat()
    token = (await squad.call("CEO", "agent.whoami")).request.headers["Authorization"][7:]
    by_agent = await app.call(
        "bets.extend", token, project_id=squad.project, bet_id=squad.bet, until=until,
        reason="I need more time for it.",
    )  # fmt: skip
    assert by_agent.status_code in (401, 403)
    short = await app.call(
        "bets.extend", squad.owner, project_id=squad.project, bet_id=squad.bet, until=until,
        reason="More.",
    )  # fmt: skip
    assert_refused(short, rule="PRJ-7", code="reason_too_short")
    extended = await app.ok(
        "bets.extend", squad.owner, project_id=squad.project, bet_id=squad.bet, until=until,
        reason="Two interviews are booked for tomorrow.",
    )  # fmt: skip
    assert (extended["bets"][0]["state"], extended["bets"][0]["extended"]) == ("active", True)

    clock.advance(hours=13)
    await squad.finish_all()
    await app.planning.tick()
    again = await app.call(
        "bets.extend", squad.owner, project_id=squad.project, bet_id=squad.bet,
        until=(app.runtime.clock() + timedelta(hours=12)).isoformat(),
        reason="Two more interviews are booked.",
    )  # fmt: skip
    assert_refused(again, rule="PRJ-7", code="bet_already_extended")

    finding = {"bet_id": squad.bet, "text": "Three of ten agencies asked for a paid pilot."}
    unproven = await squad.call("CEO", "agent.publish_finding", result="confirmed", **finding)
    assert_refused(unproven, rule="PRJ-7", code="confirmed_needs_evidence")
    invented = await squad.call(
        "CEO", "agent.publish_finding", result="confirmed", evidence=[41], **finding
    )
    assert_refused(invented, rule="PRJ-7", code="evidence_not_verified")
    published = await squad.ok("CEO", "agent.publish_finding", result="inconclusive", **finding)
    assert published["note"] == f"Published as finding-bet-{squad.bet}.md."
    assert published["bets"][0]["state"] == "inconclusive"
    assert (await squad.show(task["id"]))["state"] == "killed"
    twice = await squad.call("CEO", "agent.publish_finding", result="killed", **finding)
    assert_refused(twice, rule="7.4")


@pytest.mark.attack("GOV-10")
async def test_GOV_10_an_explore_draw_funds_findings_only(app: App) -> None:
    """GOV-10, R-46: in an Explore project the reserve funds findings for bets already
    active. After the draw no bet may be opened, and a task may serve only an active bet."""
    squad = await Squad.start(
        app, type="explore", team=False, settings={"budget.tokens": 1_000_000}
    )
    await spend(app, squad.project, 900_000)
    drawn = await squad.ok("CEO", "agent.draw_reserve", reason="One bet needs its finding.")
    assert drawn["reserve"]["draws"][0]["state"] == "drawn"
    assert "1 active bets get their findings" in drawn["reserve"]["draws"][0]["arithmetic"]
    refused = await squad.call("CEO", "agent.open_bet", **BET)
    assert_refused(refused, rule="GOV-10", code="reserve_funds_findings_only")
    task = await squad.call("CEO", "agent.create_task", **EVIDENCE_TASK)
    assert task.status_code == 200, task.text
