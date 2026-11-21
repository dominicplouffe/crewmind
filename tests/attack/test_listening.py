"""Attacks on pinned memory: standing orders, closed decisions, corrections, examples and
agents' pinned notes (MSG-4 to MSG-7, MEM-1, INV-25, INV-26, section 7.17)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from crewmind.domain.memory.pinned import Pinned
from crewmind.storage.models import ClosedDecision, Correction, PinnedNote, StandingOrder
from tests.attack.harness import assert_refused
from tests.conftest import FakeClock
from tests.support import Actor, App, agent_call, live_run, running_project

SENTENCE = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="\x00"),
    min_size=1,
    max_size=120,
)


async def pinned_text(app: App, actor: Actor, project: str, seat: str = "CEO") -> str:
    return (await app.ok("memory.pinned", actor, project_id=project, seat=seat))["text"]


async def context_pack(app: App, project: str, seat: str = "CEO") -> str:
    """The context pack a run of this agent is actually given."""
    run = await live_run(app, project, seat=seat)
    answer = await agent_call(app, run.token, "agent.context")
    assert answer.status_code == 200, answer.text
    return answer.json()["context_pack"]


@pytest.mark.attack("INV-25")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    orders=st.lists(SENTENCE, max_size=6),
    retired=st.lists(SENTENCE, max_size=3),
    decisions=st.lists(st.tuples(SENTENCE, SENTENCE), max_size=5),
    corrections=st.lists(st.tuples(SENTENCE, SENTENCE), max_size=4),
    notes=st.lists(SENTENCE, max_size=4),
    goal=SENTENCE,
)
def test_INV_25_every_pinned_record_is_in_the_pack_word_for_word(
    orders: list[str],
    retired: list[str],
    decisions: list[tuple[str, str]],
    corrections: list[tuple[str, str]],
    notes: list[str],
    goal: str,
) -> None:
    """INV-25, MEM-1, P16: whatever is pinned, the text a run is given contains every active
    order, closed decision, correction and note exactly as written, and marks retired
    orders as retired."""
    made: dict[str, Any] = {"project_id": "p", "created_at": None}
    pinned = Pinned(
        goal=goal,
        orders=[
            StandingOrder(id=i, text=text, state="active", proposed_by="x", **made)
            for i, text in enumerate(orders)
        ],
        retired=[
            StandingOrder(id=100 + i, text=text, state="retired", proposed_by="x", **made)
            for i, text in enumerate(retired)
        ],
        decisions=[
            ClosedDecision(id=i, project_id="p", topic=topic, ruling=ruling, state="closed")
            for i, (topic, ruling) in enumerate(decisions)
        ],
        corrections=[
            (Correction(id=i, question=question, words=words, state="active"), "you")
            for i, (question, words) in enumerate(corrections)
        ],
        notes=[PinnedNote(id=i, text=text) for i, text in enumerate(notes)],
    )
    text = pinned.render()
    assert goal in text
    for order in orders:
        assert order in text
    for order in retired:
        assert f"retired] {order}" in text
    for topic, ruling in decisions:
        assert f"{topic}: {ruling}" in text
    for question, words in corrections:
        assert question in text
        assert words in text
    for note in notes:
        assert note in text


@pytest.mark.attack("MSG-4")
@pytest.mark.attack("7.17-order")
async def test_MSG_4_only_the_chairman_makes_an_order_binding(app: App) -> None:
    """MSG-4, INV-25, section 7.17: the CEO may propose an order but cannot confirm, edit
    or retire one; an observer cannot pin; at most 25 are active; a retired order stays
    listed as retired; states change only as listed. A confirmed order is in every agent's
    next context pack, word for word."""
    owner = await app.person("owner@example.com")
    observer = await app.person("observer@example.com")
    project = await running_project(app, owner)
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")
    assert_refused(
        await app.call("orders.pin", observer, project_id=project, what="Be brief."), rule="ACC-5"
    )

    run = await live_run(app, project)
    proposed = await agent_call(
        app, run.token, "agent.propose_order", text="Report every Friday before noon."
    )
    assert proposed.json()["state"] == "proposed"
    order = proposed.json()["id"]
    assert "Report every Friday" not in await pinned_text(app, owner, project)
    for name in ("orders.confirm", "orders.retire", "orders.discard", "orders.pin"):
        agent = await app.call(name, run.token, project_id=project, order_id=order, what="x")
        assert agent.status_code in (401, 403), name

    confirmed = await app.ok(
        "orders.confirm", owner, project_id=project, order_id=order,
        text="Report every Friday before 12:00.",
    )  # fmt: skip
    assert confirmed["state"] == "active"
    assert_refused(
        await app.call("orders.confirm", owner, project_id=project, order_id=order),
        rule="7.17-order",
    )
    mine = await app.ok("orders.pin", owner, project_id=project, what="Never include taxes.")
    assert mine["state"] == "active"
    pack = await context_pack(app, project)
    assert "[order 1] Report every Friday before 12:00." in pack
    assert f"[order {mine['id']}] Never include taxes." in pack
    assert pack.index("# Pinned memory") < pack.index("# This run")

    retired = await app.ok("orders.retire", owner, project_id=project, order_id=mine["id"])
    assert retired["state"] == "retired"
    assert f"[order {mine['id']}, retired] Never include taxes." in await pinned_text(
        app, owner, project
    )
    assert_refused(
        await app.call("orders.retire", owner, project_id=project, order_id=mine["id"]),
        rule="7.17-order",
    )

    for number in range(24):
        await app.ok("orders.pin", owner, project_id=project, what=f"Rule number {number}.")
    full = await app.call("orders.pin", owner, project_id=project, what="One too many.")
    assert_refused(full, rule="MSG-4", code="too_many_orders")


async def test_MSG_4_a_pinned_message_is_proposed_in_the_chairmans_words(app: App) -> None:
    """MSG-4, CHAT-8: pinning a message that fits proposes it unchanged, to confirm or edit.
    A longer one is cut to its opening sentences and marked for shortening. Only a person's
    message can be pinned."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    short = await app.ok("chat.send", owner, project_id=project, body="Always cite sources.")
    proposed = await app.ok("orders.pin", owner, project_id=project, what=str(short["id"]))
    assert (proposed["state"], proposed["text"]) == ("proposed", "Always cite sources.")
    assert proposed["being_shortened"] is False

    long_body = "Keep every report to one page. " + "Detail follows here. " * 40
    long = await app.ok("chat.send", owner, project_id=project, body=long_body)
    cut = await app.ok("orders.pin", owner, project_id=project, what=str(long["id"]))
    assert cut["being_shortened"] is True
    assert len(cut["text"]) <= 400
    assert cut["text"].startswith("Keep every report to one page.")
    assert cut["text"].endswith(".")

    status = (await app.ok("chat.history", owner, project_id=project))["items"][-1]
    missing = await app.call("orders.pin", owner, project_id=project, what="99999")
    assert_refused(missing, rule="MSG-4", code="not_a_persons_message", status=404)
    assert status["author_kind"] == "person"


