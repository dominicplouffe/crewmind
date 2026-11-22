"""Attacks on flags, mistake reports and status reviews (HUM-6, HUM-8, HUM-9)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.attack.delivery_support import SOLO, spend
from tests.attack.harness import assert_refused
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App


async def items_of(crew: Crew, kind: str, open_only: bool = True) -> list[dict[str, Any]]:
    listed = await crew.app.ok(
        "items.list", crew.owner, project_id=crew.project, kind=kind, open_only=open_only
    )
    return listed["items"]


async def later(crew: Crew, clock: FakeClock, **delta: float) -> None:
    clock.advance(**delta)
    await crew.finish_all()
    await crew.app.planning.tick()
    crew.owner = await crew.app.login(crew.owner.email)


async def said_and_corrected(crew: Crew, **more: Any) -> dict[str, Any]:
    """The chairman asks, the CEO answers, and the chairman says it was not what they asked."""
    app = crew.app
    app.script("CEO/chat", {"text": "We have twelve offices."})
    await app.ok("chat.send", crew.owner, project_id=crew.project, body="How many offices?")
    await app.work()
    fixed = await app.ok(
        "corrections.record", crew.owner, project_id=crew.project,
        words="I asked about shops, not offices.", **more,
    )  # fmt: skip
    await app.work()
    return fixed


@pytest.mark.attack("HUM-6")
async def test_HUM_6_a_state_flag_closes_only_when_its_condition_clears(
    app: App, clock: FakeClock
) -> None:
    """HUM-6, 7.5: flags open from arithmetic, one per condition. The chairman acknowledges
    a flag only after the CEO has raised it with a proposal, and neither of them closes a
    state flag: it clears when its condition does. No operation lets an agent open one."""
    crew = await Crew.start(app, settings={"budget.tokens": 1_000_000})
    await spend(app, crew.project, 900_000)
    await later(crew, clock, minutes=1)
    (flag,) = [f for f in await items_of(crew, "flag") if f["fields"]["flag"] == "budget wrap-up"]
    assert (flag["fields"]["type"], flag["title"]) == ("state", "Flag: budget wrap-up")
    assert (flag["actions"], flag["waits_on_you"]) == ([], False)

    async def acknowledge() -> Any:
        return await app.call(
            "items.decide", crew.owner, project_id=crew.project, item_id=flag["id"],
            action="acknowledge",
        )  # fmt: skip

    assert_refused(await acknowledge(), rule="HUM-1", code="not_yet")
    by_lead = await crew.call(
        "build-1", "agent.raise_flag", item_id=flag["id"], proposal="Stop the extra pages now."
    )
    assert by_lead.status_code == 403
    bare = await crew.call("CEO", "agent.raise_flag", item_id=flag["id"], proposal="Noted.")
    assert_refused(bare, rule="HUM-6", code="flag_needs_a_proposal")
    raised = await crew.ok(
        "CEO", "agent.raise_flag", item_id=flag["id"],
        proposal="I will cut the about page and land the rest.",
    )  # fmt: skip
    assert raised["state"] == "raised"
    assert (await acknowledge()).json()["state"] == "acknowledged"

    await later(crew, clock, minutes=5)
    same = [f for f in await items_of(crew, "flag") if f["fields"]["flag"] == "budget wrap-up"]
    assert [(f["id"], f["state"]) for f in same] == [(flag["id"], "acknowledged")]
    await app.ok(
        "settings.change_project", crew.owner, project_id=crew.project,
        changes={"budget.tokens": 3_000_000}, reason="The work is worth more budget.",
    )  # fmt: skip
    await later(crew, clock, minutes=1)
    closed = await app.ok("items.show", crew.owner, project_id=crew.project, item_id=flag["id"])
    assert closed["state"] == "cleared"
    assert [line["state"] for line in closed["history"]] == [
        "open",
        "raised",
        "acknowledged",
        "cleared",
    ]


async def test_HUM_6_an_event_flag_closes_when_raised_and_acknowledged(
    app: App, clock: FakeClock
) -> None:
    """HUM-6: an agent corrected more than `listening.flag_at` times in 7 days gets a
    listening flag. It is an event flag: raised by the CEO and acknowledged by the
    chairman, it is closed."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"listening.flag_at": 1})
    await said_and_corrected(crew)
    await later(crew, clock, minutes=1)
    assert [f for f in await items_of(crew, "flag") if f["fields"]["flag"] == "listening"] == []
    await app.ok(
        "corrections.record", crew.owner, project_id=crew.project, words="Still not about shops."
    )
    await later(crew, clock, minutes=1)
    found = [f for f in await items_of(crew, "flag") if f["fields"]["flag"] == "listening"]
    (flag,) = found
    assert flag["fields"]["cause"] == "CEO was corrected 2 times in 7 days."
    await crew.ok(
        "CEO", "agent.raise_flag", item_id=flag["id"],
        proposal="I will restate each question before I answer it.",
    )  # fmt: skip
    await app.ok(
        "items.decide", crew.owner, project_id=crew.project, item_id=flag["id"],
        action="acknowledge",
    )  # fmt: skip
    await later(crew, clock, minutes=1)
    everything = await items_of(crew, "flag", open_only=False)
    (closed,) = [f for f in everything if f["fields"]["flag"] == "listening"]
    assert (closed["state"], closed["actions"]) == ("acknowledged", [])


