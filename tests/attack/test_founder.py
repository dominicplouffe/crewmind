"""Attacks on the Founder: a scripted model tries to break each drafting rule through its
tools, the only way it can act (FND-2 to FND-11, FND-14, section 7.19)."""

from __future__ import annotations

from typing import Any

import pytest

from crewmind.catalog.refusal import Refusal
from tests.attack.harness import assert_refused
from tests.founder_support import (
    BRIEF,
    DECISIONS,
    GOAL,
    ROLE_WORDS,
    SPEC,
    credential,
    propose,
    question,
    script,
    tool,
)
from tests.support import App

pytestmark = pytest.mark.usefixtures("quick_rehearsal")


def codes(view: dict[str, Any]) -> list[str]:
    return [hit["code"] for hit in view["rules_hit"]]


@pytest.mark.attack("FND-3")
@pytest.mark.attack("FND-4")
@pytest.mark.attack("FND-8")
@pytest.mark.attack("FND-9")
@pytest.mark.attack("FND-10")
@pytest.mark.attack("7.19")
async def test_FND_3_the_founder_cannot_talk_its_way_past_a_drafting_rule(app: App) -> None:
    """FND-2, FND-3, FND-4, FND-8, FND-9, FND-10, 7.19: a Founder that asks two things at
    once, asks out of order, offers five options, gives no recommendation, picks who pays
    for a chairman with two credentials, writes a date into the goal, sets a setting with
    no reason, leaves out the plan adversary, puts words in the chairman's mouth, or calls
    a tool it does not have, is refused each time and reaches no draft. Its tools are
    exactly eight."""
    from crewmind.domain.founder.tools import TOOLS

    assert sorted(TOOLS) == sorted(
        ["search_library", "list_credentials", "fetch_url", "read_upload", "grade_goal",
         "rehearse_spec", "ask", "propose_spec"]
    )  # fmt: skip
    owner = await app.person("owner@example.com")
    await credential(app, owner, "main")
    await credential(app, owner, "spare")
    dated = GOAL + " Finish by 31 December 2027."
    script(
        app,
        tool("ask", questions=[question("finish_line"), question("beneficiary_standard")]),
        tool("ask", questions=[question("budget")]),
        tool("ask", questions=[question("finish_line", options=["a", "b", "c", "d", "e"])]),
        tool("ask", questions=[question("finish_line", recommended=None)]),
        propose(spec={"paying_credential": "main"}),
        propose(spec={"goal": dated}),
        propose(spec={"settings": {"run.concurrency": 6}}),
        propose(spec={"teams": SPEC["teams"][:1]}),
        propose(decisions={"chairman_role": {"value": "Hands off.", "quote": "Do as you like."}}),
        tool("create_project", name="Mine"),
        tool("ask", questions=[question("finish_line")]),
        {"text": "What record shows the guide is finished?"},
    )
    started = await app.ok("founder.start", owner, brief=BRIEF)
    assert (started["state"], started["waiting_for"]) == ("drafting", "the Founder")
    assert await app.founder.tick() == 1
    shown = await app.ok("founder.show", owner, drafting_id=started["drafting_id"])
    assert codes(shown) == [
        "one_at_a_time",
        "not_the_next_decision",
        "options",
        "no_recommendation",
        "who_pays_is_not_preselected",
        "date_in_goal",
        "setting_without_reason",
        "no_plan_adversary",
        "not_the_chairmans_words",
        "unknown_tool",
    ]
    assert shown["draft"] is None
    assert [q["settles"] for q in shown["questions"]] == ["finish_line"]
    assert shown["waiting_for"] == "you"
    assert shown["lines"][-1]["body"] == "What record shows the guide is finished?"

    ref = {"drafting_id": started["drafting_id"]}
    not_ready = await app.call("founder.create", owner, **ref)
    assert_refused(not_ready, rule="FND-5", code="draft_not_ready")
    stranger = await app.person("stranger@example.com")
    assert (await app.call("founder.show", stranger, **ref)).status_code == 404
    taken = await app.call(
        "founder.answer", stranger, **ref, question_id=shown["questions"][0]["id"]
    )
    assert taken.status_code == 404


