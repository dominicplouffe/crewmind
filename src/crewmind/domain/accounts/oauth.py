"""OAuth 2.1 for MCP clients (IF-5.1, NFR-13): authorization code with PKCE S256, dynamic
client registration, audience-bound access tokens and rotating refresh tokens.

Each step is an operation, so there is one implementation behind the standard endpoints.
The person approves a client in their own browser session; no client approves itself.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog import mcp_scopes
from crewmind.catalog.caller import Authority
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.secret import OneTimeSecret
from crewmind.domain.accounts.credentials import MCP_PREFIX, hash_secret, mint_secret
from crewmind.domain.accounts.model import TokenKind, TokenState
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import OAuthClient, OAuthCode, OAuthRefresh, Token, new_id

IF_5_1 = rules.register(
    Rule("IF-5.1", "OAuth resists PKCE stripping, code replay, redirect swap and widening.")
)
NFR_13 = rules.register(
    Rule("NFR-13", "Codes are single-use for 60 s; refresh tokens rotate; replay is theft.")
)
OAUTH_GRANTED = event_type("oauth.granted", "A person approved an MCP client (IF-5.1).")
OAUTH_REVOKED = event_type("oauth.revoked", "An MCP client's grant was revoked.")
OAUTH_CLIENT = event_type("oauth.client_registered", "An MCP client registered itself.")
MCP_PATH = "/mcp"
CODE_LIFE = timedelta(seconds=60)  # NFR-13
ACCESS_LIFE = timedelta(hours=1)  # NFR-13
CLIENTS_MOST = 200  # NFR-13
LOOPBACK = ("localhost", "127.0.0.1", "[::1]")
"""NFR-13: redirect hosts allowed by default. Hosted clients are added by the admin."""
REFRESH_PREFIX, CODE_PREFIX = "cm_refresh_", "cm_code_"
ACTIVE, USED, REVOKED = "active", "used", "revoked"


def audience_of(base_url: str) -> str:
    """The one resource this server issues tokens for: its own MCP endpoint (RFC 8707)."""
    return base_url.rstrip("/") + MCP_PATH


def _refuse(code: str, message: str, rule: Rule = IF_5_1) -> Refusal:
    return Refusal(code, message, rule=rule.id, kind=RefusalKind.FORBIDDEN)


def redirect_allowed(uri: str) -> bool:
    parts = urlsplit(uri)
    host = parts.netloc.rsplit(":", 1)[0] if parts.netloc.count(":") == 1 else parts.netloc
    return parts.scheme == "http" and host in LOOPBACK and not parts.fragment


def pkce_matches(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge


class RegisterInput(BaseModel):
    client_name: str = Field(min_length=1, max_length=100, description="The client's name.")
    redirect_uris: list[str] = Field(min_length=1, max_length=5, description="Where codes go.")


class RegisteredClient(BaseModel):
    client_id: str
    client_name: str
    redirect_uris: list[str]


class ApproveInput(BaseModel):
    client_id: str
    redirect_uri: str = Field(description="One of the client's registered redirect addresses.")
    scopes: list[str] = Field(description="read, steer, create, configure.")
    code_challenge: str = Field(default="", description="The PKCE challenge.")
    code_challenge_method: str = Field(default="", description="Must be S256.")
    resource: str = Field(default="", description="The MCP server the token is for.")
    state: str = Field(default="", max_length=500, description="Returned to the client as is.")


class Approved(BaseModel):
    redirect_to: OneTimeSecret = Field(
        description="Where to send the browser. It carries the one-time code."
    )


class TokenInput(BaseModel):
    grant_type: Literal["authorization_code", "refresh_token"]
    client_id: str
    code: str | None = None
    redirect_uri: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None
    resource: str | None = None
    scope: str | None = Field(default=None, description="May narrow the grant, never widen it.")


class Tokens(BaseModel):
    access_token: OneTimeSecret
    refresh_token: OneTimeSecret
    token_type: str = "Bearer"
    expires_in: int
    scope: str


class GrantItem(BaseModel):
    grant_id: str
    client_name: str
    scopes: list[str]
    since: datetime


class GrantList(BaseModel):
    items: list[GrantItem]


class GrantRef(BaseModel):
    grant_id: str = Field(description="The grant's id, from `oauth clients`.")


class Empty(BaseModel):
    pass


@operation(
    "oauth.register",
    summary="Register an MCP client so a person can approve it.",
    authority=Authority.ANYONE,
    reversibility=Reversibility.REVERSIBLE,
)
async def register(context: Context, payload: RegisterInput) -> RegisteredClient:
    """IF-5.1, NFR-13: dynamic client registration. Redirects must be on the allowlist
    (this machine by default), and at most 200 clients exist."""
    count = await context.session.scalar(select(func.count()).select_from(OAuthClient))
    if int(count or 0) >= CLIENTS_MOST:
        raise _refuse("too_many_clients", f"{CLIENTS_MOST} clients are registered already.", NFR_13)
    bad = [uri for uri in payload.redirect_uris if not redirect_allowed(uri)]
    if bad:
        raise _refuse(
            "redirect_not_allowed",
            f"A redirect address must be http on this machine (localhost). Not allowed: "
            f"{', '.join(bad)}.",
            NFR_13,
        )
    client = OAuthClient(
        name=payload.client_name.strip(),
        redirect_uris=list(payload.redirect_uris),
        created_at=context.now,
    )
    context.session.add(client)
    await context.session.flush()
    context.record(OAUTH_CLIENT, subject=("oauth_client", client.id), after={"name": client.name})
    return RegisteredClient(
        client_id=client.id, client_name=client.name, redirect_uris=list(payload.redirect_uris)
    )


@operation(
    "oauth.approve",
    summary="Approve an MCP client for the scopes you choose. Returns where to send the browser.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def approve(context: Context, payload: ApproveInput) -> Approved:
    """IF-5.1, IF-5.6, NFR-13: the person approves in their own session. PKCE S256 is
    required, the redirect must match a registered one exactly, and the token is bound to
    this server's MCP endpoint."""
    client = await context.session.get(OAuthClient, payload.client_id)
    if client is None:
        raise _refuse("unknown_client", "This client is not registered.")
    if payload.redirect_uri not in client.redirect_uris:
        raise _refuse(
            "redirect_mismatch",
            "The redirect address is not one this client registered, character for character.",
        )
    if payload.code_challenge_method != "S256" or not payload.code_challenge:
        raise _refuse("pkce_required", "PKCE with the S256 method is required.")
    audience = audience_of(services_of(context).base_url)
    if payload.resource != audience:
        raise _refuse("wrong_audience", f"A token from this server is only for {audience}.", NFR_13)
    scopes = sorted(set(payload.scopes))
    if not scopes or any(scope not in mcp_scopes.SCOPES for scope in scopes):
        raise _refuse("unknown_scope", f"Choose from: {', '.join(mcp_scopes.SCOPES)}.")
    plain, digest = mint_secret(CODE_PREFIX)
    family_id = new_id()
    context.session.add(
        OAuthCode(
            code_hash=digest,
            client_id=client.id,
            person_id=context.caller.actor_id,
            redirect_uri=payload.redirect_uri,
            challenge=payload.code_challenge,
            scopes=scopes,
            audience=audience,
            family_id=family_id,
            expires_at=context.now + CODE_LIFE,
        )
    )
    context.record(
        OAUTH_GRANTED,
        subject=("oauth_client", client.id),
        after={"client": client.name, "scopes": scopes},
    )
    query = {"code": plain, **({"state": payload.state} if payload.state else {})}
    return Approved(redirect_to=f"{payload.redirect_uri}?{urlencode(query)}")