@pytest.mark.attack("HUM-8")
async def test_HUM_8_the_ceo_owes_a_mistake_report_and_files_it_once(
    app: App, clock: FakeClock
) -> None:
    """HUM-8, HUM-6, MEM-1, 7.5: a correction the chairman marks as costly opens a mistake
    report with the platform's own token cost. Only the CEO files it, with every part, and
    only once. Unfiled after 24 hours it raises a flag. The prevention becomes a pinned
    lesson in every later context pack."""
    crew = await Crew.start(app)
    await said_and_corrected(crew, cost_us=True)
    (report,) = await items_of(crew, "mistake report")
    assert report["title"] == "Mistake report owed: the chairman marked correction 1 as costly"
    assert report["fields"]["cost_tokens"] > 0
    assert report["actions"] == []

    await later(crew, clock, hours=25)
    owed = [f for f in await items_of(crew, "flag") if f["fields"]["flag"] == "mistake report owed"]
    assert len(owed) == 1
    parts = {
        "item_id": report["id"],
        "what_was_wrong": "I answered about offices when asked about shops.",
        "cause": "I matched the question to an earlier one about offices.",
        "fix": "I answered again with the number of shops.",
        "prevention": "Restate the question in one line before answering it.",
    }
    assert (await crew.call("build-1", "agent.file_mistake_report", **parts)).status_code == 403
    thin = await crew.call("CEO", "agent.file_mistake_report", **parts | {"cause": "Oops."})
    assert_refused(thin, rule="HUM-8", code="report_incomplete")
    filed = await crew.ok("CEO", "agent.file_mistake_report", **parts)
    assert (filed["state"], filed["fields"]["prevention"]) == ("filed", parts["prevention"])
    again = await crew.call(
        "CEO", "agent.file_mistake_report", **parts | {"cause": "A different story this time."}
    )
    assert_refused(again, rule="7.5")
    pack = (await crew.ok("build-1", "agent.context"))["context_pack"]
    assert f"- [lesson {report['id']}] Restate the question in one line" in pack
    await later(crew, clock, minutes=1)
    assert [
        f for f in await items_of(crew, "flag") if f["fields"]["flag"] == "mistake report owed"
    ] == []


@pytest.mark.attack("HUM-9")
async def test_HUM_9_a_status_review_is_frozen(app: App, clock: FakeClock) -> None:
    """HUM-9: the platform builds a review every `review.every` at 0 tokens, with a frozen
    snapshot. One with something at risk stays open; the CEO adds a narrative, the
    chairman records levers with reasons, and no agent can. The next review shows the
    last one's levers. A green review closes itself after 24 hours."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"review.every": 86_400})
    spent = (await app.ok("budget.show", crew.owner, project_id=crew.project))["spent"]
    await later(crew, clock, days=1, minutes=1)
    (review,) = await items_of(crew, "status review")
    assert review["fields"]["green"] is False
    assert "slow start" in review["fields"]["numbers"]["flags"]
    assert (review["deadline"], review["fields"]["narrative"]) == (None, None)
    assert (await app.ok("budget.show", crew.owner, project_id=crew.project))["spent"] == spent

    await spend(app, crew.project, 123_456)
    lever = {"item_id": review["id"], "lever": "cut", "reason": "The about page can wait."}
    token = (await crew.call("CEO", "agent.whoami")).request.headers["Authorization"][7:]
    by_agent = await app.call("reviews.lever", token, project_id=crew.project, **lever)
    assert by_agent.status_code in (401, 403)
    vague = await app.call(
        "reviews.lever", crew.owner, project_id=crew.project, **lever | {"reason": "Yes."}
    )
    assert_refused(vague, rule="HUM-9", code="lever_needs_a_reason")
    await crew.ok(
        "CEO", "agent.write_review_narrative", item_id=review["id"],
        text="Nothing was claimed because the first requirement had no task yet.",
    )  # fmt: skip
    used = await app.ok("reviews.lever", crew.owner, project_id=crew.project, **lever)
    assert used["fields"]["levers"] == [{"lever": "cut", "reason": "The about page can wait."}]
    assert used["fields"]["numbers"]["spent"] == review["fields"]["numbers"]["spent"]
    await app.ok(
        "items.decide", crew.owner, project_id=crew.project, item_id=review["id"], action="close"
    )
    await later(crew, clock, days=1, minutes=1)
    (second,) = await items_of(crew, "status review")
    assert second["fields"]["number"] == 2
    assert second["fields"]["previous_levers"] == used["fields"]["levers"]
    assert second["fields"]["numbers"]["spent"] == spent + 123_456

    explore = await Crew.start(
        app, type="explore", team=False, owner=crew.owner, settings={"review.every": 86_400}
    )
    await later(explore, clock, days=1, minutes=1)
    (green,) = await items_of(explore, "status review")
    assert (green["fields"]["green"], green["default_outcome"]) == (True, "close")
    await later(explore, clock, hours=25)
    closed = await items_of(explore, "status review", open_only=False)
    assert (closed[0]["state"], closed[0]["outcome"]) == ("defaulted", "close")
