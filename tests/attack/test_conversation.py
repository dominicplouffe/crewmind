"""Attacks on directives, action cards, slash commands and the pair breaker
(MSG-3, MSG-9, CHAT-5, CHAT-6, CHAT-7, P15, INV-20, section 7.17)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.attack.harness import assert_refused
from tests.conftest import FakeClock
from tests.support import Actor, App, agent_call, live_run, running_project


async def slash(app: App, actor: Actor, project: str, text: str) -> dict[str, Any]:
    return await app.ok("chat.command", actor, project_id=project, text=text)


@pytest.mark.attack("MSG-3")
@pytest.mark.attack("7.17-directive")
async def test_MSG_3_chat_words_change_state_only_through_a_directive(app: App) -> None:
    """MSG-3, P15, CHAT-6, section 7.17: a plain message wakes only a chat run, which can
    change nothing. `/do` creates a directive, echoes it, and wakes a work run that carries
    it out. Only its addressee can report it done, once."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("roster.hire_team", owner, project_id=project, team="research", role="Generalist")
    app.script("CEO/chat", {"text": "Shall I hire an ops team? Say /do."})
    await app.ok("chat.send", owner, project_id=project, body="We need an ops team.")
    await app.work()
    assert (await app.ok("roster.show", owner, project_id=project))["teams"] == ["research"]
    assert [r["kind"] for r in (await app.ok("runs.list", owner, project_id=project))["items"]] == [
        "chat"
    ]

    issued = await slash(app, owner, project, "/do Hire an ops team of two generalists")
    assert issued["operation"] == "directives.issue"
    directive = issued["result"]
    assert (directive["to"], directive["state"]) == ("CEO", "issued")
    app.script(
        "CEO/work",
        {
            "tools": [
                {
                    "name": "agent_hire_team",
                    "arguments": {"team": "ops", "role": "Generalist", "members": 2},
                }
            ]
        },
        {
            "tools": [
                {
                    "name": "agent_complete_directive",
                    "arguments": {"directive_id": 1, "outcome": "Hired the ops team of two."},
                }
            ]
        },
        {"text": "done"},
    )
    await app.work()
    assert (await app.ok("roster.show", owner, project_id=project))["teams"] == ["ops", "research"]
    listed = (await app.ok("directives.list", owner, project_id=project))["items"]
    assert (listed[0]["state"], listed[0]["outcome"]) == ("done", "Hired the ops team of two.")
    history = [
        m["body"] for m in (await app.ok("chat.history", owner, project_id=project))["items"]
    ]
    assert "Directive 1 to CEO: Hire an ops team of two generalists" in history
    assert "CEO carried out directive 1: Hired the ops team of two." in history

    to_worker = await slash(app, owner, project, "/do @research summarise the brief")
    assert to_worker["result"]["to"] == "research"
    ceo = await live_run(app, project)
    worker = await live_run(app, project, seat="research")
    stolen = await agent_call(
        app, ceo.token, "agent.complete_directive", directive_id=2, outcome="I did it instead."
    )
    assert_refused(stolen, rule="MSG-3", code="not_your_directive")
    assert (
        await agent_call(
            app,
            worker.token,
            "agent.complete_directive",
            directive_id=2,
            outcome="Summary written.",
        )
    ).status_code == 200
    again = await agent_call(
        app, worker.token, "agent.complete_directive", directive_id=2, outcome="Done again, twice."
    )
    assert_refused(again, rule="7.17-directive", code="transition_refused")
    pack = (await agent_call(app, ceo.token, "agent.context")).json()["context_pack"]
    assert "The chairman directed research: @research summarise the brief" in pack