@pytest.mark.attack("FND-5")
@pytest.mark.attack("FND-11")
async def test_FND_5_a_project_comes_only_from_a_confirmed_ledger(app: App) -> None:
    """FND-1, FND-3, FND-5, FND-6, FND-11, FND-13, FND-14, FND-10, SPD-4: the draft comes
    first and is graded; each question has a recommendation that Enter accepts; an answer,
    the chairman's own words, and an accepted recommendation are told apart in the ledger;
    the draft is not ready until every decision is settled and it has been rehearsed; then
    the chairman creates the project, which gets the conversation as its chat, the first
    requirement, the doctrine's fingerprint, and the ledger in the CEO's first pack."""
    owner = await app.person("owner@example.com")
    await credential(app, owner, "main")
    decided = {**DECISIONS, "chairman_role": {"value": "Answers questions.", "quote": ROLE_WORDS}}
    script(
        app,
        propose(decisions=decided),
        tool("ask", questions=[question("finish_line")]),
        {"text": "Here is a first draft. What record shows the guide is finished?"},
        tool("ask", questions=[question("beneficiary_standard")]),
        {"text": "Who is it for?"},
        tool("rehearse_spec"),
        {"text": "The draft is rehearsed and ready for you to confirm."},
    )
    started = await app.ok("founder.start", owner, brief=BRIEF)
    ref = {"drafting_id": started["drafting_id"]}
    await app.founder.tick()
    shown = await app.ok("founder.show", owner, **ref)
    assert shown["grade"]["ready"] is True
    assert shown["draft"]["name"] == SPEC["name"]
    sources = {entry["settles"]: entry["source"] for entry in shown["ledger"]}
    assert sources == {"who_pays": "assumption", "chairman_role": "words"}
    assert (shown["ready"], shown["rehearsal"]) == (False, None)
    assert any("has not been rehearsed" in line for line in shown["not_ready_because"])
    assert any("Not yet decided" in line for line in shown["not_ready_because"])

    first = shown["questions"][0]
    assert first["recommended"] == 0
    await app.ok("founder.answer", owner, **ref, question_id=first["id"], answer="")
    await app.founder.tick()
    second = (await app.ok("founder.show", owner, **ref))["questions"][0]
    assert second["settles"] == "beneficiary_standard"
    own = "The walker, judged against a published regional guide."
    await app.ok("founder.answer", owner, **ref, question_id=second["id"], answer=own)
    assert_refused(await app.call("founder.create", owner, **ref), rule="FND-5")
    await app.ok("founder.accept_rest", owner, **ref)
    await app.founder.tick()

    ready = await app.ok("founder.show", owner, **ref)
    assert (ready["ready"], ready["not_ready_because"]) == (True, [])
    ledger = {entry["settles"]: entry for entry in ready["ledger"]}
    assert ledger["finish_line"]["value"] == "Yes, as recommended"
    assert (ledger["beneficiary_standard"]["value"], ledger["beneficiary_standard"]["source"]) == (
        own,
        "answer",
    )
    assert ledger["budget"]["source"] == "assumption"
    assert len(ledger) == 13
    assert ready["rehearsal"].startswith("Runs to its first verified close")

    created = await app.ok("founder.create", owner, **ref)
    assert (created["state"], created["can_start"]) == ("draft", True)
    project = created["project_id"]
    done = await app.ok("founder.show", owner, **ref)
    assert (done["state"], done["project_id"]) == ("created", project)
    assert_refused(await app.call("founder.say", owner, **ref, body="One more thing."), rule="7.19")
    history = (await app.ok("chat.history", owner, project_id=project, limit=200))["items"]
    said = [line["body"] for line in history]
    assert any(body.startswith("You: I want a field guide") for body in said)
    assert any("The Founder: Here is a first draft" in body for body in said)
    exported = await app.ok("projects.export", owner, project_id=project)
    assert (exported["goal"], exported["paying_credential"]) == (GOAL, "main")
    plan = await app.ok("plan.show", owner, project_id=project)
    assert [r["text"] for r in plan["requirements"]] == [
        "A first usable guide to five birds exists."
    ]

    record = (await app.ok("record.list_install", await app.admin(), limit=200))["items"]
    drafted = [event for event in record if event["type"].startswith("drafting.")]
    assert [event["after"].get("state") for event in drafted if "state" in event["after"]] == [
        "drafting",
        "created",
    ]
    assert [e["after"]["what"] for e in drafted if e["type"] == "drafting.edited"] == [
        "answered",
        "answered",
        "accepted the rest",
    ]

    await app.ok("projects.start", owner, project_id=project)
    app.script("CEO/work", {"text": "Read."})
    await app.work()
    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    trace = await app.ok("runs.trace", owner, project_id=project, run_id=runs[0]["run_id"])
    assert "# From the Founder" in trace["context_pack"]
    assert f"- beneficiary_standard: {own} (answer)" in trace["context_pack"]