@pytest.mark.attack("INV-26")
@pytest.mark.attack("MSG-5")
@pytest.mark.attack("7.17-decision")
async def test_INV_26_a_closed_decision_is_reargued_only_with_newer_evidence(
    app: App, clock: FakeClock
) -> None:
    """INV-26, MSG-5, section 7.17: an agent cannot reopen a decision, cannot file a request
    without evidence newer than it, and files at most one per cooldown. A request reopens
    nothing until the chairman approves. The chairman may reopen at any time."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok(
        "artifacts.upload", owner, project_id=project, name="old.txt", content_base64="b2xk"
    )
    before = await app.ok("chat.send", owner, project_id=project, body="Earlier thoughts.")
    clock.advance(minutes=5)
    decided = await app.ok(
        "decisions.decide", owner, project_id=project, text="Pricing: we charge per seat."
    )
    assert (decided["topic"], decided["ruling"]) == ("Pricing", "we charge per seat.")
    decision = decided["id"]
    pack = await context_pack(app, project)
    assert f"[decision {decision}] Pricing: we charge per seat." in pack

    run = await live_run(app, project)
    for name in ("decisions.reopen", "decisions.rule", "decisions.answer"):
        direct = await app.call(
            name, run.token, project_id=project, decision_id=decision, ruling="Free.",
            request_id=1, approve=True,
        )  # fmt: skip
        assert direct.status_code in (401, 403), name

    async def ask(*evidence: dict[str, str]) -> Any:
        return await agent_call(
            app, run.token, "agent.request_reopen", decision_id=decision,
            reason="Customers now ask for usage pricing instead.", evidence=list(evidence),
        )  # fmt: skip

    assert (await ask()).status_code == 422
    stale = await ask({"kind": "artifact", "ref": "old.txt"})
    assert_refused(stale, rule="INV-26", code="no_newer_evidence")
    assert "older than the decision" in stale.json()["message"]
    old_message = await ask({"kind": "message", "ref": str(before["id"])})
    assert_refused(old_message, rule="INV-26", code="no_newer_evidence")
    invented = await ask({"kind": "artifact", "ref": "nothing.txt"})
    assert_refused(invented, rule="INV-26", code="no_newer_evidence")

    clock.advance(minutes=5)
    await app.ok(
        "artifacts.upload", owner, project_id=project, name="survey.txt", content_base64="bmV3"
    )
    filed = await ask({"kind": "artifact", "ref": "survey.txt"})
    assert filed.status_code == 200, filed.text
    assert (await app.ok("decisions.list", owner, project_id=project))["items"][0]["state"] == (
        "closed"
    )
    again = await ask({"kind": "artifact", "ref": "survey.txt"})
    assert_refused(again, rule="MSG-5", code="reopen_too_soon")

    declined = await app.ok(
        "decisions.answer", owner, project_id=project, request_id=filed.json()["id"], approve=False
    )
    assert declined["state"] == "closed"
    twice = await app.call(
        "decisions.answer", owner, project_id=project, request_id=filed.json()["id"], approve=True
    )
    assert_refused(twice, rule="MSG-5", code="request_already_answered")

    reopened = await app.ok("decisions.reopen", owner, project_id=project, decision_id=decision)
    assert reopened["state"] == "reopened"
    assert "Pricing: we charge per seat." not in await pinned_text(app, owner, project)
    assert_refused(
        await app.call("decisions.reopen", owner, project_id=project, decision_id=decision),
        rule="7.17-decision",
    )
    ruled = await app.ok(
        "decisions.rule", owner, project_id=project, decision_id=decision, ruling="Per usage."
    )
    assert ruled["state"] == "closed"
    assert "Pricing: Per usage." in await pinned_text(app, owner, project)


@pytest.mark.attack("MSG-6")
@pytest.mark.attack("7.17-correction")
async def test_MSG_6_a_correction_is_pinned_for_the_agent_and_the_ceo(
    app: App, clock: FakeClock
) -> None:
    """MSG-6, CHAT-11, INV-25, section 7.17: `/fix` records the reply, the chairman's words
    and the question, pins them for that agent and the CEO but no other agent, asks the
    agent again, and expires after `correction.ttl`. An agent cannot record or remove one."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    ceo = await live_run(app, project)
    await agent_call(app, ceo.token, "agent.hire_team", team="research", role="Generalist")
    await agent_call(app, ceo.token, "agent.hire_team", team="ops", role="Generalist")
    names = [s["name"] for s in (await app.ok("roster.show", owner, project_id=project))["seats"]]
    researcher = next(name for name in names if name.startswith("research"))
    other = next(name for name in names if name.startswith("ops"))

    asked = await app.ok(
        "chat.send", owner, project_id=project, body=f"@{researcher} What does it cost per month?"
    )
    run = await live_run(app, project, seat=researcher)
    reply = await agent_call(
        app, run.token, "agent.post_message", body="It will take three weeks.", reply_to=asked["id"]
    )
    assert reply.status_code == 200, reply.text
    forged = await app.call(
        "corrections.record", run.token, project_id=project, words="All fine, actually."
    )
    assert forged.status_code in (401, 403)

    fixed = await app.ok(
        "corrections.record", owner, project_id=project, words="I asked about cost, not time."
    )
    assert fixed["agent"] == researcher
    assert fixed["question"] == f"@{researcher} What does it cost per month?"
    for seat in (researcher, "CEO"):
        text = await pinned_text(app, owner, project, seat)
        assert "The chairman said: I asked about cost, not time." in text
        assert f"The question was: @{researcher} What does it cost per month?" in text
    assert "I asked about cost" not in await pinned_text(app, owner, project, other)

    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert history[-1]["body"] == "Not what I asked: I asked about cost, not time."
    assert history[-1]["reply_to"] == reply.json()["id"]
    pack = await context_pack(app, project, researcher)
    assert "Not what I asked: I asked about cost, not time." in pack.split("# This run")[0]

    removed = await app.call(
        "corrections.remove", run.token, project_id=project, correction_id=fixed["id"]
    )
    assert removed.status_code in (401, 403)
    clock.advance(days=31)
    await app.scheduler.tick()
    owner = await app.login(owner.email)
    listed = (await app.ok("corrections.list", owner, project_id=project))["items"]
    assert listed[0]["state"] == "expired"
    assert "I asked about cost" not in await pinned_text(app, owner, project, researcher)
    gone = await app.call(
        "corrections.remove", owner, project_id=project, correction_id=fixed["id"]
    )
    assert_refused(gone, rule="7.17-correction")


