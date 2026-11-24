"""Attacks on OAuth for MCP clients (IF-5.1, NFR-13): PKCE stripping, code replay,
redirect swap, audience confusion, scope widening and refresh-token replay."""

from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

from nightsquad.storage.models import OAuthClient
from tests.attack.harness import assert_refused
from tests.attack.test_mcp import client_for
from tests.conftest import FakeClock
from tests.support import Actor, App

REDIRECT = "http://localhost:7777/callback"
VERIFIER = "a-long-random-verifier-that-only-the-client-knows-0123456789"
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
)


def audience(app: App) -> str:
    return app.runtime.config.base_url.rstrip("/") + "/mcp"


async def registered(app: App, **more: Any) -> str:
    made = await app.ok(
        "oauth.register", client_name="Desk assistant", redirect_uris=[REDIRECT], **more
    )
    return made["client_id"]


def request(app: App, client_id: str, **changed: Any) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "scopes": ["read", "steer"],
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "resource": audience(app),
        "state": "xyz",
    } | changed


async def code_for(app: App, owner: Actor, client_id: str, **changed: Any) -> str:
    approved = await app.ok("oauth.approve", owner, **request(app, client_id, **changed))
    query: dict[str, list[str]] = parse_qs(urlsplit(str(approved["redirect_to"])).query)
    assert query["state"] == ["xyz"]
    return query["code"][0]


def exchange(client_id: str, code: str, **changed: Any) -> dict[str, Any]:
    return {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
    } | changed


@pytest.mark.attack("IF-5.1")
async def test_IF_5_1_the_five_named_attacks_fail(app: App) -> None:
    """IF-5.1: PKCE stripping, redirect swap, audience confusion and scope widening are
    refused at approval and at the token endpoint, and a code tried with wrong values is
    spent. Nobody approves a client without a signed-in person."""
    owner = await app.person("owner@example.com")
    client_id = await registered(app)
    assert (await app.call("oauth.approve", **request(app, client_id))).status_code == 401
    for changed, code in (
        ({"code_challenge_method": "plain"}, "pkce_required"),
        ({"code_challenge": ""}, "pkce_required"),
        ({"redirect_uri": "http://localhost:7777/other"}, "redirect_mismatch"),
        ({"redirect_uri": "https://evil.example/callback"}, "redirect_mismatch"),
        ({"resource": "https://another-server.example/mcp"}, "wrong_audience"),
        ({"scopes": ["read", "admin"]}, "unknown_scope"),
        ({"client_id": "0" * 32}, "unknown_client"),
    ):
        refused = await app.call("oauth.approve", owner, **request(app, client_id) | changed)
        assert refused.status_code == 403, changed
        assert refused.json()["code"] == code, changed

    for changed, code in (
        ({"code_verifier": "not-the-verifier"}, "pkce_failed"),
        ({"code_verifier": None}, "pkce_failed"),
        ({"redirect_uri": "http://localhost:7777/other"}, "redirect_mismatch"),
        ({"resource": "https://another-server.example/mcp"}, "wrong_audience"),
    ):
        fresh = await code_for(app, owner, client_id)
        refused = await app.call("oauth.token", **exchange(client_id, fresh) | changed)
        assert_refused(refused, rule=refused.json()["rule"], code=code)
        again = await app.call("oauth.token", **exchange(client_id, fresh))
        assert again.json()["code"] == "code_replayed", changed

    code = await code_for(app, owner, client_id)
    wider = await app.call("oauth.token", **exchange(client_id, code, scope="read configure"))
    assert_refused(wider, rule="IF-5.1", code="scope_widened")
    other = await registered(app)
    code = await code_for(app, owner, client_id)
    stolen = await app.call("oauth.token", **exchange(other, code))
    assert_refused(stolen, rule="IF-5.1", code="invalid_code")