@pytest.mark.attack("FND-15")
async def test_FND_15_a_document_is_grilled_one_question_at_a_time_before_any_draft(
    app: App,
) -> None:
    """FND-15, FND-3, FND-5, MSG-7: a pasted document is listed and grilled before anything
    is drafted. The Founder cannot draft first, ask before listing, or quote what the
    document does not say. Each planted problem (two contradictions, an illustrative
    number, a requirement nobody can verify) gets its own question, one at a time, and no
    draft exists until the last is resolved. Each answer is in the ledger with its
    passage, and a passage the chairman calls an example reaches the CEO labelled as one."""
    import json

    from tests.founder_support import ACCEPTANCE, DOCUMENT

    expected = json.loads((ACCEPTANCE / "grill-document.expected.json").read_text())
    planted = [
        {"kind": "number", "passage": entry["passages"][0], "problem": entry["problem"]}
        for entry in expected["planted"]
    ]
    listed = [
        {"kind": "goal", "passage": "We want a printed field guide to the birds"},
        *planted,
    ]
    example = ["It is an example", "It is a hard limit"]
    owner = await app.person("owner@example.com")
    await credential(app, owner, "main")
    script(
        app,
        propose(),
        tool("ask", questions=[question("finish_line")]),
        tool("ask", extracted=[{"kind": "number", "passage": "The guide covers ninety birds."}]),
        tool("ask", extracted=listed),
        tool("ask", questions=[question("item:2"), question("item:3")]),
        tool("ask", questions=[question("finish_line")]),
        tool("ask", questions=[question("item:2")]),
        {"text": "Forty birds or sixty?"},
        propose(),
        tool("ask", questions=[question("item:3")]),
        {"text": "Photographs or not?"},
        tool("ask", questions=[question("item:4", options=example)]),
        {"text": "Is 250 words an example or a limit?"},
        tool("ask", questions=[question("item:5")]),
        {"text": "How would anyone check that?"},
        propose(),
        {"text": "Here is the draft."},
    )
    started = await app.ok("founder.start", owner, brief="Please read this.", document=DOCUMENT)
    ref = {"drafting_id": started["drafting_id"]}
    asked: list[str] = []
    for answer in ("", "", "a", ""):
        await app.founder.tick()
        shown = await app.ok("founder.show", owner, **ref)
        assert shown["draft"] is None
        assert len(shown["questions"]) == 1
        asked.append(shown["questions"][0]["settles"])
        await app.ok(
            "founder.answer", owner, **ref, question_id=shown["questions"][0]["id"], answer=answer
        )
    assert asked == ["item:2", "item:3", "item:4", "item:5"]
    await app.founder.tick()
    done = await app.ok("founder.show", owner, **ref)
    assert codes(done) == [
        "grill_first",
        "extract_first",
        "passage_not_in_document",
        "one_at_a_time",
        "not_the_next_decision",
        "passages_unresolved",
    ]
    assert done["draft"] is not None
    ledger = {entry["settles"]: entry for entry in done["ledger"]}
    for index, entry in enumerate(expected["planted"], start=2):
        assert ledger[f"item:{index}"]["passage"] == entry["passages"][0]
        assert ledger[f"item:{index}"]["source"] == "answer"
    assert ledger["item:4"]["value"] == "It is an example"

    await app.ok("founder.accept_rest", owner, **ref)
    script(app, tool("rehearse_spec"), {"text": "Ready."})
    async with app.runtime.sessions() as session, session.begin():
        from crewmind.storage.models import Drafting

        row = await session.get(Drafting, started["drafting_id"])
        assert row is not None
        row.model_calls = 0
    await app.founder.tick()
    created = await app.ok("founder.create", owner, **ref, start=True)
    app.script("CEO/work", {"text": "Read."})
    await app.work()
    runs = (await app.ok("runs.list", owner, project_id=created["project_id"]))["items"]
    trace = await app.ok(
        "runs.trace", owner, project_id=created["project_id"], run_id=runs[0]["run_id"]
    )
    assert "ILLUSTRATION" in trace["context_pack"]
    assert "a typical entry might run to about 250 words" in trace["context_pack"]


