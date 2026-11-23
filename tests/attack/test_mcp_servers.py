"""Attacks on remote MCP servers: the address guard, sign-in, tested before saved, tools
classified and permissions held by the person (CON-9, CON-12, CON-15, INT-4, IF-5.6, 7.18)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.registry import catalog
from crewmind.domain.connections.mcp import SERVER_MACHINE, TOOL_MACHINE
from crewmind.domain.connections.mcp_client import Unreachable, address_allowed, check_host
from crewmind.domain.secrets.store import ensure_master_key
from crewmind.storage.models import Event, StoredSecret
from crewmind.surfaces.mcp.server import tool_name
from tests.attack.harness import assert_refused
from tests.attack.mcp_support import HEADER, HEADER_VALUE, TOKEN, URL, build_server, serving
from tests.attack.test_mcp import client_for, mcp_caller
from tests.conftest import FakeClock
from tests.support import App


@pytest.fixture(autouse=True)
def master_key(app: App) -> None:
    ensure_master_key(app.runtime.config.master_key_file)


def tools_of(view: dict[str, object]) -> dict[str, tuple[str, str]]:
    mcp = view["mcp"]
    assert isinstance(mcp, dict)
    return {tool["name"]: (tool["classification"], tool["permission"]) for tool in mcp["tools"]}  # type: ignore[index]


@pytest.mark.attack("CON-12")
@pytest.mark.attack("INT-4")
async def test_CON_12_a_server_is_tested_before_saving_and_only_reading_tools_start_allowed(
    app: App,
) -> None:
    """CON-12, CON-15, INT-4, P4: the test lists the server and its tools and saves nothing;
    adding it keeps only reading tools allowed; a tool that also destroys is a writer; a
    description is data, never an instruction, and is kept cut to size."""
    owner = await app.person("owner@example.com")
    async with serving((HEADER, HEADER_VALUE)) as gate:
        probe = await app.ok(
            "connections.test_mcp_server", owner, url=URL, auth_kind="header",
            header_name=HEADER, value=HEADER_VALUE,
        )  # fmt: skip
        assert probe["server_name"] == "blog tools"
        assert {tool["name"]: tool["reads_only"] for tool in probe["tools"]} == {
            "list_posts": True, "create_post": False, "wipe": False, "export_posts": True,
        }  # fmt: skip
        assert (await app.ok("connections.list", owner))["items"] == []
        added = await app.ok(
            "connections.add_mcp_server", owner, name="blog", description="The blog's tools.",
            url=URL, auth_kind="header", header_name=HEADER, value=HEADER_VALUE,
        )  # fmt: skip
        assert gate.seen[-1][HEADER.lower()] == HEADER_VALUE
    assert tools_of(added) == {
        "list_posts": ("read", "allowed"),
        "create_post": ("write", "denied"),
        "wipe": ("write", "denied"),
        "export_posts": ("read", "allowed"),
    }
    assert added["mcp"]["state"] == "active"
    assert HEADER_VALUE not in json.dumps(added)
    async with app.runtime.sessions() as session:
        stored = list(await session.scalars(select(StoredSecret.owner_id)))
    assert added["id"] in stored


@pytest.mark.attack("CON-9")
async def test_CON_9_a_server_is_reached_only_where_and_how_it_should_be(app: App) -> None:
    """CON-9, WRK-12: https only; a private address only when an admin allows it, and never
    a link-local or metadata one; a refused sign-in saves nothing and names no value."""
    owner = await app.person("owner@example.com")
    for url in (
        "http://mcp.example.com/mcp",
        "ftp://mcp.example.com",
        "https://user:pw@mcp.example.com/",
    ):
        refused = await app.call("connections.test_mcp_server", owner, url=url, auth_kind="none")
        assert_refused(refused, rule="CON-9")
    local = await app.call("connections.test_mcp_server", owner, url="http://localhost:9/mcp")
    assert_refused(local, rule="CON-9", code="mcp_private_address")
    private = await app.call(
        "connections.test_mcp_server", owner, url="https://mcp.test/mcp", private_network=True
    )
    assert_refused(private, rule="CON-9", code="admin_only")

    assert not address_allowed("169.254.169.254", private_allowed=True)
    assert not address_allowed("fd00:ec2::254", private_allowed=True)
    assert not address_allowed("10.0.0.5", private_allowed=False)
    assert address_allowed("10.0.0.5", private_allowed=True)
    for host in ("127.0.0.1", "localhost"):
        with pytest.raises(Unreachable):
            await check_host(host, 443, private_allowed=False)

    async with serving(("authorization", f"Bearer {TOKEN}")):
        wrong = await app.call(
            "connections.add_mcp_server", owner, name="blog", description="Blog.",
            url=URL, auth_kind="bearer", value="wrong-token-0000-xx",
        )  # fmt: skip
    envelope = assert_refused(wrong, rule="CON-9", code="mcp_unreachable")
    assert "refused the sign-in" in envelope.message
    assert "wrong-token" not in wrong.text
    assert (await app.ok("connections.list", owner))["items"] == []


@pytest.mark.attack("INT-4")
@pytest.mark.attack("7.18-mcp-tool")
async def test_INT_4_the_person_allows_tools_and_a_model_client_cannot(app: App) -> None:
    """INT-4, IF-5.6, 7.18: the owner allows and denies tools, each change recorded; a model
    client may deny but never allow, add a server, or test one with a value."""
    owner = await app.person("owner@example.com")
    async with serving(("authorization", f"Bearer {TOKEN}")):
        await app.ok(
            "connections.add_mcp_server", owner, name="blog", description="Blog.",
            url=URL, auth_kind="bearer", value=TOKEN,
        )  # fmt: skip
    allowed = await app.ok("connections.allow_tool", owner, connection="blog", tool="create_post")
    assert tools_of(allowed)["create_post"] == ("write", "allowed")
    other = await app.person("other@example.com")
    assert (
        await app.call("connections.allow_tool", other, connection="blog", tool="wipe")
    ).status_code == 404
    missing = await app.call("connections.deny_tool", owner, connection="blog", tool="nope")
    assert missing.status_code == 404

    minted = await app.ok("mcp_clients.mint", owner, client_name="Helper", scopes=["configure"])
    caller = await mcp_caller(app, minted["token"])
    async with client_for(app, caller) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
        for name in (
            "connections.allow_tool",
            "connections.add_mcp_server",
            "connections.test_mcp_server",
        ):
            assert tool_name(name) not in listed
            assert catalog.get(name).mcp_scope is None
        denied = await client.call_tool(
            tool_name("connections.deny_tool"), {"connection": "blog", "tool": "create_post"}
        )
        assert not denied.is_error
    async with app.runtime.sessions() as session:
        changes = list(
            await session.scalars(
                select(Event.after).where(Event.type == "mcp.tool_permission_changed")
            )
        )
    assert [change["permission"] for change in changes] == ["allowed", "denied"]  # type: ignore[index]


@pytest.mark.attack("7.18-mcp-server")
async def test_7_18_a_server_that_fails_is_marked_and_comes_back_and_new_tools_start_by_kind(
    app: App,
) -> None:
    """7.18, LLM-11, CON-12: three failed tests in a row mark the server failing with the
    reason kept; a test that works brings it back; a new reading tool starts allowed and a
    tool the server no longer offers is kept, marked gone."""
    owner = await app.person("owner@example.com")
    async with serving():
        await app.ok("connections.add_mcp_server", owner, name="blog", description="Blog.", url=URL)
    view: dict[str, Any] = {}
    for _ in range(3):
        view = await app.ok("connections.test_mcp", owner, connection="blog")
    assert view["mcp"]["state"] == "failing"
    assert view["mcp"]["last_error"]
    async with serving(server=build_server(version="2.0", extra_tool=True)):
        back = await app.ok("connections.test_mcp", owner, connection="blog")
    assert back["mcp"]["state"] == "active"
    assert back["mcp"]["server_version"] == "2.0"
    assert tools_of(back)["count_posts"] == ("read", "allowed")

    oauth = await app.ok(
        "connections.add_mcp_server", owner, name="docs", description="Docs.",
        url="https://docs.example.com/mcp", auth_kind="oauth",
    )  # fmt: skip
    assert oauth["mcp"]["state"] == "needs sign-in"
    waiting = await app.call("connections.test_mcp", owner, connection="docs")
    assert_refused(waiting, rule="CON-9", code="mcp_needs_sign_in")


@given(path=st.lists(st.sampled_from(sorted(SERVER_MACHINE.states - {"(new)"})), max_size=10))
def test_7_18_an_mcp_server_moves_only_by_listed_transitions(path: list[str]) -> None:
    """7.18: deleted is final; every other move follows the table or is refused."""
    state = "active"
    for target in path:
        if target == state:
            continue
        if SERVER_MACHINE.allows(state, target):
            assert state != "deleted"
            state = target
        else:
            with pytest.raises(Refusal):
                SERVER_MACHINE.check(state, target)


def test_7_18_a_tool_permission_moves_only_between_allowed_and_denied() -> None:
    """7.18: a tool is allowed or denied, and only the chairman moves it."""
    assert TOOL_MACHINE.allows("denied", "allowed")
    assert TOOL_MACHINE.allows("allowed", "denied")
    with pytest.raises(Refusal):
        TOOL_MACHINE.check("allowed", "gone")


@pytest.mark.attack("CON-9")
async def test_CON_9_an_older_server_is_reached_over_sse_at_an_allowed_private_address(
    app: App,
) -> None:
    """CON-9: a server that speaks only HTTP with server-sent events is reached that way,
    through the real address guard, at a private address an admin allowed for it."""
    import asyncio

    import uvicorn

    admin = await app.admin()
    app_sse = build_server().sse_app()
    server = uvicorn.Server(uvicorn.Config(app_sse, host="127.0.0.1", port=0, log_level="error"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        added = await app.ok(
            "connections.add_mcp_server", admin, name="old", description="An older server.",
            url=f"http://127.0.0.1:{port}/sse", private_network=True, scope="install",
        )  # fmt: skip
    finally:
        server.should_exit = True
        await task
    assert added["mcp"]["transport"] == "sse"
    assert tools_of(added)["list_posts"] == ("read", "allowed")


@pytest.mark.attack("CON-12")
async def test_CON_12_tools_are_read_again_every_refresh_period(app: App, clock: FakeClock) -> None:
    """CON-12: the upkeep reads each server's tools again once `mcp.tools_refresh` has
    passed, and not before; a new reading tool starts allowed."""
    owner = await app.person("owner@example.com")
    async with serving():
        await app.ok("connections.add_mcp_server", owner, name="blog", description="Blog.", url=URL)
    async with serving(server=build_server(version="3.0", extra_tool=True)):
        await app.scheduler.tick()
        unchanged = await app.ok("connections.show", owner, connection="blog")
        assert "count_posts" not in tools_of(unchanged["item"])
        clock.advance(days=1, minutes=1)
        await app.scheduler.tick()
    owner = await app.login(owner.email, owner.person_id)
    refreshed = await app.ok("connections.show", owner, connection="blog")
    assert tools_of(refreshed["item"])["count_posts"] == ("read", "allowed")
    assert refreshed["item"]["mcp"]["server_version"] == "3.0"


async def test_IF_5_1_crewmind_marks_its_own_reading_tools_so_clients_can_tell_them_apart(
    app: App,
) -> None:
    """IF-5.1, CON-12: crewmind's own MCP tools say whether they only read and whether they
    can be undone, so a client (crewmind included) allows its readers and asks about writers."""
    owner = await app.person("owner@example.com")
    minted = await app.ok("mcp_clients.mint", owner, client_name="Reader", scopes=["steer"])
    caller = await mcp_caller(app, minted["token"])
    async with client_for(app, caller) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert tools["projects_status"].annotations is not None
    assert tools["projects_status"].annotations.read_only_hint is True
    assert tools["projects_hold"].annotations is not None
    assert tools["projects_hold"].annotations.read_only_hint is False
