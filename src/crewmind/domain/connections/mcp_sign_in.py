"""Signing in to an MCP server, and keeping its tokens fresh (CON-10, CON-14).

The person who owns the server starts the sign-in in their browser; the authorization
server sends the browser back to crewmind's callback with a code. The sign-in's `state`
is single use, kept only as a hash, expires, and is bound to the browser session that
started it. Tokens are secrets of the server's connection; they act as the signed-in
person's account at that provider.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Authority, Caller
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.connections import mcp, mcp_oauth, service
from crewmind.domain.connections.item_operations import ConnectionRef
from crewmind.domain.connections.mcp import (
    OAUTH_ACCESS,
    OAUTH_CLIENT_SECRET,
    OAUTH_REFRESH,
    AuthKind,
    ServerState,
)
from crewmind.domain.connections.mcp_client import Unreachable, probe
from crewmind.domain.connections.model import SECRET_OWNER, Kind, Scope
from crewmind.domain.integrations import alerts
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.registry import Scope as SettingScope
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import Connection, McpServer, McpSignIn

CON_10 = rules.register(
    Rule("CON-10", "An MCP sign-in finishes only in the browser session that started it.")
)

CALLBACK_PATH = "/v1/connections/oauth/callback"
SIGN_IN_LIFE = timedelta(minutes=10)
"""CON-10: a sign-in not finished within ten minutes is gone."""
REFRESH_AHEAD = timedelta(minutes=1)
"""CON-10: tokens are refreshed a minute before they expire."""
VERIFIER_OWNER = "mcp_sign_in"
VERIFIER_ID = 32
"""The verifier is kept under the first 32 hex digits (128 bits) of the state's hash, the
length of a secret owner's id."""
SIGNED_IN = event_type("mcp.signed_in", "Someone signed in to an MCP server (CON-10).")
SIGN_IN_STARTED = event_type("mcp.sign_in_started", "A sign-in to an MCP server began (CON-10).")


class SignInInput(ConnectionRef):
    client_id: str | None = Field(
        default=None,
        description="A client id from the provider, when its server offers no registration.",
    )
    client_secret: SecretStr | None = Field(
        default=None, description="That client's secret, if the provider gave one."
    )


class SignInStart(BaseModel):
    authorize_url: str = Field(description="Open this in the browser to sign in.")
    acts_as: str = Field(description="What signing in means, in plain words.")


class FinishInput(BaseModel):
    code: str = Field(description="The code the provider sent back.")
    state: str = Field(description="The state the provider sent back.")


class SignedIn(BaseModel):
    name: str
    return_to: str = Field(description="Where the person goes back to.")


def _callback(context: Context) -> str:
    base = services_of(context).base_url.rstrip("/")
    parts = urlsplit(base)
    local = parts.hostname in ("localhost", "127.0.0.1")
    if parts.scheme != "https" and not local:
        raise Refusal(
            "oauth_needs_https",
            "Signing in with OAuth needs crewmind's public https address, so the provider can "
            "send you back.",
            rule=CON_10.id,
            hint="An admin sets CREWMIND_PUBLIC_URL to the install's https address.",
        )
    return base + CALLBACK_PATH


async def _limits(context: Context) -> float:
    return float(str(services_of(context).settings.registry.settings["mcp.call_timeout"].default))


def _return_to(item: Connection) -> str:
    if item.scope == Scope.PROJECT:
        return f"/projects/{item.owner_id}?panel=connections"
    return "/settings/connections"


