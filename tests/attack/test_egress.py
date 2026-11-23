"""Attacks on the egress proxy: a secret sent for the agent reaches only its own site, for
its own runs; everything else is relayed untouched or refused with a reason (CON-6,
CON-16, EXE-14, WRK-12)."""

from __future__ import annotations

import asyncio
import base64
import json
import ssl
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select

from crewmind.domain.connections.agent_operations import EGRESS
from crewmind.domain.secrets.store import ensure_master_key
from crewmind.runner.egress.proxy import EgressProxy, Refused, guarded_connect
from crewmind.runner.egress.service import build_proxy, load_authority
from crewmind.storage.models import RunStep
from tests.attack.egress_support import Site, trusting
from tests.attack.test_connections import blog_project, seats
from tests.support import App, agent_call, live_run, quiet_start, wake

WP = "wp-sent-password-4471-unguessable"


@pytest.fixture
async def site() -> AsyncIterator[Site]:
    running = Site()
    await running.start()
    yield running
    await running.stop()


@pytest.fixture
async def proxy(app: App, site: Site) -> AsyncIterator[tuple[EgressProxy, int]]:
    ensure_master_key(app.runtime.config.master_key_file)
    built = await build_proxy(
        app.runtime.sessions, app.runtime.settings, app.runtime.config.master_key_file,
        app.runtime.clock, upstream_tls=trusting(site.authority), connect=site.connect,
    )  # fmt: skip
    port = await built.start("127.0.0.1", 0)
    yield built, port
    await built.stop()