@pytest.mark.attack("FND-7")
async def test_FND_7_a_grade_stands_only_on_lines_the_goal_holds(app: App) -> None:
    """FND-6, FND-7, section 13: the reference goal grades ready. The raw brief does not,
    and is missing exactly the elements its hand grade names. A grade that quotes a line
    the goal does not hold, skips an element, or calls one weak with no evidence is
    refused; and a goal missing a load-bearing element is not ready whatever else is
    said. The grade here is a scripted model's: it proves the rules, not a model's eye."""
    import json

    from crewmind.domain.founder import grammar
    from tests.founder_support import ACCEPTANCE, grades

    owner = await app.person("owner@example.com")
    script(app)
    ready = await app.ok("goals.grade", owner, goal=GOAL)
    assert (ready["ready"], ready["missing"], ready["weak"]) == (True, [], [])
    script(app, graded="raw-brief")
    hand = json.loads((ACCEPTANCE / "raw-brief.grades.json").read_text())
    brief = await app.ok("goals.grade", owner, goal=BRIEF)
    assert (brief["ready"], brief["missing"], brief["weak"]) == (
        False,
        hand["missing"],
        hand["weak"],
    )
    assert brief["summary"] == (
        "Not ready: finish_line, standard, anti_metrics, failure_deliverable missing."
    )

    refused = await app.call("goals.grade", owner, goal="Make the valley better.")
    assert_refused(refused, rule="FND-7", code="quote_not_in_goal")
    rows = grades("reference-goal")
    weak = {**rows[0], "grade": "weak", "quote": "", "fix": "Name it."}
    silent = {**rows[0], "quote": "", "reason": ""}
    unfixed = {**rows[0], "grade": "missing", "quote": "", "fix": ""}
    for broken, code in (
        (rows[:9], "grade_incomplete"),
        ([weak, *rows[1:]], "grade_without_evidence"),
        ([silent, *rows[1:]], "grade_without_evidence"),
        ([unfixed, *rows[1:]], "grade_without_fix"),
    ):
        with pytest.raises(Refusal) as caught:
            grammar.check(GOAL, broken)
        assert caught.value.envelope.code == code
    one_missing = [{**rows[9], "grade": "missing", "quote": "", "fix": "Say what is owed."}]
    assert grammar.check(GOAL, [*rows[:9], *one_missing]).ready is False
    not_load_bearing = [{**rows[1], "grade": "missing", "quote": "", "fix": "Name the reader."}]
    assert grammar.check(GOAL, [rows[0], *not_load_bearing, *rows[2:]]).ready is True