@operation(
    "connections.sign_in",
    summary="Start signing in to an MCP server with OAuth; open the address it returns.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def sign_in(context: Context, payload: SignInInput) -> SignInStart:
    """CON-10: discovery, registration (or a pasted client), PKCE S256, a single-use state
    bound to this browser session, and the resource indicator."""
    item = await service.manageable(
        context.session, context.caller, payload.connection, payload.project_id
    )
    server = await context.session.get(McpServer, item.id)
    if item.kind != Kind.MCP_SERVER or server is None or server.auth_kind != AuthKind.OAUTH:
        raise Refusal("not_oauth", f"{item.name} does not sign in with OAuth.", rule=CON_10.id)
    if context.caller.credential_id is None:
        raise Refusal("browser_needed", "Sign in from your browser.", rule=CON_10.id)
    redirect = _callback(context)
    seconds = await _limits(context)
    try:
        endpoints = await mcp_oauth.discover(
            server.url or "", private_allowed=server.private_allowed, seconds=seconds
        )
        if payload.client_id:
            client_id, secret = (
                payload.client_id,
                (payload.client_secret.get_secret_value() if payload.client_secret else None),
            )
        else:
            client_id, secret = await mcp_oauth.register(
                endpoints, redirect, private_allowed=server.private_allowed, seconds=seconds
            )
    except Unreachable as error:
        raise Refusal(
            "oauth_unavailable",
            f"Signing in to {item.name} cannot start: {error}.",
            rule=CON_10.id,
            hint="Paste a client id from the provider if it offers no registration.",
        ) from None
    store = SecretStore(services_of(context).master_key_file)
    if secret:
        await store.put(
            context.session, (SECRET_OWNER, item.id), OAUTH_CLIENT_SECRET, secret, context.now
        )
    else:
        await store.delete(context.session, (SECRET_OWNER, item.id), OAUTH_CLIENT_SECRET)
    server.oauth = {
        **(server.oauth or {}),
        "issuer": endpoints.issuer,
        "authorization_endpoint": endpoints.authorization,
        "token_endpoint": endpoints.token,
        "resource": endpoints.resource,
        "client_id": client_id,
        "scopes": endpoints.scopes,
    }
    verifier, challenge = mcp_oauth.new_verifier()
    state, key = mcp_oauth.new_state()
    context.session.add(
        McpSignIn(
            id=key, connection_id=item.id, person_id=context.caller.actor_id,
            session_id=context.caller.credential_id, return_to=_return_to(item),
            created_at=context.now,
        )
    )  # fmt: skip
    await store.put(
        context.session, (VERIFIER_OWNER, key[:VERIFIER_ID]), "verifier", verifier, context.now
    )
    context.record(
        SIGN_IN_STARTED,
        subject=("connection", item.id),
        after={"name": item.name, "issuer": endpoints.issuer, "client_id": client_id},
    )
    return SignInStart(
        authorize_url=mcp_oauth.authorize_url(endpoints, client_id, redirect, state, challenge),
        acts_as=f"crewmind will act as your account at {urlsplit(endpoints.issuer).hostname} "
        f"when agents use {item.name}.",
    )


def _refused(reason: str) -> Refusal:
    return Refusal(
        "sign_in_failed", f"The sign-in did not finish: {reason}.", kind=RefusalKind.FORBIDDEN,
        rule=CON_10.id, hint="Start the sign-in again from Connections.",
    )  # fmt: skip


async def store_tokens(
    session: AsyncSession, store: SecretStore, server: McpServer, tokens: mcp_oauth.Tokens,
    now: datetime,
) -> None:  # fmt: skip
    """CON-10: tokens are secrets; a rotated refresh token replaces the old one."""
    owner = (SECRET_OWNER, server.connection_id)
    await store.put(session, owner, OAUTH_ACCESS, tokens.access, now)
    if tokens.refresh:
        await store.put(session, owner, OAUTH_REFRESH, tokens.refresh, now)
    expires = (
        (now + timedelta(seconds=tokens.expires_in)).isoformat() if tokens.expires_in else None
    )
    server.oauth = {**(server.oauth or {}), "expires_at": expires}


@operation(
    "connections.finish_sign_in",
    summary="Finish an MCP sign-in with the code the provider sent back to the browser.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def finish_sign_in(context: Context, payload: FinishInput) -> SignedIn:
    """CON-10: the state is used once, within its life, by the same person in the same
    browser session; then the code and the verifier become tokens and the tools are read."""
    key = mcp_oauth.state_key(payload.state)
    row = await context.session.get(McpSignIn, key)
    if row is None:
        raise _refused("this sign-in is unknown or was already used")
    await context.session.delete(row)
    store = SecretStore(services_of(context).master_key_file)
    verifier = await store.reveal(context.session, (VERIFIER_OWNER, key[:VERIFIER_ID]), "verifier")
    await store.delete(context.session, (VERIFIER_OWNER, key[:VERIFIER_ID]), "verifier")
    if row.created_at + SIGN_IN_LIFE < context.now:
        raise _refused("it took longer than ten minutes")
    if row.person_id != context.caller.actor_id or row.session_id != context.caller.credential_id:
        raise _refused("it was started in another browser session")
    item = await context.session.get(Connection, row.connection_id)
    server = await context.session.get(McpServer, row.connection_id)
    if item is None or server is None or verifier is None:
        raise _refused("the server is gone")
    oauth: dict[str, Any] = server.oauth or {}
    seconds = await _limits(context)
    secret = await store.reveal(context.session, (SECRET_OWNER, item.id), OAUTH_CLIENT_SECRET)
    try:
        tokens = await mcp_oauth.exchange(
            str(oauth["token_endpoint"]), str(oauth["resource"]), str(oauth["client_id"]), secret,
            payload.code, verifier, _callback(context), private_allowed=server.private_allowed,
            seconds=seconds,
        )  # fmt: skip
    except Unreachable as error:
        raise _refused(str(error)) from None
    await store_tokens(context.session, store, server, tokens, context.now)
    if server.state == ServerState.NEEDS_SIGN_IN:
        mcp.move(
            context.session,
            server,
            item,
            ServerState.ACTIVE,
            context.now,
            context.caller,
            "signed in",
        )
    context.record(SIGNED_IN, subject=("connection", item.id), after={"name": item.name})
    most = int(
        await services_of(context).settings.get(
            context.session, Subject(SettingScope.INSTALL, INSTALL_SUBJECT), "mcp.description_max"
        )
    )
    try:
        found = await probe(
            server.url or "", {"Authorization": f"Bearer {tokens.access}"},
            private_allowed=server.private_allowed, seconds=seconds, description_max=most,
        )  # fmt: skip
        await mcp.sync_tools(context.session, server, item, found, context.now, context.caller)
        mcp.worked(context.session, server, item, context.now, context.caller)
    except Unreachable as error:
        mcp.failed(context.session, server, item, str(error), context.now, context.caller)
    await service.refresh_users(context.session, item, context.now, context.caller)
    return SignedIn(name=item.name, return_to=row.return_to)


async def fresh_headers(
    session: AsyncSession, store: SecretStore, server: McpServer, item: Connection, now: datetime,
    caller: Caller, *, seconds: float, force: bool = False,
) -> dict[str, str]:  # fmt: skip
    """CON-10, CON-14: the server's sign-in headers, refreshing OAuth tokens a minute before
    they expire (or now, after a refused call). A refused refresh marks the server as
    needing sign-in and raises one alarm for each project that uses it."""
    oauth: dict[str, Any] = server.oauth or {}
    if server.auth_kind != AuthKind.OAUTH:
        return await mcp.headers_for(session, store, server)
    expires = oauth.get("expires_at")
    due = force or (
        expires is not None and datetime.fromisoformat(str(expires)) - REFRESH_AHEAD <= now
    )
    if not due:
        return await mcp.headers_for(session, store, server)
    owner = (SECRET_OWNER, server.connection_id)
    refresh_token = await store.reveal(session, owner, OAUTH_REFRESH)
    secret = await store.reveal(session, owner, OAUTH_CLIENT_SECRET)
    try:
        if refresh_token is None:
            raise Unreachable("there is no refresh token")
        tokens = await mcp_oauth.refresh(
            str(oauth["token_endpoint"]), str(oauth["resource"]), str(oauth["client_id"]), secret,
            refresh_token, private_allowed=server.private_allowed, seconds=seconds,
        )  # fmt: skip
    except Unreachable as error:
        await needs_sign_in(session, server, item, str(error), now, caller)
        raise Unreachable(f"{item.name} needs someone to sign in again") from None
    await store_tokens(session, store, server, tokens, now)
    return {"Authorization": f"Bearer {tokens.access}"}


async def needs_sign_in(
    session: AsyncSession, server: McpServer, item: Connection, why: str, now: datetime,
    caller: Caller,
) -> None:  # fmt: skip
    if server.state == ServerState.NEEDS_SIGN_IN:
        return
    if server.state == ServerState.FAILING:
        mcp.move(session, server, item, ServerState.ACTIVE, now, caller, why)
    mcp.move(session, server, item, ServerState.NEEDS_SIGN_IN, now, caller, why)
    await service.refresh_users(session, item, now, caller)
    for _, project in await service.attachments(session, item.id):
        alerts.queue(
            session, project,
            f"{item.name} needs someone to sign in again; the agents that use it wait until then.",
            now, level=alerts.ALARM,
        )  # fmt: skip
