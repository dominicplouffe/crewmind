"""Attacks on decision items: defaults, authority, questions, assists and spend (HUM-1 to
HUM-5, HUM-7, SPD-5, WRK-10, GOV-8, INV-10, INV-17, section 7.5)."""

from __future__ import annotations

from typing import Any

import pytest

from crewmind.domain.decisions import items
from tests.attack.delivery_support import SOLO, spend
from tests.attack.harness import assert_refused
from tests.attack.test_planning import CHAIRMAN_HOLDS, TASK, plan, propose
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App

QUESTION = {
    "question": "Should the pricing page list yearly prices too?",
    "why": "It decides how much of the page must be rebuilt later.",
    "options": ["Monthly only", "Monthly and yearly"],
    "recommended": 1,
    "default": "I will build the page with monthly prices only.",
    "concerns": "accept_scope",
}
BASIS = {"kind": "command", "ref": "curl -s https://example.com/price prints 150.00"}


async def open_items(crew: Crew, **more: Any) -> list[dict[str, Any]]:
    listed = await crew.app.ok("items.list", crew.owner, project_id=crew.project, **more)
    return listed["items"]


async def decide(crew: Crew, item: int, action: str, **more: Any) -> dict[str, Any]:
    return await crew.app.ok(
        "items.decide", crew.owner, project_id=crew.project, item_id=item, action=action, **more
    )


async def later(crew: Crew, clock: FakeClock, **delta: float) -> None:
    clock.advance(**delta)
    await crew.finish_all()
    await crew.app.planning.tick()
    crew.owner = await crew.app.login(crew.owner.email)


@pytest.mark.attack("INV-17")
@pytest.mark.attack("HUM-1")
@pytest.mark.attack("7.5")
async def test_INV_17_an_unanswered_item_resolves_to_its_declared_default(
    app: App, clock: FakeClock
) -> None:
    """INV-17, HUM-1, HUM-2, 7.5, R-57: scope the CEO proposes where the chairman holds
    plan authority is a decision item with typed actions, a deadline and a default. No
    agent decides it, an action it does not have is refused, and unanswered for 72 hours
    it is declined. A tool-permission item never resolves to allow, and a kind whose
    default would grant something cannot even be registered."""
    crew = await Crew.start(app, settings=CHAIRMAN_HOLDS)
    wanted, ignored = await propose(crew), await propose(crew, text="A second pricing page.")
    first, second = await open_items(crew)
    assert (first["kind"], first["title"]) == (
        "proposed scope",
        f"Proposed scope: requirement {wanted}, 4 runs",
    )
    assert first["actions"] == ["accept", "accept anyway", "decline"]
    assert (first["default_outcome"], first["waits_on_you"]) == ("decline", True)
    assert first["deadline"].startswith("2026-11-24T09:00")

    token = (await crew.call("CEO", "agent.whoami")).request.headers["Authorization"][7:]
    by_agent = await app.call(
        "items.decide", token, project_id=crew.project, item_id=first["id"], action="accept"
    )
    assert by_agent.status_code in (401, 403)
    wrong = await app.call(
        "items.decide", crew.owner, project_id=crew.project, item_id=first["id"], action="grant"
    )
    assert_refused(wrong, rule="HUM-1", code="not_an_action")
    decided = await decide(crew, first["id"], "accept", note="Go ahead.")
    assert (decided["state"], decided["outcome"], decided["actions"]) == ("decided", "accept", [])
    assert (await plan(crew))[wanted]["state"] == "accepted"
    again = await app.call(
        "items.decide", crew.owner, project_id=crew.project, item_id=first["id"], action="decline"
    )
    assert_refused(again, rule="7.5")

    tool = await crew.ok(
        "build-1", "agent.request_approval", kind="tool permission", tool="send_invoice",
        recommendation="Allow me to send invoices.", if_declined="Invoices are sent by hand.",
    )  # fmt: skip
    await later(crew, clock, hours=73)
    shown = await app.ok("items.show", crew.owner, project_id=crew.project, item_id=second["id"])
    assert (shown["state"], shown["outcome"]) == ("defaulted", "decline")
    assert [line["state"] for line in shown["history"]] == ["open", "defaulted"]
    declined = (await plan(crew))[ignored]
    assert (declined["state"], declined["reason"]) == ("declined", "Not accepted by its deadline.")
    await later(crew, clock, days=5)
    shown = await app.ok("items.show", crew.owner, project_id=crew.project, item_id=tool["id"])
    assert (shown["state"], shown["outcome"]) == ("defaulted", "deny")

    with pytest.raises(ValueError, match="a default may not be"):
        items.register(
            items.Kind(
                name="approval: sample",
                filed_by="agent",
                actions=("approve", "deny"),
                default="approve",
                title=lambda fields: "Sample",
                positive=("approve",),
            )
        )


