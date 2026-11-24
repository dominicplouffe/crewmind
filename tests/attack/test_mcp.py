"""Attacks through an MCP client (IF-5.1, IF-5.2, IF-5.6, INV-5)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from mcp import Client

from nightsquad.catalog import catalog, mcp_scopes, registry
from nightsquad.catalog.caller import Caller
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.server import create_app
from nightsquad.surfaces.mcp.server import build_mcp, tool_name
from tests.attack.harness import assert_refused
from tests.conftest import FakeClock
from tests.support import App

HUMAN_ONLY = (
    "members.add",
    "members.set_role",
    "members.remove",
    "members.hand_on_chair",
    "projects.delete",
    "projects.confirm_delete",
    "mcp_clients.mint",
    "tokens.mint",
)


async def mcp_caller(app: App, token: str) -> Caller:
    return await app.runtime.authenticator.authenticate(token, on_mcp=True)


def client_for(app: App, caller: Caller) -> Client:
    async def caller_of(_: Any) -> Caller:
        return caller

    return Client(build_mcp(catalog, app.runtime.executor, caller_of))


@pytest.mark.attack("IF-5.2")
async def test_IF_5_2_a_read_client_sees_and_calls_only_read_tools(app: App) -> None:
    """IF-5.2, IF-5.6: with the read scope, no write and no human-only operation is listed,
    and calling one answers exactly like a tool that does not exist."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    minted = await app.ok("mcp_clients.mint", owner, client_name="Desk assistant")
    caller = await mcp_caller(app, minted["token"])
    assert caller.via == "mcp:Desk assistant"
    async with client_for(app, caller) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
        by_tool = {tool_name(operation.name): operation for operation in catalog}
        assert len(listed) >= 8
        for name in listed:
            assert by_tool[name].reversibility is Reversibility.READ, name
        for name in HUMAN_ONLY:
            assert tool_name(name) not in listed
        missing = await client.call_tool("no_such_tool", {})
        for name in ("projects.hold", "projects.stop", "settings.change_project", *HUMAN_ONLY):
            result = await client.call_tool(tool_name(name), {"project_id": project})
            assert result.is_error
            assert result.structured_content is not None
            assert result.structured_content["code"] == "unknown_tool"
            assert set(result.structured_content) == set(missing.structured_content or {})
        status = await client.call_tool("projects_status", {"project_id": project})
        assert status.structured_content is not None
        assert status.structured_content["state"] == "draft"


