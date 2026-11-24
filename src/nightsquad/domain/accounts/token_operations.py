"""Personal tokens and MCP client tokens (ACC-3, IF-5.1, IF-5.2, section 7.10)."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from nightsquad.catalog import mcp_scopes
from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.pagination import PageRequest, fetch_page
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.secret import OneTimeSecret
from nightsquad.domain.accounts.credentials import MCP_PREFIX, PERSONAL_PREFIX, mint_secret
from nightsquad.domain.accounts.model import TOKEN_MACHINE, TokenKind, TokenState
from nightsquad.domain.accounts.people import ACC_3
from nightsquad.domain.settings.registry import Scope, SettingValueError
from nightsquad.domain.settings.service import Subject
from nightsquad.services import services_of
from nightsquad.storage.events import event_type
from nightsquad.storage.models import Token

TOKEN_MINTED = event_type("token.minted", "A token was minted (ACC-3).")
TOKEN_REVOKED = event_type("token.revoked", "A token was revoked.")
TOKEN_EXPIRED = event_type("token.expired", "A token passed its expiry date.")

IF_5_2 = rules.register(
    Rule("IF-5.2", "An MCP client sees and calls only the tools its scopes grant.")
)

SECONDS_PER_DAY = 86_400
SCOPES_AVAILABLE = mcp_scopes.SCOPES
"""IF-5.2: the four MCP scopes. `read` is implied by every other one."""


class MintTokenInput(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="A name to recognise it by.")
    expires_in_days: int | None = Field(
        None, description="Days until it expires, 1 to 365. Default: your token.default_expiry."
    )


class MintMcpInput(BaseModel):
    client_name: str = Field(min_length=1, max_length=100, description="The MCP client's name.")
    scopes: list[str] = Field(default=["read"], description="Scopes to grant.")


class MintedToken(BaseModel):
    token_id: str
    name: str
    token: OneTimeSecret = Field(description="The token. Shown once; it cannot be read again.")
    scopes: list[str]
    expires_at: datetime | None


class TokenItem(BaseModel):
    token_id: str
    name: str
    scopes: list[str]
    state: str
    created_at: datetime
    expires_at: datetime | None


class TokenList(BaseModel):
    items: list[TokenItem]
    next: str | None = None


class TokenRef(BaseModel):
    token_id: str = Field(description="The token's id, from the list.")


def _item(token: Token, now: datetime) -> TokenItem:
    state = token.state
    if state == TokenState.ACTIVE and token.expires_at is not None and now >= token.expires_at:
        state = TokenState.EXPIRED
    return TokenItem(
        token_id=token.id,
        name=token.name,
        scopes=[str(scope) for scope in token.scopes],
        state=state,
        created_at=token.created_at,
        expires_at=token.expires_at,
    )


async def _mint(
    context: Context,
    kind: TokenKind,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
) -> MintedToken:
    plain, digest = mint_secret(MCP_PREFIX if kind is TokenKind.MCP else PERSONAL_PREFIX)
    TOKEN_MACHINE.check("(new)", TokenState.ACTIVE)
    token = Token(
        token_hash=digest,
        kind=kind,
        person_id=context.caller.actor_id,
        name=name,
        scopes=scopes,
        state=TokenState.ACTIVE,
        created_at=context.now,
        expires_at=expires_at,
        revoked_at=None,
    )
    context.session.add(token)
    await context.session.flush()
    context.record(
        TOKEN_MINTED,
        subject=("token", token.id),
        after={"state": TokenState.ACTIVE, "kind": kind, "name": name, "scopes": scopes},
    )
    return MintedToken(
        token_id=token.id, name=name, token=plain, scopes=scopes, expires_at=expires_at
    )


async def _list(context: Context, kind: TokenKind, page: PageRequest) -> TokenList:
    rows, cursor = await fetch_page(
        context.session,
        select(Token).where(Token.person_id == context.caller.actor_id, Token.kind == kind),
        page,
        key=Token.id,
        at=Token.created_at,
    )
    return TokenList(items=[_item(row, context.now) for row in rows], next=cursor)


async def _revoke(context: Context, kind: TokenKind, token_id: str) -> TokenItem:
    token = await context.session.get(Token, token_id)
    owns = token is not None and (
        token.person_id == context.caller.actor_id or context.caller.is_admin
    )
    if token is None or token.kind != kind or not owns:
        raise Refusal(
            "token_not_found", "There is no token with that id.", kind=RefusalKind.NOT_FOUND
        )
    TOKEN_MACHINE.check(_item(token, context.now).state, TokenState.REVOKED)
    token.state = TokenState.REVOKED
    token.revoked_at = context.now
    context.record(
        TOKEN_REVOKED,
        subject=("token", token.id),
        before={"state": TokenState.ACTIVE},
        after={"state": TokenState.REVOKED},
    )
    return _item(token, context.now)


@operation(
    "tokens.mint",
    summary="Mint a named personal token that expires.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def mint_token(context: Context, payload: MintTokenInput) -> MintedToken:
    """ACC-3: tokens are named and expire after 1 to 365 days. None lasts for ever."""
    services = services_of(context)
    definition = services.registry.get("token.default_expiry")
    subject = Subject(Scope.PERSON, context.caller.actor_id)
    if payload.expires_in_days is None:
        seconds = await services.settings.get(context.session, subject, definition.name)
    else:
        seconds = payload.expires_in_days * SECONDS_PER_DAY
    try:
        definition.validate_value(seconds)
    except SettingValueError:
        raise Refusal(
            "token_expiry_out_of_range",
            f"A token expires after 1 to 365 days; {payload.expires_in_days} was asked for. "
            "Tokens that never expire are not offered.",
            rule=ACC_3.id,
            hint="Choose 1 to 365 days.",
        ) from None
    expires_at = context.now + timedelta(seconds=seconds)
    return await _mint(context, TokenKind.PERSONAL, payload.name, [], expires_at)


@operation(
    "tokens.list",
    summary="List your personal tokens. Values are never shown.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def list_tokens(context: Context, payload: PageRequest) -> TokenList:
    return await _list(context, TokenKind.PERSONAL, payload)


@operation(
    "tokens.revoke",
    summary="Revoke a personal token.",
    authority=Authority.PERSON,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def revoke_token(context: Context, payload: TokenRef) -> TokenItem:
    return await _revoke(context, TokenKind.PERSONAL, payload.token_id)


@operation(
    "mcp_clients.mint",
    summary="Mint a token for an MCP client, limited to the scopes you choose.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def mint_mcp_token(context: Context, payload: MintMcpInput) -> MintedToken:
    """IF-5.1, IF-5.2: a client gets its own token, never the person's credential."""
    scopes = sorted(set(payload.scopes))
    unavailable = [scope for scope in scopes if scope not in SCOPES_AVAILABLE]
    if unavailable or not scopes:
        raise Refusal(
            "scope_unavailable",
            f"Only these scopes can be granted now: {', '.join(SCOPES_AVAILABLE)}. "
            f"Asked for: {', '.join(scopes) or 'none'}.",
            rule=IF_5_2.id,
            hint="Choose from read, steer, create and configure.",
        )
    return await _mint(context, TokenKind.MCP, payload.client_name, scopes, None)


@operation(
    "mcp_clients.list",
    summary="List your MCP client tokens. Values are never shown.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def list_mcp_tokens(context: Context, payload: PageRequest) -> TokenList:
    return await _list(context, TokenKind.MCP, payload)


@operation(
    "mcp_clients.revoke",
    summary="Revoke an MCP client's token.",
    authority=Authority.PERSON,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def revoke_mcp_token(context: Context, payload: TokenRef) -> TokenItem:
    return await _revoke(context, TokenKind.MCP, payload.token_id)