@pytest.mark.attack("HUM-3")
async def test_HUM_3_only_an_open_approval_is_extended(app: App) -> None:
    """HUM-3: an approval's deadline is extended by 1 to 30 days with a reason. A question
    is not an approval, and a decided item cannot be extended."""
    crew = await Crew.start(app, settings=CHAIRMAN_HOLDS)
    tool = await crew.ok(
        "build-1", "agent.request_approval", kind="tool permission", tool="send_invoice",
        recommendation="Allow me to send invoices.", if_declined="Invoices are sent by hand.",
    )  # fmt: skip
    asked = await crew.ok("CEO", "agent.ask_question", **QUESTION)

    async def extend(item: int, days: int, reason: str) -> Any:
        return await app.call(
            "items.extend", crew.owner, project_id=crew.project, item_id=item, days=days,
            reason=reason,
        )  # fmt: skip

    assert_refused(await extend(tool["id"], 31, "I am away this month."), rule="HUM-3")
    assert_refused(await extend(tool["id"], 5, "Later."), rule="HUM-3")
    assert_refused(await extend(asked["id"], 5, "I am away this week."), rule="HUM-3")
    longer = await extend(tool["id"], 5, "I am away this week.")
    assert longer.json()["deadline"].startswith("2026-12-03T09:00")
    await decide(crew, tool["id"], "deny")
    assert_refused(await extend(tool["id"], 5, "I am away this week."), rule="HUM-3")


@pytest.mark.attack("HUM-4")
@pytest.mark.attack("HUM-5")
async def test_HUM_5_a_question_never_blocks_and_never_asks_what_the_ceo_holds(
    app: App, clock: FakeClock
) -> None:
    """HUM-4, HUM-5, SPD-5, R-27: the CEO is refused a question about a decision it holds.
    Where the chairman holds it, the CEO asks and carries on at once. At most
    `question.max_open` are open. An answer that differs from the default is said so and
    the rework is recorded against the question. Unanswered, the default stands on the
    record and the platform does nothing else: no scope is accepted by silence."""
    held = await Crew.start(app, team=False, settings=SOLO)
    own = await held.call("CEO", "agent.ask_question", **QUESTION)
    envelope = assert_refused(own, rule="HUM-4", code="you_hold_this_decision")
    assert envelope.message == "You hold this decision. Decide it and post a heads-up."
    told = await held.ok("CEO", "agent.post_heads_up", text="I accepted the pricing page scope.")
    assert (told["kind"], told["waits_on_you"], told["deadline"]) == ("heads-up", False, None)

    crew = await Crew.start(app, settings=CHAIRMAN_HOLDS, owner=held.owner)
    assert (await crew.call("build-1", "agent.ask_question", **QUESTION)).status_code == 403
    thin = await crew.call("CEO", "agent.ask_question", **QUESTION | {"why": "Because."})
    assert_refused(thin, rule="HUM-5", code="question_incomplete")
    vague = await crew.call("CEO", "agent.ask_question", **QUESTION | {"concerns": "things"})
    assert_refused(vague, rule="HUM-4", code="concerns_unknown")
    first = await crew.ok("CEO", "agent.ask_question", **QUESTION)
    assert (first["default_outcome"], first["deadline"][:16]) == (
        "the default stands",
        "2026-11-22T09:00",
    )
    proposed = await propose(crew)
    task = await crew.call("CEO", "agent.create_task", team="build", **TASK)
    assert task.status_code == 200, task.text
    for _ in range(2):
        await crew.ok("CEO", "agent.ask_question", **QUESTION | {"concerns": "other"})
    fourth = await crew.call("CEO", "agent.ask_question", **QUESTION)
    assert_refused(fourth, rule="HUM-5", code="too_many_questions")

    answered = await decide(crew, first["id"], "answer", option=2, note="Customers ask for it.")
    assert answered["state"] == "decided"
    pack = (await crew.ok("CEO", "agent.context"))["context_pack"]
    assert "Monthly and yearly Customers ask for it." in pack
    assert "This differs from the default you acted on." in pack
    await crew.ok(
        "CEO", "agent.record_rework", item_id=first["id"], what="Rebuilt the price table."
    )
    shown = await app.ok("items.show", crew.owner, project_id=crew.project, item_id=first["id"])
    assert shown["fields"]["concerns"] == "accept_scope"

    await later(crew, clock, hours=13)
    await later(crew, clock, hours=12)
    lapsed = [
        item for item in await open_items(crew, open_only=False) if item["kind"] == "question"
    ]
    assert [item["state"] for item in lapsed] == ["decided", "defaulted", "defaulted"]
    assert (await plan(crew))[proposed]["state"] == "proposed"


