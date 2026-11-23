"""What `crewmind doctor` says about connections: a server that needs sign-in or fails, a
started project waiting for a connection, and an egress proxy that does not run while a
secret is sent for agents, each with its fix (CON-16, CON-6, CON-10, CON-5, NFR-5)."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import select

from crewmind.domain.connections.doctor import PROXY_FILE, record_proxy
from crewmind.domain.secrets.store import ensure_master_key
from crewmind.storage.models import McpServer
from tests.attack import mcp_support
from tests.attack.mcp_support import URL, serving
from tests.attack.test_connections import blog_project
from tests.attack.test_install import environment
from tests.support import App
from tests.unit.test_install import a_server_is_running

VALUE = "wp-app-password-0451-unguessable"


async def findings(app: App) -> dict[str, tuple[bool, str, str | None]]:
    report = await app.host("install.doctor")
    return {item.check: (item.ok, item.detail, item.fix) for item in report.findings}


async def test_CON_16_doctor_names_servers_waiting_needs_and_a_proxy_that_does_not_answer(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CON-16, CON-10, CON-5, CON-6, NFR-5: every connection problem the doctor finds names
    what is wrong and how to fix it; with nothing wrong each check passes."""
    environment(app.runtime, monkeypatch)
    ensure_master_key(app.runtime.config.master_key_file)
    mcp_support.created.clear()
    before = await findings(app)
    assert before["MCP servers"][0]
    assert before["connection needs"][0]
    assert before["egress proxy"][0]

    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    await app.ok("projects.start", owner, project_id=project, without_missing=True)
    async with serving():
        await app.ok(
            "connections.add_mcp_server", owner, name="blog", description="The blog's tools.",
            url=URL,
        )  # fmt: skip
    async with app.runtime.sessions() as session, session.begin():
        server = await session.scalar(select(McpServer))
        assert server is not None
        server.state = "needs sign-in"
    found = await findings(app)
    ok, detail, fix = found["MCP servers"]
    assert not ok
    assert "Waiting for sign-in: blog." in detail
    assert fix
    assert "sign in again" in fix
    ok, detail, fix = found["connection needs"]
    assert not ok
    assert "(1)" in detail
    assert fix

    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=VALUE, sites=["example.com"], project_id=project,
    )  # fmt: skip
    a_server_is_running(app.runtime.config.data_dir)
    record_proxy(app.runtime.config.data_dir, None, "OSError")
    ok, detail, fix = (await findings(app))["egress proxy"]
    assert not ok
    assert "OSError" in detail
    assert fix
    assert "crewmind up" in fix

    listening = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = listening.sockets[0].getsockname()[1]
    try:
        record_proxy(app.runtime.config.data_dir, port, None)
        assert (await findings(app))["egress proxy"][0]
    finally:
        listening.close()
        await listening.wait_closed()
    assert json.loads((app.runtime.config.data_dir / PROXY_FILE).read_text())["port"] == port
    assert VALUE not in json.dumps(await findings(app))
