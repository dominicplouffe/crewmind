"""The phase 1 exit demo, as a scenario (PLAN.md phase 1; INV-21, IF-1.2, IF-5.4).

Create a user and a project, change a setting with a reason, start, hold and resume. Then
see every change in the event log from the API, the CLI and an MCP client.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp import Client

from crewmind.catalog import Surface, catalog
from crewmind.catalog.caller import Caller
from crewmind.catalog.execute import Executor
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.surfaces import exposed_on
from crewmind.domain.secrets.store import ensure_master_key
from crewmind.surfaces.cli.invoke import LocalInvoker
from crewmind.surfaces.cli.main import build_cli
from crewmind.surfaces.mcp.server import build_mcp
from tests.attack.test_models import FakeProvider
from tests.support import App, OnLoop, agent_call, invoker_for, live_run, run_cli

EXPECTED = [
    "project.created",
    "member.added",
    "seat.created",
    "setting.changed",
    "setting.changed",
    "project.state_changed",
    "project.hold_added",
    "project.state_changed",
    "project.hold_lifted",
    "project.state_changed",
]


async def test_phase_1_exit_demo_every_change_is_in_the_event_log_on_every_surface(
    app: App,
) -> None:
    """INV-21, IF-1.2, IF-3.8, IF-5.4: the same log through the API, the CLI and MCP, with
    actor, time, before and after for every change."""
    chairman = await app.person("dominic@example.com")
    project = await app.project(chairman)
    changed = await app.ok(
        "settings.change_project",
        chairman,
        project_id=project,
        changes={"run.concurrency": 6},
        reason="More parallel work for the launch.",
    )
    concurrency = next(i for i in changed["items"] if i["name"] == "run.concurrency")
    assert (concurrency["value"], concurrency["version"]) == (6, 1)
    assert (await app.ok("projects.start", chairman, project_id=project))["state"] == "running"
    assert (await app.ok("projects.hold", chairman, project_id=project))["state"] == "held"
    assert (await app.ok("projects.resume", chairman, project_id=project))["state"] == "running"

    from_api = await app.events(chairman, project)
    assert [event["type"] for event in from_api] == EXPECTED
    for event in from_api:
        if event["type"] == "seat.created":
            continue
        assert event["actor"] == chairman.person_id
        assert event["actor_kind"] == "person"
        assert event["via"] == "direct"
        assert event["at"]
    setting = from_api[4]
    assert setting["before"] == {"value": 4}
    assert setting["after"] == {"value": 6}
    assert setting["detail"]["reason"] == "More parallel work for the launch."
    states = [(e["before"], e["after"]) for e in from_api if e["type"] == "project.state_changed"]
    assert states == [
        ({"state": "draft"}, {"state": "running"}),
        ({"state": "running"}, {"state": "held"}),
        ({"state": "held"}, {"state": "running"}),
    ]

    async def executor() -> Executor:
        return app.runtime.executor

    invoker = OnLoop(invoker_for(app.api, chairman.token))
    cli = build_cli(catalog, invoker, OnLoop(LocalInvoker(executor)))
    listed = await run_cli(
        cli, ["record", "list", "--project-id", project, "--limit", "200", "--json"]
    )
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout)["items"] == from_api

    minted = await app.ok("mcp_clients.mint", chairman, client_name="Desk assistant")
    caller = await app.runtime.authenticator.authenticate(minted["token"], on_mcp=True)

    async def caller_of(_: Any) -> Caller:
        return caller

    async with Client(build_mcp(catalog, app.runtime.executor, caller_of)) as client:
        result = await client.call_tool("record_list", {"project_id": project, "limit": 200})
    assert result.structured_content is not None
    assert result.structured_content["items"] == from_api


async def test_INV_21_every_write_operation_records_an_event(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-21: every state change appears in the event log. Each write operation is called
    once here, and each must add at least one event naming its actor."""
    from sqlalchemy import func, select

    from crewmind.storage.models import Event

    async def events() -> int:
        async with app.runtime.sessions() as session:
            return await session.scalar(select(func.count()).select_from(Event)) or 0

    recorded: set[str] = set()
    ensure_master_key(app.runtime.config.master_key_file)
    FakeProvider(monkeypatch)

    async def write(name: str, actor: Any, /, **values: Any) -> dict[str, Any]:
        before = await events()
        result = await app.ok(name, actor, **values)
        assert await events() > before, f"{name} changed state without an event"
        recorded.add(name)
        return result

    admin = await app.admin()
    invite = await write("people.invite", admin, email="a@example.com", name="A")
    await write("auth.use_link", None, link=invite["link"], password="a long enough password")
    session = await write(
        "auth.login", None, email="a@example.com", password="a long enough password"
    )
    alice = session["session"]
    await write(
        "auth.change_password",
        alice,
        current_password="a long enough password",
        new_password="another long password",
    )
    alice = (
        await write("auth.login", None, email="a@example.com", password="another long password")
    )["session"]
    bob = await app.person("bob@example.com")
    await write("people.set_role", admin, person_id=bob.person_id, role="admin")
    await write("people.reset_link", admin, person_id=bob.person_id)
    token = await write("tokens.mint", alice, name="laptop")
    await write("tokens.revoke", alice, token_id=token["token_id"])
    mcp = await write("mcp_clients.mint", alice, client_name="Desk")
    await write("mcp_clients.revoke", alice, token_id=mcp["token_id"])
    await write("settings.change_mine", alice, changes={"chat.brevity": "short"})
    await write(
        "settings.change_install", admin, changes={"delete.grace": 86_400}, reason="Shorter grace."
    )
    project = (await write("projects.create", alice, name="Atlas", type="operate", goal="Run it."))[
        "project_id"
    ]
    await write(
        "settings.change_project",
        alice,
        project_id=project,
        changes={"cycle.period": "daily"},
        reason="A daily rhythm fits this.",
    )
    await write("members.add", alice, project_id=project, email=bob.email, role="observer")
    await write(
        "members.set_role", alice, project_id=project, person_id=bob.person_id, role="co-chair"
    )
    await write("members.hand_on_chair", alice, project_id=project, person_id=bob.person_id)
    await write(
        "members.break_glass_hand_on",
        admin,
        project_id=project,
        person_id=session["person_id"],
        reason="Returning the chair.",
    )
    await write("members.remove", alice, project_id=project, person_id=bob.person_id)
    await write("roster.hire_team", alice, project_id=project, team="research", role="Generalist")
    await write("roster.stand_down_team", alice, project_id=project, team="research")
    await write("roster.recall_team", alice, project_id=project, team="research")
    await write("chat.send", alice, project_id=project, body="Hello, team.")
    await write("projects.start", alice, project_id=project)
    await write("projects.hold", alice, project_id=project)
    await write("projects.resume", alice, project_id=project)
    await write("projects.stop", alice, project_id=project)
    code = (await write("projects.delete", alice, project_id=project))["confirmation"]
    await write(
        "projects.confirm_delete", alice, project_id=project, confirmation=code, name="Atlas"
    )
    await write("projects.cancel_delete", alice, project_id=project)
    for name in ("add", "smoke", "refresh_lineup", "hide", "show"):
        extra = {"provider": "anthropic", "key": "sk-test-key"} if name == "add" else {}
        await write(f"credentials.{name}", alice, name="main", **extra)
    await write(
        "credentials.override_lineup", admin, name="main", model_class="fast", model="claude-x"
    )
    created = await write("projects.create", alice, name="Paid", type="deliver", goal="x")
    paid = created["project_id"]
    await write("models.set_payer", alice, project_id=paid, credential="main")
    await write("models.set_seat", alice, project_id=paid, seat="CEO", effort="low")
    await write("models.set_ceiling", admin, provider="anthropic", max_concurrent=3)
    await write("artifacts.upload", alice, project_id=paid, name="a.txt", content_base64="YQ==")
    await write("artifacts.mark", alice, project_id=paid, name="a.txt", mark="reference")
    await write("artifacts.lock", alice, project_id=paid, name="a.txt")
    await write("artifacts.unlock", alice, project_id=paid, name="a.txt")
    begun = await app.ok("uploads.begin", alice, project_id=paid, name="b.txt", size=0)
    await write("uploads.finish", alice, project_id=paid, upload_id=begun["upload_id"])
    await write("projects.start", alice, project_id=paid)
    await write("directives.issue", alice, project_id=paid, instruction="Write the plan.")
    await write("chat.command", alice, project_id=paid, text="/hold")
    await write("chat.quality", alice, project_id=paid, level="fast")
    await write("budget.command", alice, project_id=paid, tokens=5_000_000)
    await write("chat.brevity", alice, level="detailed")
    live = await live_run(app, paid)
    proposal = {"what": "Draft the launch plan.", "estimated_tokens": 1000, "reversible": True}
    for decision in ("accept", "dismiss"):
        await agent_call(app, live.token, "agent.propose_action", **proposal)
        card = (await app.ok("cards.list", alice, project_id=paid))["items"][-1]["id"]
        await write(f"cards.{decision}", alice, project_id=paid, card_id=card)
    await write("runs.interrupt", alice, project_id=paid, run_id=live.run_id)
    await write("credentials.delete", alice, name="main")
    await write("people.deactivate", admin, person_id=bob.person_id)
    await write("people.reactivate", admin, person_id=bob.person_id)
    await write("auth.logout", alice)

    writes = {
        operation.name
        for operation in catalog
        if operation.reversibility is not Reversibility.READ and exposed_on(operation, Surface.API)
    }
    assert recorded == writes - set(NO_EVENT)


# Writes that change no governed state, so they record no event (INV-21), and one covered
# by its own test.
NO_EVENT = {
    "chat.mark_read": "a person's own read position",
    "uploads.begin": "an upload in progress is not yet an artifact",
    "chat.unfreeze": "asserted in test_MSG_9_two_agents_looping_in_a_thread_are_frozen",
}
