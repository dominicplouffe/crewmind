"""Attacks through an MCP client (IF-5.1, IF-5.2, IF-5.6, INV-5)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from mcp import Client

from crewmind.catalog import catalog
from crewmind.catalog.caller import Caller
from crewmind.catalog.operation import Reversibility
from crewmind.server import create_app
from crewmind.surfaces.mcp.server import build_mcp, tool_name
from tests.attack.harness import assert_refused
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
async def test_IF_5_2_only_the_read_scope_can_be_minted_and_scopes_cannot_widen(app: App) -> None:
    """IF-5.2: asking for a wider scope is refused, and a client with no scope sees nothing."""
    owner = await app.person("owner@example.com")
    for scopes in (["steer"], ["read", "configure"], []):
        refused = await app.call("mcp_clients.mint", owner, client_name="Greedy", scopes=scopes)
        assert_refused(refused, rule="IF-5.2", code="scope_unavailable")
    minted = await app.ok("mcp_clients.mint", owner, client_name="Desk assistant")
    caller = await mcp_caller(app, minted["token"])
    stripped = Caller(caller.kind, caller.actor_id, role=caller.role, via=caller.via)
    async with client_for(app, stripped) as client:
        assert (await client.list_tools()).tools == []
        result = await client.call_tool("auth_whoami", {})
        assert result.structured_content is not None
        assert result.structured_content["code"] == "unknown_tool"


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
        for credential in (None, personal, owner.token, revoked["token"], "cm_mcp_forged"):
            headers = {"Authorization": f"Bearer {credential}"} if credential else {}
            response = await http.post("/mcp", json={}, headers=headers)
            assert response.status_code == 401, credential
            assert response.json()["code"] == "unauthenticated"
    assert (await app.call("auth.whoami", live)).status_code == 401
    events = await app.ok("record.list_install", await app.admin(), type="token.minted")
    assert any(event["after"]["kind"] == "mcp" for event in events["items"])