async def _revoke_family(session: AsyncSession, family_id: str, now: datetime) -> None:
    """Theft or a person's own revoke: end every token of one grant."""
    await session.execute(
        update(OAuthRefresh).where(OAuthRefresh.family_id == family_id).values(state=REVOKED)
    )
    await session.execute(
        update(Token)
        .where(Token.family_id == family_id, Token.state == TokenState.ACTIVE)
        .values(state=TokenState.REVOKED, revoked_at=now)
    )


async def _issue(
    session: AsyncSession,
    client: OAuthClient,
    person_id: str,
    scopes: list[str],
    audience: str,
    family_id: str,
    now: datetime,
) -> Tokens:
    access, access_hash = mint_secret(MCP_PREFIX)
    refresh, refresh_hash = mint_secret(REFRESH_PREFIX)
    session.add(
        Token(
            token_hash=access_hash,
            kind=TokenKind.MCP,
            person_id=person_id,
            name=client.name,
            scopes=scopes,
            state=TokenState.ACTIVE,
            created_at=now,
            expires_at=now + ACCESS_LIFE,
            revoked_at=None,
            audience=audience,
            family_id=family_id,
        )
    )
    session.add(
        OAuthRefresh(
            token_hash=refresh_hash,
            family_id=family_id,
            client_id=client.id,
            person_id=person_id,
            scopes=scopes,
            audience=audience,
            state=ACTIVE,
            created_at=now,
        )
    )
    return Tokens(
        access_token=access,
        refresh_token=refresh,
        expires_in=int(ACCESS_LIFE.total_seconds()),
        scope=" ".join(scopes),
    )


def _then_revoke(refusal: Refusal, family_id: str, now: datetime) -> Refusal:
    """A replay is refused and, in a transaction of its own, the grant is revoked."""

    async def afterwards(session: AsyncSession) -> None:
        await _revoke_family(session, family_id, now)

    refusal.afterwards = afterwards
    return refusal


def _then_burn(refusal: Refusal, code_id: str) -> Refusal:
    """A code presented wrongly is spent, so it cannot be tried again with other values."""

    async def afterwards(session: AsyncSession) -> None:
        await session.execute(update(OAuthCode).where(OAuthCode.id == code_id).values(used=True))

    refusal.afterwards = afterwards
    return refusal


