"""The v1 frustrations of themes 1 and 5 as scripted scenarios (NFR-19, P15, P16).

Each scenario is a behaviour with a floor: the thing the chairman said once must be in
front of the agent afterwards, and the thing the agent must not do must fail.
"""

from __future__ import annotations

from tests.conftest import FakeClock
from tests.support import App, agent_call, live_run, running_project


async def chat_history(app: App, owner: object, project: str) -> list[dict[str, object]]:
    return (await app.ok("chat.history", owner, project_id=project))["items"]  # type: ignore[arg-type]


async def test_scenario_a_standing_order_is_in_front_of_every_later_run(app: App) -> None:
    """Theme 1, "a standing order ignored" (MSG-4, INV-25): once pinned, the order is in the
    pack of the CEO's next chat run and next work run, and of a team member hired later."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("orders.pin", owner, project_id=project, what="Never quote prices with taxes.")

    await app.ok("chat.send", owner, project_id=project, body="What will it cost?")
    work = await live_run(app, project)
    hire = await agent_call(app, work.token, "agent.hire_team", team="pricing", role="Generalist")
    assert hire.status_code == 200, hire.text
    chat = await live_run(app, project)
    pack = (await agent_call(app, chat.token, "agent.context")).json()
    assert pack["run_kind"] == "chat"
    assert "Never quote prices with taxes." in pack["context_pack"]
    await agent_call(app, chat.token, "agent.post_message", body="About 40 a month.")
    hired = await live_run(app, project, seat="pricing")
    later = (await agent_call(app, hired.token, "agent.context")).json()["context_pack"]
    assert "[order 1] Never quote prices with taxes." in later


async def test_scenario_a_question_answered_sideways_is_asked_again(app: App) -> None:
    """Theme 1, "a question answered sideways" (MSG-6, CHAT-11, CHAT-12): after `/fix` the
    agent is asked again, its next reply quotes the original question, the correction is in
    its pack, and its listening score shows one correction in two replies."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    app.script("CEO/chat", {"text": "It takes three weeks."})
    await app.ok("chat.send", owner, project_id=project, body="What does it cost per month?")
    assert await app.work() == 1

    await app.ok("chat.command", owner, project_id=project, text="/fix I asked about cost.")
    app.script("CEO/chat", {"text": "About 40 a month."})
    assert await app.work() == 1
    history = await chat_history(app, owner, project)
    assert history[-1]["body"] == "> What does it cost per month?\n\nAbout 40 a month."
    assert history[-1]["reply_to"] == history[-2]["id"]

    ceo = (await app.ok("roster.show", owner, project_id=project))["seats"][0]
    assert (ceo["replies"], ceo["corrections"], ceo["listening_score"]) == (2, 1, 50.0)


async def test_scenario_a_wordy_reply_is_rewritten_once(app: App) -> None:
    """MSG-12, CHAT-13, P1: a reply over the reader's brevity budget is sent back once and
    the rewrite is posted. A reply that is still too long posts with the "long" marker. Both
    runs finish normally: feedback is never a refusal."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("chat.brevity", owner, level="short")
    app.script("CEO/chat", {"text": "word " * 80}, {"text": "Yes: it is ready."})
    await app.ok("chat.send", owner, project_id=project, body="Is it ready?")
    assert await app.work() == 1
    history = await chat_history(app, owner, project)
    assert (history[-1]["body"], history[-1]["detail"]) == ("Yes: it is ready.", None)

    app.script("CEO/chat", {"text": "word " * 80}, {"text": "word " * 70})
    await app.ok("chat.send", owner, project_id=project, body="And the plan?")
    assert await app.work() == 1
    history = await chat_history(app, owner, project)
    assert history[-1]["detail"] == {"lint": "long"}
    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert {run["state"] for run in runs} == {"finished"}


async def test_scenario_status_posts_wait_for_the_slot_but_replies_do_not(
    app: App, clock: FakeClock
) -> None:
    """MSG-8, P1: with a reporting cadence, the CEO's unprompted status post is held, not
    refused, and goes out at the next slot. A reply to the chairman goes out at once."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"report.cadence": 1})
    run = await live_run(app, project)
    held = await agent_call(app, run.token, "agent.post_message", body="Research is half done.")
    assert held.status_code == 200
    assert held.json()["posted"] is False
    assert held.json()["held_until"].startswith("2026-11-22T08:00")
    assert await chat_history(app, owner, project) == []

    asked = await app.ok("chat.send", owner, project_id=project, body="Any blockers?")
    reply = await agent_call(app, run.token, "agent.post_message", body="None so far.")
    assert (reply.json()["posted"], reply.json()["reply_to"]) == (True, asked["id"])

    await app.scheduler.tick()
    assert len(await chat_history(app, owner, project)) == 2
    clock.advance(hours=23)
    await app.scheduler.tick()
    history = await chat_history(app, owner, project)
    assert history[-1]["body"] == "Research is half done."
    assert history[-1]["detail"] == {"kind": "held report"}
    await app.scheduler.tick()
    assert len(await chat_history(app, owner, project)) == 3


