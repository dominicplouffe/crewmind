"""Signing in to an MCP server, and keeping its tokens fresh (CON-10, CON-14).

The person who owns the server starts the sign-in in their browser; the authorization
server sends the browser back to Nightsquad's callback with a code. The sign-in's `state`
is single use, kept only as a hash, expires, and is bound to the browser session that
started it. Tokens are secrets of the server's connection; they act as the signed-in
person's account at that provider.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightsquad.catalog.caller import Authority, Caller
from nightsquad.catalog.define import operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.connections import mcp, mcp_oauth, service
from nightsquad.domain.connections.item_operations import ConnectionRef
from nightsquad.domain.connections.mcp import (
    OAUTH_ACCESS,
    OAUTH_CLIENT_SECRET,
    OAUTH_REFRESH,
    AuthKind,
    ServerState,
)
from nightsquad.domain.connections.mcp_client import CommandSpec, Probe, Target, Unreachable, probe
from nightsquad.domain.connections.model import (
    SECRET_NAME,
    SECRET_OWNER,
    ConnectionState,
    Kind,
    Scope,
)
from nightsquad.domain.integrations import alerts
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.domain.settings.registry import Scope as SettingScope
from nightsquad.domain.settings.service import INSTALL_SUBJECT, Subject
from nightsquad.services import CLOCK, SESSIONS, Services, services_of
from nightsquad.storage.events import event_type
from nightsquad.storage.models import Connection, ConnectionVariable, McpServer, McpSignIn

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


def sessions_of(services: Services) -> async_sessionmaker[AsyncSession]:
    found: async_sessionmaker[AsyncSession] = services.wired[SESSIONS]
    return found


def clock_of(services: Services) -> Callable[[], datetime]:
    found: Callable[[], datetime] = services.wired[CLOCK]
    return found


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


def callback_of(base_url: str) -> str:
    base = base_url.rstrip("/")
    parts = urlsplit(base)
    local = parts.hostname in ("localhost", "127.0.0.1")
    if parts.scheme != "https" and not local:
        raise Refusal(
            "oauth_needs_https",
            "Signing in with OAuth needs Nightsquad's public https address, so the provider can "
            "send you back.",
            rule=CON_10.id,
            hint="An admin sets NIGHTSQUAD_PUBLIC_URL to the install's https address.",
        )
    return base + CALLBACK_PATH


def _seconds(services: Services) -> float:
    return float(str(services.settings.registry.settings["mcp.call_timeout"].default))


def _return_to(item: Connection) -> str:
    if item.scope == Scope.PROJECT:
        return f"/projects/{item.owner_id}?panel=connections"
    return "/settings/connections"


async def _oauth_server(
    session: AsyncSession, caller: Caller, payload: SignInInput
) -> tuple[Connection, McpServer]:
    item = await service.manageable(session, caller, payload.connection, payload.project_id)
    server = await session.get(McpServer, item.id)
    if item.kind != Kind.MCP_SERVER or server is None or server.auth_kind != AuthKind.OAUTH:
        raise Refusal("not_oauth", f"{item.name} does not sign in with OAuth.", rule=CON_10.id)
    if caller.credential_id is None:
        raise Refusal("browser_needed", "Sign in from your browser.", rule=CON_10.id)
    return item, server


@dataclass(frozen=True)
class Discovered:
    endpoints: mcp_oauth.Endpoints
    client_id: str
    client_secret: str | None
    redirect: str

    def __repr__(self) -> str:  # never shows the client secret
        return f"Discovered({self.endpoints.issuer}, client {self.client_id})"


async def _prepare_sign_in(caller: Caller, payload: SignInInput, services: Services) -> Discovered:
    """The provider is reached here, with no database transaction open (CON-10)."""
    async with sessions_of(services)() as session:
        item, server = await _oauth_server(session, caller, payload)
        url, private = server.url or "", server.private_allowed
    redirect = callback_of(services.base_url)
    seconds = _seconds(services)
    try:
        endpoints = await mcp_oauth.discover(url, private_allowed=private, seconds=seconds)
        if payload.client_id:
            pasted = payload.client_secret.get_secret_value() if payload.client_secret else None
            return Discovered(endpoints, payload.client_id, pasted, redirect)
        client_id, secret = await mcp_oauth.register(
            endpoints, redirect, private_allowed=private, seconds=seconds
        )
    except Unreachable as error:
        raise Refusal(
            "oauth_unavailable",
            f"Signing in to {item.name} cannot start: {error}.",
            rule=CON_10.id,
            hint="Paste a client id from the provider if it offers no registration.",
        ) from None
    return Discovered(endpoints, client_id, secret, redirect)


@operation(
    "connections.sign_in",
    summary="Start signing in to an MCP server with OAuth; open the address it returns.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
    prepare=_prepare_sign_in,
)
async def sign_in(context: Context, payload: SignInInput) -> SignInStart:
    """CON-10: discovery, registration (or a pasted client), PKCE S256, a single-use state
    bound to this browser session, and the resource indicator."""
    item, server = await _oauth_server(context.session, context.caller, payload)
    found: Discovered = context.prepared
    endpoints = found.endpoints
    store = SecretStore(services_of(context).master_key_file)
    owner = (SECRET_OWNER, item.id)
    if found.client_secret:
        await store.put(
            context.session, owner, OAUTH_CLIENT_SECRET, found.client_secret, context.now
        )
    else:
        await store.delete(context.session, owner, OAUTH_CLIENT_SECRET)
    server.oauth = {
        **(server.oauth or {}),
        "issuer": endpoints.issuer,
        "authorization_endpoint": endpoints.authorization,
        "token_endpoint": endpoints.token,
        "resource": endpoints.resource,
        "client_id": found.client_id,
        "scopes": endpoints.scopes,
    }
    verifier, challenge = mcp_oauth.new_verifier()
    state, key = mcp_oauth.new_state()
    assert context.caller.credential_id is not None
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
        after={"name": item.name, "issuer": endpoints.issuer, "client_id": found.client_id},
    )
    return SignInStart(
        authorize_url=mcp_oauth.authorize_url(
            endpoints, found.client_id, found.redirect, state, challenge
        ),
        acts_as=f"Nightsquad will act as your account at {urlsplit(endpoints.issuer).hostname} "
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


@dataclass(frozen=True)
class Finished:
    connection_id: str
    return_to: str
    tokens: mcp_oauth.Tokens
    probe: Probe | None
    failure: str | None


async def _prepare_finish(caller: Caller, payload: FinishInput, services: Services) -> Finished:
    """CON-10: the state is used up in its own transaction, so it can never be replayed;
    the provider and the server are reached with no transaction open."""
    key = mcp_oauth.state_key(payload.state)
    store = SecretStore(services.master_key_file)
    now = clock_of(services)()
    async with sessions_of(services)() as session, session.begin():
        row = await session.get(McpSignIn, key)
        if row is None:
            raise _refused("this sign-in is unknown or was already used")
        await session.delete(row)
        owner = (VERIFIER_OWNER, key[:VERIFIER_ID])
        verifier = await store.reveal(session, owner, "verifier")
        await store.delete(session, owner, "verifier")
        expired = row.created_at + SIGN_IN_LIFE < now
        someone_else = row.person_id != caller.actor_id or row.session_id != caller.credential_id
        item = await session.get(Connection, row.connection_id)
        server = await session.get(McpServer, row.connection_id)
        oauth: dict[str, Any] = dict(server.oauth or {}) if server is not None else {}
        secret = (
            await store.reveal(session, (SECRET_OWNER, row.connection_id), OAUTH_CLIENT_SECRET)
            if item is not None
            else None
        )
        url = server.url or "" if server is not None else ""
        private = server.private_allowed if server is not None else False
        return_to = row.return_to
    if expired:
        raise _refused("it took longer than ten minutes")
    if someone_else:
        raise _refused("it was started in another browser session")
    if item is None or server is None or verifier is None:
        raise _refused("the server is gone")
    seconds = _seconds(services)
    try:
        tokens = await mcp_oauth.exchange(
            str(oauth["token_endpoint"]), str(oauth["resource"]), str(oauth["client_id"]), secret,
            payload.code, verifier, callback_of(services.base_url), private_allowed=private,
            seconds=seconds,
        )  # fmt: skip
    except Unreachable as error:
        raise _refused(str(error)) from None
    async with sessions_of(services)() as session:
        most = int(
            await services.settings.get(
                session, Subject(SettingScope.INSTALL, INSTALL_SUBJECT), "mcp.description_max"
            )
        )
    try:
        found = await probe(
            url, {"Authorization": f"Bearer {tokens.access}"}, private_allowed=private,
            seconds=seconds, description_max=most,
        )  # fmt: skip
        return Finished(item.id, return_to, tokens, found, None)
    except Unreachable as error:
        return Finished(item.id, return_to, tokens, None, str(error))


@operation(
    "connections.finish_sign_in",
    summary="Finish an MCP sign-in with the code the provider sent back to the browser.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
    prepare=_prepare_finish,
)
async def finish_sign_in(context: Context, payload: FinishInput) -> SignedIn:
    """CON-10: the state is used once, within its life, by the same person in the same
    browser session; then the code and the verifier become tokens and the tools are read."""
    done: Finished = context.prepared
    item = await context.session.get(Connection, done.connection_id)
    server = await context.session.get(McpServer, done.connection_id)
    if item is None or server is None:
        raise _refused("the server is gone")
    store = SecretStore(services_of(context).master_key_file)
    await store_tokens(context.session, store, server, done.tokens, context.now)
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
    if done.probe is not None:
        await mcp.sync_tools(context.session, server, item, done.probe, context.now, context.caller)
        mcp.worked(context.session, server, item, context.now, context.caller)
    else:
        mcp.failed(context.session, server, item, done.failure or "", context.now, context.caller)
    await service.refresh_users(context.session, item, context.now, context.caller)
    return SignedIn(name=item.name, return_to=done.return_to)


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


async def target_for(
    session: AsyncSession, store: SecretStore, server: McpServer, item: Connection, now: datetime,
    caller: Caller, *, seconds: float, force: bool = False,
) -> Target:  # fmt: skip
    """CON-9, CON-11: how to reach the server now. For a remote server, its address and fresh
    sign-in headers; for a command server, its command and the values of only the variables
    it was given, read from their connections."""
    if server.kind != "command":
        headers = await fresh_headers(
            session, store, server, item, now, caller, seconds=seconds, force=force
        )
        return Target(server.url or "", headers, server.private_allowed, server.transport)
    values: dict[str, str] = {}
    for env, connection_id in (server.environment or {}).items():
        source = await session.get(Connection, str(connection_id))
        if source is None or source.state != ConnectionState.ACTIVE:
            raise Unreachable(f"the connection it needs for {env} is gone or expired")
        if source.kind == Kind.VARIABLE:
            variable = await session.get(ConnectionVariable, source.id)
            value = variable.value if variable is not None else None
        else:
            value = await store.reveal(session, (SECRET_OWNER, source.id), SECRET_NAME)
        if value is None:
            raise Unreachable(f"the connection it needs for {env} has no value")
        values[str(env)] = value
    spec = CommandSpec(server.connection_id, server.image, tuple(server.command or []), values)
    return Target("", {}, False, None, spec)


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