async def sending_setup(app: App) -> tuple[str, str]:
    """A started blog project whose writer has the WordPress password sent for it to
    wp.test, with basic sign-in. Returns the project and the writer's seat name."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=WP, sites=["wp.test"], header_kind="basic", basic_user="dom", project_id=project,
    )  # fmt: skip
    await app.ok("projects.start", owner, project_id=project)
    await quiet_start(app, project)
    found = await seats(app, project)
    return project, next(n for n, s in found.items() if n != "CEO" and s.kind != "reviewer")


async def sending_project(app: App) -> tuple[str, str, str]:
    """The same, with a live run of the writer and of the CEO: the project, their tokens."""
    project, writer = await sending_setup(app)
    return (
        project,
        (await live_run(app, project, seat=writer)).token,
        (await live_run(app, project)).token,
    )


async def trusted_by_runs(app: App) -> ssl.SSLContext:
    authority = await load_authority(
        app.runtime.sessions, app.runtime.config.master_key_file, app.runtime.clock()
    )
    return trusting(authority)


def through(port: int, token: str, verify: ssl.SSLContext) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        proxy=f"http://run:{token}@127.0.0.1:{port}", verify=verify, trust_env=False
    )


@pytest.mark.attack("CON-6")
async def test_CON_6_a_granted_site_gets_the_secret_and_nothing_else_does(
    app: App, site: Site, proxy: tuple[EgressProxy, int]
) -> None:
    """CON-6, CON-16: requests to the granted site carry the secret as the header the
    agent's own value is replaced by, over kept-alive connections and chunked bodies. A
    site without a secret is an opaque tunnel with its own certificate. The trace names
    each sending without the value or the query."""
    _, port = proxy
    _, writer, _ = await sending_project(app)
    expected = "Basic " + base64.b64encode(f"dom:{WP}".encode()).decode()
    runs_trust = await trusted_by_runs(app)
    async with through(port, writer, runs_trust) as client:
        first = await client.get(
            "https://wp.test/wp-json/wp/v2/posts?search=secret",
            headers={"Authorization": "Bearer mine"},
        )
        assert first.status_code == 200
        seen = first.json()
        assert seen["headers"]["authorization"] == expected
        assert "proxy-authorization" not in seen["headers"]

        async def chunks() -> AsyncIterator[bytes]:
            for _ in range(3):
                yield b"x" * 1000

        second = await client.post("https://wp.test/wp-json/wp/v2/posts", content=chunks())
        assert second.json()["body"] == 3000
        assert second.json()["headers"]["authorization"] == expected

    async with through(port, writer, trusting(site.authority)) as tunnel:
        other = (await tunnel.get("https://other.test/hello")).json()
    assert "authorization" not in other["headers"]

    async with app.runtime.sessions() as session:
        steps = list(await session.scalars(select(RunStep).where(RunStep.kind == "secret sent")))
    assert [
        (s.data["site"], s.data["secret"], s.data["method"], s.data["path"], s.data["status"])
        for s in steps
    ] == [
        ("wp.test", "wordpress", "GET", "/wp-json/wp/v2/posts", 200),
        ("wp.test", "wordpress", "POST", "/wp-json/wp/v2/posts", 200),
    ]
    assert WP not in json.dumps([step.data for step in steps])
    assert base64.b64encode(f"dom:{WP}".encode()).decode() not in json.dumps(
        [s.data for s in steps]
    )


@pytest.mark.attack("CON-6")
async def test_CON_6_strangers_mismatches_and_plain_http_never_get_the_secret(
    app: App, site: Site, proxy: tuple[EgressProxy, int]
) -> None:
    """CON-6: a credential that is not a live run's is refused; a run whose role is not
    granted is tunnelled; a request inside the site's tunnel naming another host, a TLS
    server name for another host, and an upgrade are refused; plain HTTP to the site is
    relayed without the secret."""
    _, port = proxy
    _, writer, ceo = await sending_project(app)
    runs_trust = await trusted_by_runs(app)

    async with through(port, "not-a-run-token", runs_trust) as stranger:
        with pytest.raises(httpx.ProxyError):
            await stranger.get("https://wp.test/")
    async with through(port, ceo, trusting(site.authority)) as other_role:
        assert "authorization" not in (await other_role.get("https://wp.test/")).json()["headers"]

    async with through(port, writer, runs_trust) as client:
        misdirected = await client.get("https://wp.test/", headers={"Host": "other.test"})
        assert misdirected.status_code == 421
    async with through(port, writer, runs_trust) as client:
        upgrade = await client.get(
            "https://wp.test/", headers={"Upgrade": "websocket", "Connection": "Upgrade"}
        )
        assert upgrade.status_code == 501

    reader, stream = await asyncio.open_connection("127.0.0.1", port)
    credential = base64.b64encode(f"run:{writer}".encode()).decode()
    stream.write(
        b"CONNECT wp.test:443 HTTP/1.1\r\nHost: wp.test:443\r\n"
        + f"Proxy-Authorization: Basic {credential}\r\n\r\n".encode()
    )
    await stream.drain()
    assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
    with pytest.raises((ssl.SSLError, ConnectionError)):
        await stream.start_tls(runs_trust, server_hostname="other.test")
    stream.close()

    async with through(port, writer, runs_trust) as client:
        plain = (await client.get("http://wp.test/plain")).json()
    assert "authorization" not in plain["headers"]
    assert WP not in json.dumps(site.received)


@pytest.mark.attack("WRK-12")
@pytest.mark.attack("CON-6")
async def test_EXE_14_the_proxy_never_leads_into_the_host_or_its_network(app: App) -> None:
    """EXE-14, WRK-12: the proxy runs beside the control plane, so it connects only to
    public addresses, and says so in plain words."""
    for host in ("127.0.0.1", "localhost", "10.0.0.8", "169.254.169.254", "::1"):
        with pytest.raises(Refused):
            await guarded_connect(host, 443)
    ensure_master_key(app.runtime.config.master_key_file)
    built = await build_proxy(
        app.runtime.sessions,
        app.runtime.settings,
        app.runtime.config.master_key_file,
        app.runtime.clock,
    )
    port = await built.start("127.0.0.1", 0)
    try:
        _, writer, _ = await sending_project(app)
        async with through(port, writer, ssl.create_default_context()) as client:
            with pytest.raises(httpx.ProxyError) as refused:
                await client.get("https://127.0.0.1:9/")
        assert "403" in str(refused.value)
        async with app.runtime.sessions() as session:
            reasons = list(
                await session.scalars(select(RunStep.data).where(RunStep.kind == "egress refused"))
            )
        assert "not a public address" in reasons[-1]["reason"]
    finally:
        await built.stop()


@pytest.mark.attack("CON-6")
async def test_CON_6_the_writer_posts_with_curl_and_never_holds_the_password(
    app: App, site: Site, proxy: tuple[EgressProxy, int]
) -> None:
    """CON-6, CON-7, the 7B.3 demo: the blog writer's own command posts to the site through
    the proxy; the site receives the password, and nothing in the writer's sandbox, its
    model's conversation or the platform's records holds it. A role with nothing sent for
    it is not sent through the proxy at all."""
    _, port = proxy
    app.runtime.services.wired[EGRESS] = f"http://127.0.0.1:{port}"
    project, writer = await sending_setup(app)
    command = (
        "curl -s -X POST https://wp.test/wp-json/wp/v2/posts -d title=Hello; "
        'echo; env | grep -c "wp-sent" || true'
    )
    app.script(
        writer, {"tools": [{"name": "shell", "arguments": {"command": command}}]}, {"text": "done"}
    )
    await wake(app, project, seat=writer)
    await app.work()

    expected = "Basic " + base64.b64encode(f"dom:{WP}".encode()).decode()
    posted = [seen for seen in site.received if seen["target"] == "/wp-json/wp/v2/posts"]
    assert posted
    assert posted[-1]["headers"]["authorization"] == expected
    async with app.runtime.sessions() as session:
        steps = [step.data for step in await session.scalars(select(RunStep))]
    said = json.dumps(steps)
    assert WP not in said
    assert '"secret sent"' in said or any(step.get("secret") == "wordpress" for step in steps)
    ceo = (await live_run(app, project)).token
    ceo_environment = (await agent_call(app, ceo, "agent.environment")).json()
    assert ceo_environment["proxy"] is None