def _code_problem(row: OAuthCode, payload: TokenInput, now: datetime) -> Refusal | None:
    if now > row.expires_at:
        return _refuse("code_expired", "A code lasts 60 seconds.", NFR_13)
    if payload.redirect_uri != row.redirect_uri:
        return _refuse("redirect_mismatch", "The redirect address differs from the request.")
    if not payload.code_verifier or not pkce_matches(payload.code_verifier, row.challenge):
        return _refuse("pkce_failed", "The PKCE verifier does not match the challenge.")
    if payload.resource is not None and payload.resource != row.audience:
        return _refuse("wrong_audience", f"This code is only for {row.audience}.", NFR_13)
    return None


def _narrowed(granted: list[Any], asked: str | None) -> list[str]:
    """The scopes to issue. Asking for one that was not granted is refused."""
    have = [str(scope) for scope in granted]
    if asked is None:
        return have
    wanted = sorted(set(asked.split()))
    if not wanted or any(scope not in have for scope in wanted):
        raise _refuse("scope_widened", "A token carries only scopes the person approved.")
    return wanted


@operation(
    "oauth.token",
    summary="Exchange an authorization code or a refresh token for an access token.",
    authority=Authority.ANYONE,
    reversibility=Reversibility.REVERSIBLE,
)
async def token(context: Context, payload: TokenInput) -> Tokens:
    """IF-5.1, NFR-13: a code is used once, within 60 seconds, by the client it was issued
    to, with the redirect and the PKCE verifier it was issued for. A refresh token is
    rotated on every use; using one twice revokes the whole grant."""
    client = await context.session.get(OAuthClient, payload.client_id)
    if client is None:
        raise _refuse("unknown_client", "This client is not registered.")
    if payload.grant_type == "authorization_code":
        row = await context.session.scalar(
            select(OAuthCode).where(OAuthCode.code_hash == hash_secret(payload.code or ""))
        )
        if row is None or row.client_id != client.id:
            raise _refuse("invalid_code", "This code is not valid for this client.")
        if row.used:
            raise _then_revoke(
                _refuse(
                    "code_replayed",
                    "This code was already used. The tokens it produced are revoked.",
                    NFR_13,
                ),
                row.family_id,
                context.now,
            )
        problem = _code_problem(row, payload, context.now)
        if problem is not None:
            raise _then_burn(problem, row.id)
        row.used = True
        scopes = _narrowed(row.scopes, payload.scope)
        return await _issue(
            context.session, client, row.person_id, scopes, row.audience, row.family_id,
            context.now,
        )  # fmt: skip
    old = await context.session.scalar(
        select(OAuthRefresh).where(
            OAuthRefresh.token_hash == hash_secret(payload.refresh_token or "")
        )
    )
    if old is None or old.client_id != client.id or not old.family_id:
        raise _refuse("invalid_refresh_token", "This refresh token is not valid for this client.")
    if old.state != ACTIVE:
        raise _then_revoke(
            _refuse(
                "refresh_replayed",
                "This refresh token was already used. Every token of this grant is revoked.",
                NFR_13,
            ),
            old.family_id,
            context.now,
        )
    if payload.resource is not None and payload.resource != old.audience:
        raise _refuse("wrong_audience", f"This grant is only for {old.audience}.", NFR_13)
    old.state = USED
    scopes = _narrowed(old.scopes, payload.scope)
    return await _issue(
        context.session, client, old.person_id, scopes, old.audience, old.family_id, context.now
    )


@operation(
    "oauth.clients",
    summary="List the MCP clients you approved through OAuth.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def clients(context: Context, payload: Empty) -> GrantList:
    """IF-5.1: a person sees their own grants. Token values are never shown."""
    rows = await context.session.execute(
        select(OAuthRefresh, OAuthClient)
        .join(OAuthClient, OAuthClient.id == OAuthRefresh.client_id)
        .where(
            OAuthRefresh.person_id == context.caller.actor_id,
            OAuthRefresh.state == ACTIVE,
        )
        .order_by(OAuthRefresh.created_at)
    )
    return GrantList(
        items=[
            GrantItem(
                grant_id=refresh.family_id,
                client_name=client.name,
                scopes=[str(scope) for scope in refresh.scopes],
                since=refresh.created_at,
            )
            for refresh, client in rows.all()
        ]
    )


@operation(
    "oauth.revoke",
    summary="Revoke an MCP client you approved. Its tokens stop working at once.",
    authority=Authority.PERSON,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def revoke(context: Context, payload: GrantRef) -> GrantList:
    """IF-5.1: the person ends a grant; every token of it is revoked."""
    mine = await context.session.scalar(
        select(OAuthRefresh.id).where(
            OAuthRefresh.family_id == payload.grant_id,
            OAuthRefresh.person_id == context.caller.actor_id,
        )
    )
    if mine is None:
        raise Refusal("grant_not_found", "There is no such grant.", kind=RefusalKind.NOT_FOUND)
    await _revoke_family(context.session, payload.grant_id, context.now)
    context.record(OAUTH_REVOKED, subject=("oauth_grant", payload.grant_id))
    return await clients(context, Empty())