@pytest.mark.attack("IF-5.2")
@pytest.mark.attack("IF-5.6")
async def test_IF_5_2_a_scope_reaches_its_own_tools_and_human_only_verbs_reach_none(
    app: App,
) -> None:
    """IF-5.2, IF-5.6: four scopes, with read implied by the others. A steer client holds
    and resumes a project but cannot configure it. No scope lists or calls a human-only
    verb, a scope that does not exist cannot be minted, and a client stripped of its
    scopes sees nothing."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    for scopes in (["admin"], ["read", "everything"], []):
        refused = await app.call("mcp_clients.mint", owner, client_name="Greedy", scopes=scopes)
        assert_refused(refused, rule="IF-5.2", code="scope_unavailable")

    steer = await app.ok("mcp_clients.mint", owner, client_name="Steerer", scopes=["steer"])
    caller = await mcp_caller(app, steer["token"])
    assert caller.mcp_scopes == {"read", "steer"}
    async with client_for(app, caller) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
        assert {"projects_start", "projects_hold", "chat_send", "items_decide"} <= listed
        assert not {"settings_change_project", "roster_hire_team", "projects_create"} & listed
        started = await client.call_tool("projects_start", {"project_id": project})
        assert started.structured_content is not None
        assert started.structured_content["state"] == "running"
        widened = await client.call_tool(
            "settings_change_project",
            {"project_id": project, "changes": {"run.concurrency": 8}, "reason": "More, please."},
        )
        assert (widened.structured_content or {})["code"] == "unknown_tool"

    everything = await app.ok(
        "mcp_clients.mint", owner, client_name="All four",
        scopes=["read", "steer", "create", "configure"],
    )  # fmt: skip
    async with client_for(app, await mcp_caller(app, everything["token"])) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
        assert {"settings_change_project", "roster_hire_team", "projects_create"} <= listed
        for name in mcp_scopes.HUMAN_ONLY:
            assert tool_name(name) not in listed, name
            result = await client.call_tool(tool_name(name), {"project_id": project})
            assert (result.structured_content or {})["code"] == "unknown_tool", name

    stripped = Caller(caller.kind, caller.actor_id, role=caller.role, via=caller.via)
    async with client_for(app, stripped) as client:
        assert (await client.list_tools()).tools == []
        result = await client.call_tool("auth_whoami", {})
        assert (result.structured_content or {})["code"] == "unknown_tool"


def test_IF_5_2_every_person_operation_has_a_scope_or_a_stated_reason() -> None:
    """IF-5.2, IF-5.6, section 9: anything a person can do, an MCP client can do within
    its scope, except the human-only verbs and the person's own account. An operation
    that is neither scoped nor listed with its reason fails here."""
    registry.load_domain_modules()
    for operation in catalog:
        if Principal.PERSON not in operation.principals:
            continue
        reachable = operation.mcp_scope in mcp_scopes.SCOPES
        excused = operation.name in {**mcp_scopes.HUMAN_ONLY, **mcp_scopes.NOT_FOR_CLIENTS}
        assert reachable != excused, operation.name


@pytest.mark.attack("IF-5.3")
@pytest.mark.attack("7.10")
async def test_IF_5_3_an_irreversible_write_needs_two_calls(app: App, clock: FakeClock) -> None:
    """IF-5.3, IF-5.4, 7.10: stopping a project through MCP first returns a preview and a
    confirm token. The token works once, for that tool and those exact arguments, for
    that client, within 5 minutes. The write is recorded as the person acting through
    the named client."""
    owner = await app.person("owner@example.com")
    first, second = await app.project(owner), await app.project(owner, name="Other")
    minted = await app.ok("mcp_clients.mint", owner, client_name="Steerer", scopes=["steer"])
    other = await app.ok("mcp_clients.mint", owner, client_name="Another", scopes=["steer"])
    async with client_for(app, await mcp_caller(app, minted["token"])) as client:
        preview = (
            await client.call_tool("projects_stop", {"project_id": first})
        ).structured_content
        assert preview is not None
        assert preview["confirm_required"] is True
        assert preview["arguments"] == {"project_id": first}
        assert (await app.ok("projects.status", owner, project_id=first))["state"] == "draft"
        token = preview["confirm"]

        async def stop(project: str, confirm: str) -> dict[str, Any]:
            result = await client.call_tool(
                "projects_stop", {"project_id": project, "confirm": confirm}
            )
            return result.structured_content or {}

        assert (await stop(second, token))["code"] == "confirm_token_does_not_match"
        assert (await stop(first, "ns_confirm_guess"))["code"] == "confirm_token_does_not_match"
        async with client_for(app, await mcp_caller(app, other["token"])) as stranger:
            stolen = await stranger.call_tool(
                "projects_stop", {"project_id": first, "confirm": token}
            )
            assert (stolen.structured_content or {})["code"] == "confirm_token_does_not_match"
        assert (await stop(first, token))["state"] == "stopped"
        assert (await stop(first, token))["code"] == "confirm_token_spent"

        late = (await client.call_tool("projects_stop", {"project_id": second})).structured_content
        assert late is not None
        clock.advance(minutes=6)
        assert (await stop(second, late["confirm"]))["code"] == "confirm_token_expired"
    owner = await app.login(owner.email)
    assert (await app.ok("projects.status", owner, project_id=second))["state"] == "draft"
    stopped = [
        event
        for event in await app.events(owner, first)
        if event["type"] == "project.state_changed"
    ][-1]
    assert (stopped["actor"], stopped["via"]) == (owner.person_id, "mcp:Steerer")


@pytest.mark.attack("IF-5.7")
async def test_IF_5_7_a_payload_is_cut_to_the_budget_and_says_so(app: App) -> None:
    """IF-5.7, IF-5.5: a tool summarises by default: about 600 characters per string, 20
    items per list. Full detail is returned on request. Whatever is cut is marked in the
    payload, and agent-written text still arrives inside its envelope."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    long_text = "The site has a home page. " * 30
    for number in range(25):
        await app.ok(
            "requirements.add", owner, project_id=project,
            text=f"{long_text}Requirement number {number}.", test_kind="observable",
            success_test="A visitor can open the home page.",
        )  # fmt: skip
    minted = await app.ok("mcp_clients.mint", owner, client_name="Reader")
    async with client_for(app, await mcp_caller(app, minted["token"])) as client:
        short = (await client.call_tool("plan_show", {"project_id": project})).structured_content
        assert short is not None
        assert len(short["requirements"]) <= 20
        assert "[truncated:" in short["requirements"][0]["text"]
        assert "a list of 25 items was cut" in short["truncated"]
        assert "detail set to full" in short["truncated"]
        assert len(json.dumps(short)) <= 6_000 + len(short["truncated"]) + 20
        full = (
            await client.call_tool("plan_show", {"project_id": project, "detail": "full"})
        ).structured_content
        assert full is not None
        assert len(full["requirements"]) == 25
        assert full["requirements"][0]["text"].endswith("Requirement number 0.")
        assert "truncated" not in full