@pytest.mark.attack("MSG-3")
async def test_INV_20_a_directive_on_a_held_project_waits_until_it_resumes(
    app: App, clock: FakeClock
) -> None:
    """MSG-3, INV-20, section 7.17: on a held project a directive waits and no work run
    starts; it is issued again on resume. Stopping the project voids it. A draft project
    takes none."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("projects.hold", owner, project_id=project)
    waiting = await slash(app, owner, project, "/do Draft the launch plan")
    assert waiting["result"]["state"] == "waiting"
    assert await app.work() == 0
    history = [
        m["body"] for m in (await app.ok("chat.history", owner, project_id=project))["items"]
    ]
    assert "It waits until the project runs again (it is held)." in history[-1]

    await slash(app, owner, project, "/resume")
    app.script("CEO/work", {"text": "on it"})
    assert await app.work() == 1
    run = (await app.ok("runs.list", owner, project_id=project))["items"][0]
    assert run["reasons"] == ["notice: directive issued"]
    assert (await app.ok("directives.list", owner, project_id=project))["items"][0][
        "state"
    ] == "issued"

    await slash(app, owner, project, "/stop")
    assert (await app.ok("directives.list", owner, project_id=project))["items"][0][
        "state"
    ] == "void"
    draft = await app.project(owner)
    refused = await app.call("directives.issue", owner, project_id=draft, instruction="Start now")
    assert_refused(refused, rule="MSG-3", code="project_not_started")


@pytest.mark.attack("7.17-card")
async def test_CHAT_7_an_action_card_does_nothing_until_the_chairman_accepts_it(app: App) -> None:
    """CHAT-7, INV-23, section 7.17: a chat run may propose with a card. Nothing happens
    until "Do it", which creates a directive, with the edit if one was made. A card is
    decided once; an observer cannot decide it."""
    owner = await app.person("owner@example.com")
    observer = await app.person("observer@example.com")
    project = await running_project(app, owner)
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")
    app.script(
        "CEO/chat",
        {
            "tools": [
                {
                    "name": "agent_propose_action",
                    "arguments": {
                        "what": "Hire a two-person research team.",
                        "estimated_tokens": 400000,
                        "reversible": True,
                    },
                }
            ]
        },
        {"text": ""},
    )
    asked = await app.ok("chat.send", owner, project_id=project, body="Can we look into pricing?")
    await app.work()
    cards = (await app.ok("cards.list", owner, project_id=project))["items"]
    assert (cards[0]["state"], cards[0]["estimated_tokens"], cards[0]["reversible"]) == (
        "open",
        400000,
        True,
    )
    card = (await app.ok("chat.history", owner, project_id=project))["items"][-1]
    assert card["detail"] == {"kind": "action card", "card": 1}
    assert card["reply_to"] == asked["id"]
    assert "Estimated 400,000 tokens. It can be undone." in card["body"]
    assert (await app.ok("chat.header", owner, project_id=project))["waiting_on_you"] == 1
    assert (await app.ok("directives.list", owner, project_id=project))["items"] == []
    assert (await app.ok("roster.show", owner, project_id=project))["teams"] == []

    assert_refused(
        await app.call("cards.accept", observer, project_id=project, card_id=1), rule="ACC-5"
    )
    await app.ok(
        "cards.accept", owner, project_id=project, card_id=1, edited="Hire one researcher only."
    )
    directive = (await app.ok("directives.list", owner, project_id=project))["items"][0]
    assert (directive["text"], directive["to"]) == ("Hire one researcher only.", "CEO")
    for name in ("cards.accept", "cards.dismiss"):
        assert_refused(await app.call(name, owner, project_id=project, card_id=1), rule="7.17-card")
    assert (await app.ok("chat.header", owner, project_id=project))["waiting_on_you"] == 0


async def test_CHAT_5_a_slash_command_is_the_operation_it_names(app: App) -> None:
    """CHAT-5, IF-1.2, IF-1.4, GOV-1: a slash command runs the catalog operation with that
    operation's own authority and refusals. An observer's `/hold` is refused exactly as the
    operation refuses it."""
    owner = await app.person("owner@example.com")
    observer = await app.person("observer@example.com")
    project = await running_project(app, owner)
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")

    helped = await slash(app, owner, project, "/help")
    assert set(helped["result"]["commands"]) >= {
        "/do",
        "/hold",
        "/resume",
        "/stop",
        "/status",
        "/budget",
        "/quality",
        "/brevity",
        "/lock",
        "/deliverables",
        "/help",
    }
    assert "/pin" in helped["result"]["later"]

    held = await slash(app, owner, project, "/hold until 2026-11-23T09:00:00Z note=Weekend")
    assert held["operation"] == "projects.hold"
    assert held["result"]["state"] == "held"
    assert held["result"]["holds"][0]["lifts_at"] == "2026-11-23T09:00:00Z"
    assert (await slash(app, owner, project, "/status"))["result"]["state"] == "held"
    assert (await slash(app, owner, project, "/resume"))["result"]["state"] == "running"

    best = await slash(app, owner, project, "/quality best")
    assert best["result"]["quality"] == "best"
    budget = await slash(app, owner, project, "/budget 30000000")
    assert budget["result"]["wall"] == 30_000_000
    history = (await app.ok("settings.history_project", owner, project_id=project))["items"]
    assert {
        h["name"]: h["reason"] for h in history if h["name"] in ("quality", "budget.tokens")
    } == {
        "quality": "Changed with a slash command in the project chat.",
        "budget.tokens": "Changed with a slash command in the project chat.",
    }
    brief = await slash(app, observer, project, "/brevity short")
    assert brief["operation"] == "chat.brevity"

    direct = await app.call("projects.hold", observer, project_id=project)
    via_slash = await app.call("chat.command", observer, project_id=project, text="/hold")
    assert (via_slash.status_code, via_slash.json()) == (direct.status_code, direct.json())
    for text in ("/budget 5", "/quality superb", "/explode"):
        refused = await app.call("chat.command", owner, project_id=project, text=text)
        assert refused.status_code in (403, 404, 422), text
    assert (await app.ok("budget.show", owner, project_id=project))["wall"] == 30_000_000
    unknown = await app.call("chat.command", owner, project_id=project, text="/pin this")
    assert unknown.json()["code"] == "unknown_command"


@pytest.mark.attack("MSG-9")
async def test_MSG_9_two_agents_looping_in_a_thread_are_frozen(app: App) -> None:
    """MSG-9: when a thread's last `thread.freeze_after` messages are from the same two
    agents and nothing else changed, the next post is refused, the chairman and the CEO are
    told, and only a chair can unfreeze it."""
    owner = await app.person("owner@example.com")
    observer = await app.person("observer@example.com")
    project = await running_project(app, owner, **{"thread.freeze_after": 4, "refusal.cap": 20})
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")
    await app.ok("roster.hire_team", owner, project_id=project, team="research", role="Generalist")
    ceo = await live_run(app, project)
    lead = await live_run(app, project, seat="research")
    for turn in range(4):
        speaker = ceo if turn % 2 == 0 else lead
        posted = await agent_call(
            app,
            speaker.token,
            "agent.post_message",
            body=f"After you ({turn}).",
            channel="leadership",
        )
        assert posted.status_code == 200, posted.text
    frozen = await agent_call(
        app, ceo.token, "agent.post_message", body="No, after you.", channel="leadership"
    )
    assert_refused(frozen, rule="MSG-9", code="thread_frozen")
    assert_refused(
        await agent_call(
            app, lead.token, "agent.post_message", body="Please.", channel="leadership"
        ),
        rule="MSG-9",
    )
    assert (
        len(
            (await app.ok("chat.history", owner, project_id=project, channel="leadership"))["items"]
        )
        == 4
    )
    told = (await app.ok("chat.history", owner, project_id=project))["items"][-1]
    assert "was frozen: 4 messages between two agents" in told["body"]

    assert_refused(
        await app.call("chat.unfreeze", observer, project_id=project, channel="leadership"),
        rule="ACC-5",
    )
    await app.ok("chat.unfreeze", owner, project_id=project, channel="leadership")
    unfrozen = await app.ok("record.list", owner, project_id=project, type="thread.unfrozen")
    assert unfrozen["items"][0]["actor"] == owner.person_id
    await app.ok("roster.hire_team", owner, project_id=project, team="ops", role="Generalist")
    again = await agent_call(
        app, ceo.token, "agent.post_message", body="A team was hired.", channel="leadership"
    )
    assert again.status_code == 200, again.text


async def test_CHAT_14_search_header_and_feed(app: App) -> None:
    """CHAT-14, CHAT-17, CHAT-18, CHAT-19, EXE-4: search finds messages and files; each
    person has their own read position; the header shows state, holds with what lifts them
    and the budget; the feed tells every change in plain words."""
    owner = await app.person("owner@example.com")
    cochair = await app.person("cochair@example.com")
    project = await running_project(app, owner)
    await app.ok("members.add", owner, project_id=project, email=cochair.email, role="co-chair")
    first = await app.ok(
        "chat.send", owner, project_id=project, body="The LLAMA pricing looks wrong."
    )
    await app.ok(
        "chat.send", cochair, project_id=project, body="Agreed, check the alpaca numbers too."
    )
    await app.ok(
        "artifacts.upload",
        owner,
        project_id=project,
        name="llama-prices.csv",
        content_base64="YSxi",
    )
    found = await app.ok("chat.search", owner, project_id=project, query="llama")
    assert first["id"] in [m["id"] for m in found["messages"]]
    assert found["artifacts"] == ["llama-prices.csv"]

    assert (await app.ok("chat.header", owner, project_id=project))["unread"] == 1
    assert (await app.ok("chat.header", cochair, project_id=project))["unread"] == 2
    last = (await app.ok("chat.history", owner, project_id=project))["items"][-1]["id"]
    await app.ok("chat.mark_read", owner, project_id=project, message_id=last)
    assert (await app.ok("chat.header", owner, project_id=project))["unread"] == 0
    assert (await app.ok("chat.header", cochair, project_id=project))["unread"] == 2

    await app.ok("projects.hold", owner, project_id=project, until="2026-11-23T09:00:00Z")
    header = await app.ok("chat.header", owner, project_id=project)
    assert header["state"] == "held"
    assert header["holds"] == [{"reason": "chairman", "lifts": "`/resume`, or its lift time"}]
    assert header["next"] == ["The hold lifts at 2026-11-23T09:00+00:00."]
    assert header["budget"] == "0 of 20,000,000 tokens used (0%)"
    feed = [
        item["text"] for item in (await app.ok("record.feed", owner, project_id=project))["items"]
    ]
    assert "The project went from draft to running." in feed
    assert "A hold was added: chairman. It lifts by `/resume`, or its lift time." in feed
    assert any(text.startswith("owner saved version 1 of llama-prices.csv") for text in feed)