@pytest.mark.attack("WRK-10")
@pytest.mark.attack("GOV-8")
@pytest.mark.attack("INV-10")
async def test_GOV_8_real_world_spend_stays_under_its_cap_and_threshold(app: App) -> None:
    """GOV-8, INV-10, WRK-10, HUM-3: spend is off until the chairman turns it on. A
    purchase at or above `spend.approval_at` needs an approved spend item, and that item
    is refused without the basis of its amount. No approval lets committed spend pass
    `spend.monthly_cap`. Only the declaring seat settles a purchase, and a cancelled one
    stops counting. Spend approvals stay with the chairman under autonomous authority."""
    crew = await Crew.start(app)
    off = await crew.call("CEO", "agent.declare_purchase", what="A domain name", amount=12)
    assert_refused(off, rule="GOV-8", code="spend_is_off")
    await app.ok(
        "settings.change_project", crew.owner, project_id=crew.project,
        changes={"spend.enabled": True}, reason="The crew may buy small things.",
    )  # fmt: skip
    small = await crew.ok("CEO", "agent.declare_purchase", what="A domain name", amount=50)
    assert (small["state"], small["committed_this_month"], small["monthly_cap"]) == (
        "committed",
        50.0,
        500.0,
    )
    big = {"what": "A year of hosting", "amount": 150}
    unapproved = await crew.call("CEO", "agent.declare_purchase", **big)
    assert_refused(unapproved, rule="GOV-8", code="needs_spend_approval")

    ask = {
        "kind": "spend", "amount": 150, "recommendation": "Approve a year of hosting.",
        "if_declined": "The site stays on the free plan.",
    }  # fmt: skip
    assert (await crew.call("build-1", "agent.request_approval", **ask)).status_code == 403
    bare = await crew.call("CEO", "agent.request_approval", **ask)
    assert_refused(bare, rule="WRK-10", code="figure_needs_a_basis")
    item = await crew.ok("CEO", "agent.request_approval", **ask, basis=BASIS)
    assert (item["title"], item["default_outcome"]) == ("Spend 150.00 USD", "deny")
    await decide(crew, item["id"], "approve")
    bought = await crew.ok("CEO", "agent.declare_purchase", **big)
    assert bought["committed_this_month"] == 200.0
    twice = await crew.call("CEO", "agent.declare_purchase", **big)
    assert_refused(twice, rule="GOV-8", code="needs_spend_approval")

    huge = await crew.ok("CEO", "agent.request_approval", **ask | {"amount": 400}, basis=BASIS)
    await decide(crew, huge["id"], "approve")
    over = await crew.call("CEO", "agent.declare_purchase", what="A big server", amount=400)
    envelope = assert_refused(over, rule="INV-10", code="over_the_monthly_cap")
    assert "committed spend to 600.00 USD; `spend.monthly_cap` is 500.00 USD" in envelope.message

    other = await crew.call(
        "build-1", "agent.finish_purchase", purchase_id=bought["id"], bought=False
    )
    assert_refused(other, rule="GOV-8", code="not_your_open_purchase")
    cancelled = await crew.ok(
        "CEO", "agent.finish_purchase", purchase_id=bought["id"], bought=False
    )
    assert (cancelled["state"], cancelled["committed_this_month"]) == ("cancelled", 50.0)
    fits = await crew.ok("CEO", "agent.declare_purchase", what="A big server", amount=400)
    assert fits["committed_this_month"] == 450.0
    shown = await app.ok("spend.show", crew.owner, project_id=crew.project)
    assert [p["state"] for p in shown["purchases"]] == ["committed", "cancelled", "committed"]


async def test_HUM_7_an_assist_holds_one_task_and_nothing_else(app: App) -> None:
    """HUM-7, HUM-2: any agent may ask for a step only a human can do. The project goes on
    meanwhile. When the chairman cannot do it, the task that needed it is blocked."""
    crew = await Crew.start(app)
    task = await crew.task()
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    asked = await crew.ok(
        "build-1", "agent.file_assist", what="two-factor code", task_id=task["id"],
        step="Sign in to the hosting account and read me the six-digit code.",
    )  # fmt: skip
    assert (asked["title"], asked["actions"]) == (
        "A step only you can do: two-factor code",
        ["done", "cannot"],
    )
    another = await crew.task(title="Write the about page")
    assert another["state"] == "ready"
    await decide(crew, asked["id"], "cannot", note="I do not have that account.")
    assert (await crew.show(task["id"]))["state"] == "blocked"
    assert (await crew.show(another["id"]))["state"] == "ready"