@pytest.mark.attack("IF-5.8")
async def test_IF_5_8_resources_and_prompts_show_only_what_the_person_may_see(app: App) -> None:
    """IF-5.8, INV-5: the desk and each of the person's projects are resources, with the
    documents the server itself uses. Another person's project is not listed and cannot
    be read. The four prompts are offered."""
    owner = await app.person("owner@example.com")
    outsider = await app.person("outsider@example.com")
    mine = await app.project(owner)
    theirs = await app.project(outsider, name="Secret")
    minted = await app.ok("mcp_clients.mint", owner, client_name="Reader")
    async with client_for(app, await mcp_caller(app, minted["token"])) as client:
        listed = {str(resource.uri) for resource in (await client.list_resources()).resources}
        assert listed == {
            "nightsquad://desk",
            "nightsquad://documents/output-standard",
            "nightsquad://documents/design-doctrine",
            "nightsquad://documents/goal-grammar",
            f"nightsquad://projects/{mine}",
        }
        project = await client.read_resource(f"nightsquad://projects/{mine}")
        body = json.loads(project.contents[0].text)  # type: ignore[union-attr]
        assert body["status"]["state"] == "draft"
        assert body["plan"]["requirements"] == []
        secret = await client.read_resource(f"nightsquad://projects/{theirs}")
        hidden = json.loads(secret.contents[0].text)  # type: ignore[union-attr]
        assert hidden["status"]["code"] == "project_not_found"
        standard = await client.read_resource("nightsquad://documents/output-standard")
        assert "plain" in standard.contents[0].text.lower()  # type: ignore[union-attr]
        from nightsquad.domain.founder import drafting

        served = ""
        for name in ("design-doctrine", "goal-grammar"):
            page = await client.read_resource(f"nightsquad://documents/{name}")
            served += page.contents[0].text  # type: ignore[union-attr]
        for line in ("how a nightsquad project is drafted", "`failure_deliverable`"):
            assert line in served
            assert line in drafting.doctrine_text()
        prompts = {prompt.name for prompt in (await client.list_prompts()).prompts}
        assert prompts == {
            "design_a_project",
            "todays_brief",
            "why_is_a_project_at_risk",
            "spot_audit",
        }
        brief = await client.get_prompt("todays_brief")
        assert "desk_show" in brief.messages[0].content.text  # type: ignore[union-attr]


@pytest.mark.attack("INV-5")
@pytest.mark.attack("IF-5.2")
async def test_INV_5_an_mcp_client_sees_only_its_persons_projects(app: App) -> None:
    """INV-5, IF-5.2: another person's project answers like one that does not exist."""
    owner = await app.person("owner@example.com")
    outsider = await app.person("outsider@example.com")
    project = await app.project(owner)
    minted = await app.ok("mcp_clients.mint", outsider, client_name="Snoop")
    async with client_for(app, await mcp_caller(app, minted["token"])) as client:
        listed = await client.call_tool("projects_list", {})
        assert listed.structured_content is not None
        assert listed.structured_content["items"] == []
        answers: list[Any] = []
        for project_id in (project, uuid.uuid4().hex):
            result = await client.call_tool("record_list", {"project_id": project_id})
            answers.append(result.structured_content)
        assert answers[0] == answers[1]
        assert answers[0] is not None
        assert answers[0]["code"] == "project_not_found"


@pytest.mark.attack("IF-5.2")
async def test_IF_5_1_the_mcp_endpoint_takes_only_a_live_mcp_token(app: App) -> None:
    """IF-5.1, section 9.2: no token, a personal token, a session and a revoked MCP token
    are all refused at the endpoint; an MCP token is refused on the human API."""
    owner = await app.person("owner@example.com")
    personal = (await app.ok("tokens.mint", owner, name="laptop"))["token"]
    revoked = await app.ok("mcp_clients.mint", owner, client_name="Old")
    await app.ok("mcp_clients.revoke", owner, token_id=revoked["token_id"])
    live = (await app.ok("mcp_clients.mint", owner, client_name="Desk assistant"))["token"]
    server = create_app(app.runtime, run_scheduler=False)
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8420") as http:
        for credential in (None, personal, owner.token, revoked["token"], "ns_mcp_forged"):
            headers = {"Authorization": f"Bearer {credential}"} if credential else {}
            response = await http.post("/mcp", json={}, headers=headers)
            assert response.status_code == 401, credential
            assert response.json()["code"] == "unauthenticated"
    assert (await app.call("auth.whoami", live)).status_code == 401
    events = await app.ok("record.list_install", await app.admin(), type="token.minted")
    assert any(event["after"]["kind"] == "mcp" for event in events["items"])
