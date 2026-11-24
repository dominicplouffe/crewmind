"""Attacks on MCP OAuth sign-in: PKCE, the resource indicator, a single-use state bound to
the browser session, refresh with rotation, and a refused refresh (CON-10, CON-14)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from nightsquad.domain.connections.mcp_sign_in import CALLBACK_PATH
from nightsquad.domain.secrets.store import ensure_master_key
from nightsquad.storage.models import Alarm, Event
from nightsquad.surfaces.api.app import SESSION_COOKIE
from tests.attack.harness import assert_refused
from tests.attack.oauth_support import Authority, oauth_serving
from tests.conftest import FakeClock
from tests.support import Actor, App

URL = "https://mcp.test/mcp"


@pytest.fixture(autouse=True)
def master_key(app: App) -> None:
    ensure_master_key(app.runtime.config.master_key_file)


async def come_back(app: App, actor: Actor, code: str, state: str) -> httpx.Response:
    """The browser arriving at nightsquad's callback, carrying its session cookie."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app.api), base_url=app.runtime.config.base_url,
        cookies={SESSION_COOKIE: actor.token},
    ) as browser:  # fmt: skip
        return await browser.get(CALLBACK_PATH, params={"code": code, "state": state})


async def start(app: App, owner: Actor, authority: Authority) -> tuple[dict[str, str], str]:
    started = await app.ok("connections.sign_in", owner, connection="docs")
    address = str(started["authorize_url"])
    query = {key: values[0] for key, values in parse_qs(urlsplit(address).query).items()}
    return query, authority.code_for(query)


@pytest.mark.attack("CON-10")
async def test_CON_10_sign_in_uses_pkce_and_the_resource_and_finishes_once_in_the_same_browser(
    app: App, clock: FakeClock
) -> None:
    """CON-10: discovery, dynamic registration, PKCE S256 and the resource indicator; the
    state works once, only for the person and browser session that started it, and only
    for ten minutes; the tokens are never shown; signing in reads the tools."""
    owner = await app.person("owner@example.com")
    other = await app.person("other@example.com")
    authority = Authority()
    async with oauth_serving(authority):
        await app.ok(
            "connections.add_mcp_server", owner, name="docs", description="Docs.", url=URL,
            auth_kind="oauth",
        )  # fmt: skip
        query, code = await start(app, owner, authority)
        assert query["code_challenge_method"] == "S256"
        assert query["resource"] == URL
        assert query["client_id"] == "client-1"
        assert query["redirect_uri"].endswith(CALLBACK_PATH)
        assert authority.registered[0]["token_endpoint_auth_method"] == "none"

        stolen = await come_back(app, other, code, query["state"])
        assert "sign_in_error" in stolen.headers["location"]
        query, code = await start(app, owner, authority)
        done = await come_back(app, owner, code, query["state"])
        assert done.status_code == 303
        assert done.headers["location"] == "/settings/connections?signed_in=docs"
        again = await come_back(app, owner, code, query["state"])
        assert "sign_in_error" in again.headers["location"]

        query, code = await start(app, owner, authority)
        clock.advance(minutes=11)
        owner = await app.login(owner.email, owner.person_id)
        late = await come_back(app, owner, code, query["state"])
        assert (
            "ten+minutes" in late.headers["location"] or "ten%20minutes" in late.headers["location"]
        )

    shown = await app.ok("connections.show", owner, connection="docs")
    assert shown["item"]["mcp"]["state"] == "active"
    assert {tool["name"] for tool in shown["item"]["mcp"]["tools"]} >= {"list_posts"}
    said = json.dumps(shown)
    assert not any(token in said for token in authority.access | authority.refresh)
    async with app.runtime.sessions() as session:
        events = list(await session.scalars(select(Event)))
        recorded = json.dumps([e.after for e in events], default=str)
    kinds = [event.type for event in events]
    assert "mcp.sign_in_started" in kinds
    assert "mcp.signed_in" in kinds
    assert not any(token in recorded for token in authority.access | authority.refresh)


@pytest.mark.attack("CON-10")
async def test_CON_10_tokens_are_refreshed_and_rotated_and_a_refused_refresh_asks_to_sign_in(
    app: App, clock: FakeClock
) -> None:
    """CON-10, CON-14: a token about to expire is refreshed and the rotated refresh token
    kept; when the provider refuses the refresh, the server needs sign-in again and each
    project that uses it gets one alarm."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    authority = Authority(access_life=30)
    async with oauth_serving(authority):
        await app.ok(
            "connections.add_mcp_server", owner, name="docs", description="Docs.", url=URL,
            auth_kind="oauth", project_id=project, roles=["*"],
        )  # fmt: skip
        query, code = await start(app, owner, authority)
        await come_back(app, owner, code, query["state"])
        for _ in range(2):
            clock.advance(minutes=1)
            owner = await app.login(owner.email, owner.person_id)
            tested = await app.ok("connections.test_mcp", owner, connection="docs")
            assert tested["mcp"]["state"] == "active"
        assert authority.grants.count("refresh_token") == 2

        authority.refused_refresh = True
        clock.advance(minutes=1)
        owner = await app.login(owner.email, owner.person_id)
        needs = await app.ok("connections.test_mcp", owner, connection="docs")
        assert needs["mcp"]["state"] == "needs sign-in"
        retest = await app.call("connections.test_mcp", owner, connection="docs")
        assert_refused(retest, rule="CON-9", code="mcp_needs_sign_in")
    async with app.runtime.sessions() as session:
        alarms = list(await session.scalars(select(Alarm.body)))
    assert len([body for body in alarms if "sign in again" in body]) == 1