async def test_HUM_2_every_kind_that_waits_on_the_chairman_is_an_item(
    app: App, clock: FakeClock
) -> None:
    """HUM-1, HUM-2, GOV-3, 7.5: the budget checkpoint, a verdict the chairman holds and a
    reopen request are items like any other, decided with their typed actions. A verdict
    the chairman does not give in 72 hours passes to a reviewer seat. Stopping the
    project voids what is still open."""
    crew = await Crew.start(
        app, team=False,
        settings=SOLO | {"budget.tokens": 1_000_000, "authority.verdict": "chairman"},
    )  # fmt: skip
    task = await crew.ok("CEO", "agent.create_task", **TASK)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    await crew.ok("CEO", "agent.complete_task", task_id=task["id"], evidence="The page is up.")
    await later(crew, clock, minutes=1)
    verdict = next(item for item in await open_items(crew) if item["kind"] == "verdict")
    assert (verdict["kind"], verdict["default_outcome"]) == ("verdict", "to a reviewer")
    await later(crew, clock, hours=73)
    assert (await plan(crew))[crew.requirement]["state"] == "checking"
    ruled = await crew.call(
        "Reviewer", "agent.rule_requirement", requirement_id=crew.requirement, passed=True
    )
    assert ruled.status_code == 200, ruled.text
    assert (await plan(crew))[crew.requirement]["state"] == "met"

    await crew.finish_all()
    app.script("CEO/work", {"text": "Working.", "usage": {"input": 10_000, "output": 0}})
    await spend(app, crew.project, 895_000)
    await app.ok("chat.command", crew.owner, project_id=crew.project, text="/do Carry on.")
    await app.work()
    checkpoint = next(i for i in await open_items(crew) if i["kind"] == "budget checkpoint")
    assert checkpoint["actions"] == ["raise the budget", "land"]
    assert checkpoint["default_outcome"] == "land"
    small = await app.call(
        "items.decide", crew.owner, project_id=crew.project, item_id=checkpoint["id"],
        action="raise the budget", amount=500_000,
    )  # fmt: skip
    assert_refused(small, rule="GOV-3", code="not_a_raise")
    await decide(crew, checkpoint["id"], "raise the budget", amount=2_000_000)
    assert (await app.ok("budget.show", crew.owner, project_id=crew.project))["wall"] == 2_000_000

    await crew.ok("CEO", "agent.post_heads_up", text="I raised nothing; the chairman did.")
    await app.ok("projects.stop", crew.owner, project_id=crew.project)
    states = {item["kind"]: item["state"] for item in await open_items(crew, open_only=False)}
    assert states["heads-up"] == "void"
    assert states["budget checkpoint"] == "decided"


async def test_HUM_1_a_new_kind_is_only_a_registration(app: App) -> None:
    """HUM-1, IF-1.3: registering a kind is all it takes. With no other code, an item of
    it is listed for people and for agents, shown as a card line in the chat, counted on
    the desk, decided with its typed action, and its title comes from its typed fields."""
    crew = await Crew.start(app, team=False, settings=SOLO)
    items.register(
        items.Kind(
            name="sample: colour",
            filed_by="platform",
            actions=("choose", "skip"),
            default="skip",
            title=lambda fields: f"Choose a colour for page {fields['page']}",
        )
    )
    async with app.runtime.sessions() as session, session.begin():
        from crewmind.storage.models import Project

        project = await session.get(Project, crew.project)
        assert project is not None
        await items.file(
            session, app.runtime.services.settings, project, "sample: colour",
            filer=items.ITEMS_JOB, fields={"page": 3},
            recommendation="Pick the colour you like.", if_declined="It stays grey.",
            now=app.runtime.clock(),
        )  # fmt: skip
    (listed,) = await open_items(crew, kind="sample: colour")
    assert (listed["title"], listed["actions"]) == (
        "Choose a colour for page 3",
        ["choose", "skip"],
    )
    seen = (await crew.ok("CEO", "agent.items"))["items"]
    assert "sample: colour" in [item["kind"] for item in seen]
    desk = (await app.ok("desk.show", crew.owner))["waiting"]
    assert [entry["title"] for entry in desk] == ["Choose a colour for page 3"]
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    assert any("Choose a colour for page 3" in line["body"] for line in lines)
    decided = await decide(crew, listed["id"], "choose")
    assert (decided["state"], decided["outcome"]) == ("decided", "choose")
    assert (await app.ok("desk.show", crew.owner))["waiting"] == []


def test_INV_17_no_registered_kind_defaults_to_a_grant() -> None:
    """INV-17, HUM-3, P6: over every registered kind, the default outcome grants nothing,
    except delivery sign-off and a green status review, which only close the books. A
    tool permission never defaults to allow."""
    from crewmind.catalog import registry

    registry.load_domain_modules()
    positive_defaults = {
        kind.name
        for kind in items.kinds()
        if kind.default is not None and kind.default in kind.positive
    }
    assert positive_defaults == {"delivery sign-off", "status review"}
    assert items.kind_of("approval: tool permission").default == "deny"
    deadlines = {kind.name for kind in items.kinds() if kind.window is not None}
    assert {"proposed scope", "proposed commitment", "verdict", "reserve draw"} <= deadlines