async def test_scenario_chat_words_change_nothing_without_a_directive(app: App) -> None:
    """Theme 5, "chat acted on without a directive" (INV-23, MSG-3, P15): asked in plain
    chat to hire a team, a CEO that tries is refused and the roster does not change. The
    same words as a directive are carried out."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    hire = {"name": "agent_hire_team", "arguments": {"team": "ops", "role": "Generalist"}}
    app.script("CEO/chat", {"text": "", "tools": [hire]}, {"text": "I can propose that."})
    await app.ok("chat.send", owner, project_id=project, body="Hire an ops team.")
    assert await app.work() == 1
    assert (await app.ok("roster.show", owner, project_id=project))["teams"] == []

    app.script("CEO", {"text": "", "tools": [hire]}, {"text": "Hired."})
    await app.ok("chat.command", owner, project_id=project, text="/do Hire an ops team.")
    await app.work()
    assert (await app.ok("roster.show", owner, project_id=project))["teams"] == ["ops"]


async def test_scenario_an_example_used_as_data_is_flagged(app: App) -> None:
    """Theme 1, "an example used as data" (MSG-7): a deliverable that uses a figure the
    chairman gave only inside an example is flagged in the chat and its author is told. A
    figure the chairman also gave as data is not flagged."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("chat.send", owner, project_id=project, body="We have 240 customers today.")
    await app.ok(
        "chat.command", owner, project_id=project,
        text="/example A plan might say revenue of 5,000,000 from 240 customers.",
    )  # fmt: skip
    run = await live_run(app, project)
    published = await agent_call(
        app, run.token, "agent.publish_artifact", name="plan.md",
        content="We expect revenue of 5000000 from 240 customers in 12 months.",
        purpose="The launch plan",
    )  # fmt: skip
    assert published.status_code == 200, published.text
    flag = (await chat_history(app, owner, project))[-1]
    assert flag["detail"] == {
        "kind": "example figure",
        "artifact": "plan.md",
        "figures": ["5000000"],
    }
    assert "5000000" in str(flag["body"])
    assert "240" not in str(flag["body"]).replace("plan.md", "")

    clean = await agent_call(
        app, run.token, "agent.publish_artifact", name="plan.md",
        content="We expect 240 customers to renew.", purpose="The launch plan",
    )  # fmt: skip
    assert clean.status_code == 200
    kinds = [m["detail"] for m in await chat_history(app, owner, project) if m["detail"]]
    assert sum(1 for d in kinds if d.get("kind") == "example figure") == 1  # type: ignore[union-attr]


async def test_scenario_a_closed_decision_is_not_reargued(app: App, clock: FakeClock) -> None:
    """Theme 1, "a closed decision re-argued" (MSG-5, INV-26): the ruling is in the pack, a
    scripted CEO that asks to reopen it with nothing new is refused, and the ruling stands."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok("chat.command", owner, project_id=project, text="/decide Launch: in spring.")
    reopen = {
        "name": "agent_request_reopen",
        "arguments": {
            "decision_id": 1,
            "reason": "I still think autumn would be the better time.",
            "evidence": [{"kind": "message", "ref": "1"}],
        },
    }
    app.script("CEO", {"text": "", "tools": [reopen]}, {"text": "Understood: spring."})
    clock.advance(minutes=1)
    await app.ok("chat.send", owner, project_id=project, body="When do we launch?")
    await app.work()
    decision = (await app.ok("decisions.list", owner, project_id=project))["items"][0]
    assert (decision["state"], decision["ruling"]) == ("closed", "in spring.")
    assert (await app.ok("decisions.requests", owner, project_id=project))["items"] == []
    trace_runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    assert trace_runs
    history = await chat_history(app, owner, project)
    assert history[-1]["body"] == "Understood: spring."
