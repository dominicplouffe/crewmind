"""The phase 7.B exit demo, end to end through the public operations (docs/phases/
phase-7b-plan.md): the Founder names what the squad needs; start says what is missing; the
chairman adds a secret sent for the agent, a variable and one MCP server of each kind; the
writer posts with plain curl and never holds the password; tools are used and asked for;
no value is anywhere; a replaced password is used at once; a revoked sign-in raises one
alarm. Every external service is a local stand-in."""

from __future__ import annotations

import base64
import logging
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from nightsquad.domain.connections.agent_operations import EGRESS
from nightsquad.domain.connections.mcp_sign_in import CALLBACK_PATH
from nightsquad.domain.secrets.store import ensure_master_key
from nightsquad.gateway.protocol import CompletionRequest
from nightsquad.runner.egress.proxy import EgressProxy
from nightsquad.runner.egress.service import build_proxy
from nightsquad.storage.models import Alarm
from nightsquad.surfaces.api.app import SESSION_COOKIE
from tests.attack import mcp_support
from tests.attack.egress_support import Site, trusting
from tests.attack.harness import assert_refused
from tests.attack.mcp_support import URL, serving
from tests.attack.oauth_support import Authority, oauth_serving
from tests.attack.test_connections import seats
from tests.attack.test_mcp_calls import mcp_call
from tests.conftest import FakeClock
from tests.founder_support import BRIEF, SPEC, credential, propose, script
from tests.leaks import scan
from tests.support import Actor, App, agent_call, live_run, quiet_start, wake

pytestmark = pytest.mark.usefixtures("quick_rehearsal")

PASSWORD = "wp-demo-password-6620-unguessable"
REPLACED = "wp-demo-replaced-3391-unguessable"
BEARER = mcp_support.TOKEN
HEADER = "mcp-header-value-7734-unguessable"
NOTES = "notes-token-demo-1188-unguessable"
STDIO = Path(__file__).parents[1] / "attack" / "mcp_stdio_server.py"
WRITER_ROLE = "blog-writer"


@pytest.fixture
async def site() -> AsyncIterator[Site]:
    running = Site()
    await running.start()
    yield running
    await running.stop()


@pytest.fixture
async def proxy(app: App, site: Site) -> AsyncIterator[int]:
    ensure_master_key(app.runtime.config.master_key_file)
    built: EgressProxy = await build_proxy(
        app.runtime.sessions, app.runtime.settings, app.runtime.config.master_key_file,
        app.runtime.clock, upstream_tls=trusting(site.authority), connect=site.connect,
    )  # fmt: skip
    port = await built.start("127.0.0.1", 0)
    app.runtime.services.wired[EGRESS] = f"http://127.0.0.1:{port}"
    yield port
    await built.stop()


async def come_back(app: App, actor: Actor, address: str, authority: Authority) -> None:
    """The person agrees at the provider and the browser returns to Nightsquad."""
    query = {key: values[0] for key, values in parse_qs(urlsplit(address).query).items()}
    code = authority.code_for(query)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app.api), base_url=app.runtime.config.base_url,
        cookies={SESSION_COOKIE: actor.token},
    ) as browser:  # fmt: skip
        answer = await browser.get(CALLBACK_PATH, params={"code": code, "state": query["state"]})
    assert answer.status_code in (200, 302, 303), answer.text


def basic(password: str) -> str:
    return "Basic " + base64.b64encode(f"dom:{password}".encode()).decode()


async def writer_posts(app: App, project: str, writer: str, site: Site) -> dict[str, str]:
    """The writer's own command posts a draft; returns the headers the site received."""
    command = "curl -s -X POST https://wp.test/wp-json/wp/v2/posts -d status=draft; echo"
    app.script(
        writer, {"tools": [{"name": "shell", "arguments": {"command": command}}]}, {"text": "done"}
    )
    await wake(app, project, seat=writer)
    await app.work()
    posted = [seen for seen in site.received if seen["target"] == "/wp-json/wp/v2/posts"]
    assert posted, "the post never reached the site"
    return posted[-1]["headers"]


