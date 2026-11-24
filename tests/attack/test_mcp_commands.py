"""Attacks on MCP servers started from a command: tested before saving, given only their own
variables, never added by a model client, used by agents like any server (CON-11, IF-5.6)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nightsquad.catalog.registry import catalog
from nightsquad.domain.secrets.store import ensure_master_key
from nightsquad.surfaces.mcp.server import tool_name
from tests.attack.harness import assert_refused
from tests.attack.test_mcp import client_for, mcp_caller
from tests.attack.test_mcp_calls import mcp_call
from tests.support import App, live_run, running_project

SCRIPT = Path(__file__).with_name("mcp_stdio_server.py")
COMMAND = f"{sys.executable} {SCRIPT}"
TOKEN = "notes-token-5521-unguessable"


@pytest.fixture(autouse=True)
def master_key(app: App) -> None:
    ensure_master_key(app.runtime.config.master_key_file)


@pytest.mark.attack("CON-11")
async def test_CON_11_a_command_server_runs_with_only_its_own_variables_and_serves_agents(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CON-11, CON-12, CON-13: the command is tested before it is saved; it sees the secret
    it was given and nothing of the host's environment; its reading tools are offered to
    agents, who use them through nightsquad; it stops when the install closes."""
    monkeypatch.setenv("NIGHTSQUAD_HOST_ONLY", "host-value")
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok(
        "connections.add_secret", owner, name="notes-token", description="The notes service token.",
        value=TOKEN, delivery="given", env_name="NOTES_TOKEN",
    )  # fmt: skip
    added = await app.ok(
        "connections.add_command_mcp_server", owner, name="notes", description="Notes tools.",
        command=COMMAND, environment={"BLOG_TOKEN": "notes-token"}, project_id=project,
        roles=["*"],
    )  # fmt: skip
    assert added["mcp"]["transport"] == "stdio"
    tools = {tool["name"]: tool["permission"] for tool in added["mcp"]["tools"]}
    assert tools == {
        "token_length": "allowed",
        "environment_names": "allowed",
        "write_note": "denied",
    }
    assert TOKEN not in str(added)

    run = await live_run(app, project)
    length = await mcp_call(app, run.token, added["id"], "token_length")
    assert length.status_code == 200, length.text
    assert length.json()["content"] == str(len(TOKEN))
    names = (await mcp_call(app, run.token, added["id"], "environment_names")).json()["content"]
    assert "BLOG_TOKEN" in names
    assert "NIGHTSQUAD_HOST_ONLY" not in names
    assert app.runtime.commands.running() == [added["id"]]
    await app.runtime.commands.close()
    assert app.runtime.commands.running() == []


@pytest.mark.attack("CON-11")
async def test_CON_11_a_broken_command_saves_nothing_and_a_model_client_cannot_add_one(
    app: App,
) -> None:
    """CON-11, IF-5.6, CON-7: a command that does not start is refused with a reason and
    saves nothing; a reserved variable name is refused; a model client is never offered
    the operation."""
    owner = await app.person("owner@example.com")
    broken = await app.call(
        "connections.add_command_mcp_server", owner, name="broken", description="Broken.",
        command=f"{sys.executable} -c 'raise SystemExit(3)'",
    )  # fmt: skip
    assert_refused(broken, rule="CON-11", code="mcp_unreachable")
    assert (await app.ok("connections.list", owner))["items"] == []
    await app.ok(
        "connections.add_variable", owner, name="dir", description="A folder.", value="/tmp"
    )
    reserved = await app.call(
        "connections.add_command_mcp_server", owner, name="bad", description="Bad.",
        command=COMMAND, environment={"LD_PRELOAD": "dir"},
    )  # fmt: skip
    assert_refused(reserved, rule="CON-7", code="env_name_reserved")
    assert catalog.get("connections.add_command_mcp_server").mcp_scope is None
    minted = await app.ok("mcp_clients.mint", owner, client_name="Helper", scopes=["configure"])
    async with client_for(app, await mcp_caller(app, minted["token"])) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
    assert tool_name("connections.add_command_mcp_server") not in listed