@pytest.mark.attack("FND-3")
async def test_FND_12_quick_mode_creates_and_starts_or_leaves_nothing(app: App) -> None:
    """FND-12, FND-3, 7.19, INV-8: quick mode accepts the Founder's own recommendations,
    asks nothing, and creates and starts the project, moving drafting to started. With
    two credentials it does not begin until told who pays. A quick draft that cannot be
    created ends failed with no project. Founder calls are metered to no project."""
    from sqlalchemy import select

    from crewmind.storage.models import LedgerLine

    owner = await app.person("owner@example.com")
    await credential(app, owner, "main")
    script(
        app,
        tool("ask", questions=[question("finish_line")]),
        propose(spec={"integrations": ["email"]}),
        {"text": "Drafted."},
    )
    quick = await app.ok("founder.quick", owner, brief=BRIEF)
    await app.founder.tick()
    shown = await app.ok("founder.show", owner, drafting_id=quick["drafting_id"])
    assert codes(shown) == ["quick_mode_asks_nothing"]
    assert (shown["state"], shown["questions"]) == ("started", [])
    assert {entry["source"] for entry in shown["ledger"]} == {"assumption"}
    project = shown["project_id"]
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "running"
    exported = await app.ok("projects.export", owner, project_id=project)
    assert (exported["paying_credential"], exported["integrations"]) == ("main", [])
    async with app.runtime.sessions() as session:
        lines = list(await session.scalars(select(LedgerLine).where(LedgerLine.kind == "founder")))
    assert lines
    assert all(line.project_id is None for line in lines)

    await credential(app, owner, "spare")
    unsaid = await app.call("founder.quick", owner, brief=BRIEF)
    assert_refused(unsaid, rule="FND-3", code="say_who_pays")
    before = len((await app.ok("projects.list", owner))["items"])
    script(app, propose(spec={"teams": SPEC["teams"][:1]}), {"text": "Drafted."})
    failing = await app.ok("founder.quick", owner, brief=BRIEF, credential="spare")
    await app.founder.tick()
    failed = await app.ok("founder.show", owner, drafting_id=failing["drafting_id"])
    assert (failed["state"], failed["project_id"]) == ("failed", None)
    assert "nothing was created" in failed["lines"][-1]["body"]
    assert len((await app.ok("projects.list", owner))["items"]) == before