@pytest.mark.attack("NFR-13")
async def test_NFR_13_codes_are_single_use_and_a_replayed_refresh_is_theft(
    app: App, clock: FakeClock
) -> None:
    """NFR-13, IF-5.1, IF-5.4: a code works once and for 60 seconds. The access token
    lasts an hour, works only at this server's MCP endpoint, and is recorded as the
    person acting through the client. A refresh token rotates on use; using an old one
    again revokes every token of the grant. Using a code twice does the same."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    client_id = await registered(app)

    late = await code_for(app, owner, client_id)
    clock.advance(seconds=61)
    expired = await app.call("oauth.token", **exchange(client_id, late))
    assert_refused(expired, rule="NFR-13", code="code_expired")

    code = await code_for(app, owner, client_id)
    first = await app.ok("oauth.token", **exchange(client_id, code))
    assert (first["token_type"], first["expires_in"], first["scope"]) == (
        "Bearer",
        3600,
        "read steer",
    )
    authenticate = app.runtime.authenticator.authenticate
    caller = await authenticate(first["access_token"], on_mcp=True, audience=audience(app))
    assert (caller.via, caller.mcp_scopes) == ("mcp:Desk assistant", {"read", "steer"})
    with pytest.raises(Exception, match="Sign in"):
        await authenticate(first["access_token"], on_mcp=True, audience="https://other/mcp")
    async with client_for(app, caller) as client:
        started = await client.call_tool("projects_start", {"project_id": project})
        assert (started.structured_content or {})["state"] == "running"
    change = [e for e in await app.events(owner, project) if e["type"] == "project.state_changed"]
    assert change[-1]["via"] == "mcp:Desk assistant"

    renew = {"grant_type": "refresh_token", "client_id": client_id}
    second = await app.ok("oauth.token", **renew, refresh_token=first["refresh_token"])
    assert second["access_token"] != first["access_token"]
    await authenticate(second["access_token"], on_mcp=True, audience=audience(app))
    replay = await app.call("oauth.token", **renew, refresh_token=first["refresh_token"])
    assert_refused(replay, rule="NFR-13", code="refresh_replayed")
    for token in (first["access_token"], second["access_token"]):
        with pytest.raises(Exception, match="Sign in"):
            await authenticate(token, on_mcp=True, audience=audience(app))
    dead = await app.call("oauth.token", **renew, refresh_token=second["refresh_token"])
    assert_refused(dead, rule="NFR-13", code="refresh_replayed")

    code = await code_for(app, owner, client_id)
    third = await app.ok("oauth.token", **exchange(client_id, code))
    twice = await app.call("oauth.token", **exchange(client_id, code))
    assert_refused(twice, rule="NFR-13", code="code_replayed")
    with pytest.raises(Exception, match="Sign in"):
        await authenticate(third["access_token"], on_mcp=True, audience=audience(app))

    clock.advance(minutes=61)
    code = await code_for(app, await app.login(owner.email), client_id)
    fourth = await app.ok("oauth.token", **exchange(client_id, code))
    clock.advance(minutes=61)
    with pytest.raises(Exception, match="Sign in"):
        await authenticate(fourth["access_token"], on_mcp=True, audience=audience(app))


@pytest.mark.attack("NFR-13")
async def test_NFR_13_registration_is_capped_and_redirects_stay_on_this_machine(app: App) -> None:
    """NFR-13, IF-5.1: a client registers itself, but only with redirect addresses on the
    allowlist (this machine), and at most 200 clients exist. The standard endpoints are
    the same operations: metadata names S256 only, and the token endpoint takes a form."""
    for uri in ("https://evil.example/cb", "http://localhost.evil.example/cb", "ftp://localhost/"):
        refused = await app.call("oauth.register", client_name="Odd", redirect_uris=[uri])
        assert_refused(refused, rule="NFR-13", code="redirect_not_allowed")
    async with app.client() as http:
        meta = (await http.get("/.well-known/oauth-authorization-server")).json()
        assert meta["code_challenge_methods_supported"] == ["S256"]
        assert meta["token_endpoint"].endswith("/oauth/token")
        made = await http.post(
            "/oauth/register", json={"client_name": "By the book", "redirect_uris": [REDIRECT]}
        )
        assert made.status_code == 201
        wrong = await http.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code", "client_id": made.json()["client_id"],
                "code": "cm_code_guess", "redirect_uri": REDIRECT, "code_verifier": VERIFIER,
            },
        )  # fmt: skip
        assert (wrong.status_code, wrong.json()["error"]) == (400, "invalid_code")
        sent = await http.get("/oauth/authorize?client_id=abc&state=1", follow_redirects=False)
        assert sent.headers["location"].startswith("/#/oauth/approve?client_id=abc")

    async with app.runtime.sessions() as session, session.begin():
        have = await session.scalar(select(func.count()).select_from(OAuthClient)) or 0
        for number in range(200 - have):
            session.add(
                OAuthClient(
                    name=f"Client {number}", redirect_uris=[REDIRECT],
                    created_at=app.runtime.clock(),
                )
            )  # fmt: skip
    full = await app.call("oauth.register", client_name="One too many", redirect_uris=[REDIRECT])
    assert_refused(full, rule="NFR-13", code="too_many_clients")


async def test_IF_5_1_a_person_revokes_a_client(app: App) -> None:
    """IF-5.1, INV-5: a person lists the clients they approved and revokes one. Its tokens
    stop working at once. Another person sees and revokes nothing of theirs."""
    owner = await app.person("owner@example.com")
    outsider = await app.person("outsider@example.com")
    client_id = await registered(app)
    tokens = await app.ok(
        "oauth.token", **exchange(client_id, await code_for(app, owner, client_id))
    )
    (grant,) = (await app.ok("oauth.clients", owner))["items"]
    assert (grant["client_name"], grant["scopes"]) == ("Desk assistant", ["read", "steer"])
    assert (await app.ok("oauth.clients", outsider))["items"] == []
    theirs = await app.call("oauth.revoke", outsider, grant_id=grant["grant_id"])
    assert theirs.status_code == 404
    left = await app.ok("oauth.revoke", owner, grant_id=grant["grant_id"])
    assert left["items"] == []
    with pytest.raises(Exception, match="Sign in"):
        await app.runtime.authenticator.authenticate(
            tokens["access_token"], on_mcp=True, audience=audience(app)
        )