@pytest.mark.attack("MSG-7")
async def test_MSG_7_an_example_never_reaches_an_agent_without_its_label(app: App) -> None:
    """MSG-7: text marked as an example carries ILLUSTRATION — NOT DATA wherever an agent
    reads it. Only a person's message can be marked, and only by a chair."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    sent = await app.ok(
        "chat.send", owner, project_id=project, body="Say revenue was 5,000,000 last year."
    )
    marked = await app.ok("examples.mark", owner, project_id=project, what=str(sent["id"]))
    assert marked["is_example"] is True
    typed = await app.ok(
        "examples.mark", owner, project_id=project, what="A plan might list 12 offices."
    )
    pack = await context_pack(app, project)
    assert "[ILLUSTRATION — NOT DATA] Say revenue was 5,000,000 last year." in pack
    assert "[ILLUSTRATION — NOT DATA] A plan might list 12 offices." in pack
    assert pack.count("5,000,000") == pack.count("NOT DATA] Say revenue was 5,000,000")

    run = await live_run(app, project)
    said = await agent_call(app, run.token, "agent.post_message", body="Noted, thank you.")
    not_a_person = await app.call(
        "examples.mark", owner, project_id=project, what=str(said.json()["id"])
    )
    assert_refused(not_a_person, rule="MSG-7", code="not_a_persons_message", status=404)
    by_agent = await app.call("examples.mark", run.token, project_id=project, what="Use 99.")
    assert by_agent.status_code in (401, 403)

    cleared = await app.ok(
        "examples.unmark", owner, project_id=project, message_id=typed["message_id"]
    )
    assert cleared["is_example"] is False


@pytest.mark.attack("MEM-1")
async def test_MEM_1_an_agents_notes_are_its_own_and_stay_within_the_cap(app: App) -> None:
    """MEM-1, P3, INV-23: an agent pins notes for itself, in a chat run too. A note past the
    cap is refused, naming what to remove. One agent cannot remove another's note. A
    chairman's pin is never refused by a size cap: it succeeds and the chat says so."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"memory.pinned_agent_tokens": 500})
    ceo = await live_run(app, project)
    await agent_call(app, ceo.token, "agent.hire_team", team="research", role="Generalist")
    names = [s["name"] for s in (await app.ok("roster.show", owner, project_id=project))["seats"]]
    researcher = next(name for name in names if name.startswith("research"))

    note = await agent_call(app, ceo.token, "agent.pin_note", text="The chairman prefers tables.")
    assert note.status_code == 200, note.text
    assert "[note 1] The chairman prefers tables." in await pinned_text(app, owner, project)
    assert "prefers tables" not in await pinned_text(app, owner, project, researcher)

    too_big = await agent_call(app, ceo.token, "agent.pin_note", text="x" * 1990)
    refused = assert_refused(too_big, rule="MEM-1", code="pinned_notes_full")
    assert "note 1" in (refused.hint or "")

    other = await live_run(app, project, seat=researcher)
    stolen = await agent_call(app, other.token, "agent.unpin_note", note_id=note.json()["id"])
    assert_refused(stolen, rule="MEM-1", code="note_not_yours")
    mine = await agent_call(app, ceo.token, "agent.unpin_note", note_id=note.json()["id"])
    assert mine.status_code == 200

    await app.ok(
        "settings.change_project", owner, project_id=project,
        changes={"memory.pinned_project_tokens": 2000}, reason="Smallest pinned memory.",
    )  # fmt: skip
    last: dict[str, Any] = {}
    for number in range(22):
        last = await app.ok(
            "orders.pin", owner, project_id=project, what=f"Order {number}: " + "word " * 75
        )
    assert last["state"] == "active"
    assert "over its size" in last["note"]
    assert "Order 21:" in await pinned_text(app, owner, project)