@pytest.mark.attack("FND-16")
async def test_FND_16_a_grilled_document_becomes_no_work_until_the_ledger_is_confirmed(
    app: App,
) -> None:
    """FND-16, FND-3, section 13: `/grill` in a running project makes the CEO interview
    the chairman about a document. While it is open the CEO can propose no requirement;
    work already under way goes on. The CEO cannot quote what the document does not say
    or invent what a passage conflicts with; the planted conflict with a standing order
    is surfaced as a question in the chat, with no deadline. Nothing is confirmed while a
    question is open; after the chairman confirms, the CEO may propose scope again."""
    from tests.attack.work_support import Crew
    from tests.founder_support import DOCUMENT

    crew = await Crew.start(app)
    owner, project = crew.owner, crew.project
    order = await app.ok(
        "orders.pin", owner, project_id=project, what="Every plate is a photograph."
    )
    requirement = {
        "text": "The guide has a page for the wren.",
        "test_kind": "observable",
        "success_test": "A reader finds the wren's page in the guide.",
        "estimate_runs": 1,
    }
    await crew.ok("CEO", "agent.propose_requirement", **requirement)

    stranger = await app.person("stranger@example.com")
    assert (await app.call("grill.start", stranger, project_id=project)).status_code in (403, 404)
    grilling = await app.ok("grill.start", owner, project_id=project, document=DOCUMENT)
    assert (grilling["grilling"], grilling["can_confirm"]) == (True, False)
    assert_refused(
        await app.call("grill.start", owner, project_id=project, document=DOCUMENT),
        rule="FND-16",
        code="already_grilling",
    )
    blocked = await crew.call(
        "CEO", "agent.propose_requirement", **{**requirement, "text": "The guide has a robin page."}
    )
    assert_refused(blocked, rule="FND-16", code="grilling_in_progress")
    assert_refused(await app.call("grill.confirm", owner, project_id=project), rule="FND-16")

    seen = await crew.ok("CEO", "agent.grill")
    assert seen["document"].startswith("Hollin Valley bird guide")
    drawing = {"kind": "constraint", "passage": "Every plate is a drawing.", "problem": "conflict"}
    invented = await crew.call(
        "CEO", "agent.grill_extract", items=[{**drawing, "conflicts_with": "order:999"}]
    )
    assert_refused(invented, rule="FND-16", code="conflict_with_nothing")
    misquoted = await crew.call(
        "CEO", "agent.grill_extract", items=[{"kind": "number", "passage": "Ninety birds."}]
    )
    assert_refused(misquoted, rule="FND-15", code="passage_not_in_document")
    listed = await crew.ok(
        "CEO",
        "agent.grill_extract",
        items=[
            {"kind": "goal", "passage": "We want a printed field guide to the birds"},
            {**drawing, "conflicts_with": f"order:{order['id']}"},
        ],
    )
    conflict = next(item for item in listed["items"] if item["problem"] == "conflict")
    assert (conflict["state"], conflict["note"]) == ("open", f"Conflicts with order:{order['id']}.")

    card = {
        "text": "The document says drawings; your standing order says photographs. Which wins?",
        "options": ["The standing order: photographs", "The document: drawings"],
        "recommended": 0,
        "changes": "Whether the plates are drawn or photographed.",
    }
    clear = next(item for item in listed["items"] if item["problem"] is None)
    wrong = await crew.call("CEO", "agent.grill_ask", item_id=clear["id"], **card)
    assert_refused(wrong, rule="FND-15", code="not_the_next_decision")
    asked = await crew.ok("CEO", "agent.grill_ask", item_id=conflict["id"], **card)
    question = asked["questions"][0]
    history = (await app.ok("chat.history", owner, project_id=project, limit=200))["items"]
    shown = next(line for line in history if "grill question" in str(line["detail"]))
    assert "Which wins?" in shown["body"]
    assert "(recommended)" in shown["body"]
    items = (await app.ok("items.list", owner, project_id=project))["items"]
    assert not [item for item in items if "grill" in item["kind"]]
    assert_refused(await app.call("grill.confirm", owner, project_id=project), rule="FND-16")

    answered = await app.ok(
        "grill.answer", owner, project_id=project, question_id=question["id"], answer="b"
    )
    assert answered["can_confirm"] is True
    assert answered["ledger"][0]["value"] == "The document: drawings"
    assert answered["ledger"][0]["passage"] == "Every plate is a drawing."
    history = (await app.ok("chat.history", owner, project_id=project, limit=200))["items"]
    assert any("change that too" in line["body"] for line in history)
    confirmed = await app.ok("grill.confirm", owner, project_id=project)
    assert (confirmed["grilling"], confirmed["state"]) == (False, "created")
    crew.owner = owner
    await crew.ok(
        "CEO", "agent.propose_requirement", **{**requirement, "text": "Every plate is a drawing."}
    )
    events = [e for e in await app.events(owner, project) if e["type"].startswith("drafting.")]
    seen_events = [
        (str(e["type"]), str(dict(e["after"]).get("state") or dict(e["after"]).get("what")))
        for e in events
    ]
    assert seen_events == [
        ("drafting.state_changed", "drafting"),
        ("drafting.edited", "answered"),
        ("drafting.state_changed", "created"),
    ]