async def test_phase_7b_exit_demo(
    app: App,
    site: Site,
    proxy: int,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CON-1 to CON-16, FND-9, FND-13, PRJ-1, EXE-13, EXE-14, INT-4, INV-6, INV-21: the
    exit demo, steps 1 to 6."""
    caplog.set_level(logging.DEBUG, logger="nightsquad")
    sent: list[CompletionRequest] = []
    complete = app.runtime.mock.complete

    async def recording(request: CompletionRequest, **kwargs: Any) -> Any:
        sent.append(request)
        return await complete(request, **kwargs)

    monkeypatch.setattr(app.runtime.mock, "complete", recording)
    owner = await app.person("owner@example.com")
    await credential(app, owner, "main")
    mcp_support.created.clear()

    # 1. The Founder drafts the squad and names what it needs; nothing is had yet.
    teams = [*SPEC["teams"], {"name": "Desk", "role": WRITER_ROLE, "members": ["Wren"]}]
    grants = [
        {"name": "wordpress", "roles": [WRITER_ROLE]},
        {"name": "wordpress-site", "kind": "variable", "roles": [WRITER_ROLE]},
    ]
    script(
        app,
        propose(spec={"teams": teams, "credentials": grants}),
        {"text": "The blog writer needs the WordPress password and the site's address."},
    )
    started = await app.ok("founder.start", owner, brief=BRIEF)
    await app.founder.tick()
    drafted = await app.ok("founder.show", owner, drafting_id=started["drafting_id"])
    assert {(need["name"], need["have"]) for need in drafted["needs"]} == {
        ("wordpress", False),
        ("wordpress-site", False),
    }

    # 2. Create works; start says what is missing and which agents would wait.
    created = await app.ok(
        "projects.import_spec", owner, **{**drafted["draft"], "paying_credential": "main"}
    )
    project = created["project_id"]
    assert any("wordpress" in line for line in created["waiting"])
    refused = await app.call("projects.start", owner, project_id=project)
    assert_refused(refused, rule="CON-5")
    assert "wordpress" in refused.text

    # 3. The chairman adds what is missing, and one MCP server of each kind.
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=PASSWORD, sites=["wp.test"], header_kind="basic", basic_user="dom",
        project_id=project,
    )  # fmt: skip
    await app.ok(
        "connections.add_variable", owner, name="wordpress-site", description="The blog.",
        value="https://wp.test", project_id=project,
    )  # fmt: skip
    servers: dict[str, dict[str, Any]] = {}
    remote: list[tuple[str, dict[str, Any], tuple[str, str] | None]] = [
        ("docs-open", {}, None),
        ("docs-token", {"auth_kind": "bearer", "value": BEARER},
         ("authorization", f"Bearer {BEARER}")),
        ("docs-header", {"auth_kind": "header", "header_name": "X-Api-Key", "value": HEADER},
         ("x-api-key", HEADER)),
    ]  # fmt: skip
    for name, auth, wanted in remote:
        async with serving(wanted):
            servers[name] = await app.ok(
                "connections.add_mcp_server", owner, name=name, description="Docs tools.",
                url=URL, project_id=project, roles=["*"], **auth,
            )  # fmt: skip
    authority = Authority(access_life=30)
    async with oauth_serving(authority):
        servers["docs-oauth"] = await app.ok(
            "connections.add_mcp_server", owner, name="docs-oauth", description="Docs tools.",
            url=URL, auth_kind="oauth", project_id=project, roles=["*"],
        )  # fmt: skip
        begun = await app.ok("connections.sign_in", owner, connection="docs-oauth")
        await come_back(app, owner, str(begun["authorize_url"]), authority)
    await app.ok(
        "connections.add_secret", owner, name="notes-token", description="Notes token.",
        value=NOTES, delivery="given", env_name="NOTES_TOKEN",
    )  # fmt: skip
    servers["notes"] = await app.ok(
        "connections.add_command_mcp_server", owner, name="notes", description="Notes tools.",
        command=f"{sys.executable} {STDIO}", environment={"BLOG_TOKEN": "notes-token"},
        project_id=project, roles=["*"],
    )  # fmt: skip
    for name in ("docs-open", "docs-token", "docs-header"):
        tools = {tool["name"]: tool["permission"] for tool in servers[name]["mcp"]["tools"]}
        assert tools["list_posts"] == "allowed"
        assert tools["create_post"] == "denied"
    shown = await app.ok("connections.show", owner, connection="docs-oauth")
    assert shown["item"]["mcp"]["state"] == "active"

    # 4. The project starts; the writer posts through Nightsquad without holding the password.
    await app.ok("projects.start", owner, project_id=project)
    await quiet_start(app, project)
    writer = next(name for name in await seats(app, project) if name == "Wren")
    headers = await writer_posts(app, project, writer, site)
    assert headers["authorization"] == basic(PASSWORD)
    run = await live_run(app, project)
    async with serving() as gate:
        server = servers["docs-open"]["id"]
        listed = await mcp_call(app, run.token, server, "list_posts")
        assert listed.status_code == 200, listed.text
        before = len(gate.seen)
        denied = await mcp_call(app, run.token, server, "create_post", title="Hello")
        assert_refused(denied, rule="INT-4", code="mcp_tool_denied")
        assert len(gate.seen) == before
    asked = await agent_call(
        app, run.token, "agent.request_access", server="docs-open", tool="create_post",
        why="To publish the first post the plan asks for.",
    )  # fmt: skip
    assert asked.status_code == 200, asked.text
    desk = await app.ok("items.list", owner, project_id=project)
    assert any(item["id"] == asked.json()["item_id"] for item in desk["items"])

    # 6. A replaced password is used by the very next request.
    await app.ok("connections.replace_secret", owner, connection="wordpress", value=REPLACED)
    headers = await writer_posts(app, project, writer, site)
    assert headers["authorization"] == basic(REPLACED)

    # 6. A revoked sign-in asks for sign-in again, with one alarm.
    async with oauth_serving(authority):
        authority.refused_refresh = True
        clock.advance(minutes=1)
        owner = await app.login(owner.email, owner.person_id)
        for _ in range(2):
            await app.call("connections.test_mcp", owner, connection="docs-oauth")
    async with app.runtime.sessions() as session:
        alarms = list(await session.scalars(select(Alarm.body)))
    assert len([body for body in alarms if "sign in again" in body]) == 1

    # 5. No value is anywhere Nightsquad keeps or says anything.
    values = {
        "password": PASSWORD, "replaced": REPLACED, "basic": f"dom:{PASSWORD}",
        "basic-replaced": f"dom:{REPLACED}", "bearer": BEARER, "header": HEADER, "notes": NOTES,
        **{f"oauth-access-{n}": token for n, token in enumerate(authority.access)},
        **{f"oauth-refresh-{n}": token for n, token in enumerate(authority.refresh)},
    }  # fmt: skip
    exported = await app.ok("projects.export", owner, project_id=project)
    cloned = await app.ok("projects.clone", owner, project_id=project, name="Blog two")
    said = {
        "model requests": [request.model_dump(mode="json") for request in sent],
        "log lines": [record.getMessage() for record in caplog.records],
        "export": exported,
        "clone": cloned,
        "connections": await app.ok("connections.list", owner, project_id=project),
        "project connections": await app.ok("connections.for_project", owner, project_id=project),
        "record": await app.ok("record.list", owner, project_id=project, limit=200),
    }
    assert await scan(app, values, said) == []
    await app.runtime.commands.close()
