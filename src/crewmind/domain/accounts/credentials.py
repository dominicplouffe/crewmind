"""Sessions, personal tokens, MCP tokens and links: minting and checking (ACC-2 to ACC-4).

Only hashes are stored (NFR-12). The plain value exists once, in the answer that mints it.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog import mcp_scopes
from crewmind.catalog.caller import ANONYMOUS, Caller, CallerKind, InstanceRole
from crewmind.catalog.execute import Clock, unauthenticated, utc_now
from crewmind.domain.accounts.model import (
    SESSION_MACHINE,
    SESSION_MAX_AGE,
    SESSION_MAX_IDLE,
    TOKEN_MACHINE,
    PersonState,
    SessionState,
    TokenKind,
    TokenState,
)
from crewmind.storage.models import BrowserSession, Person, Token

SESSION_PREFIX = "cm_ses_"
PERSONAL_PREFIX = "cm_pat_"
MCP_PREFIX = "cm_mcp_"
LINK_PREFIX = "cm_lnk_"


def mint_secret(prefix: str) -> tuple[str, str]:
    """A new random credential and the hash to store for it."""
    plain = prefix + secrets.token_urlsafe(32)
    return plain, hash_secret(plain)


def hash_secret(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def session_is_live(row: BrowserSession, now: datetime) -> bool:
    return (
        row.state == SessionState.ACTIVE
        and now - row.created_at < SESSION_MAX_AGE
        and now - row.last_seen_at < SESSION_MAX_IDLE
    )


def token_is_live(row: Token, now: datetime) -> bool:
    return row.state == TokenState.ACTIVE and (row.expires_at is None or now < row.expires_at)


async def end_sessions(session: AsyncSession, person_id: str, now: datetime) -> int:
    """End every live session of a person (ACC-2). Returns how many ended."""
    SESSION_MACHINE.check(SessionState.ACTIVE, SessionState.ENDED)
    result = await session.execute(
        update(BrowserSession)
        .where(BrowserSession.person_id == person_id, BrowserSession.state == SessionState.ACTIVE)
        .values(state=SessionState.ENDED, ended_at=now)
    )
    return cast("CursorResult[Any]", result).rowcount


async def revoke_tokens(session: AsyncSession, person_id: str, now: datetime) -> int:
    """Revoke every active token of a person (section 7.10)."""
    TOKEN_MACHINE.check(TokenState.ACTIVE, TokenState.REVOKED)
    result = await session.execute(
        update(Token)
        .where(Token.person_id == person_id, Token.state == TokenState.ACTIVE)
        .values(state=TokenState.REVOKED, revoked_at=now)
    )
    return cast("CursorResult[Any]", result).rowcount


class Authenticator:
    """Turns a presented credential into a caller. Surfaces call this and nothing else.

    A session or personal token is a person acting directly. An MCP token is a person's
    client acting for them, and works only on the MCP surface; a person's own credential
    never works there (section 9.2).
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession], clock: Clock = utc_now) -> None:
        self._sessions = sessions
        self._clock = clock

    async def authenticate(self, credential: str | None, *, on_mcp: bool = False) -> Caller:
        if not credential:
            return ANONYMOUS
        now = self._clock()
        digest = hash_secret(credential)
        async with self._sessions() as session, session.begin():
            if credential.startswith(SESSION_PREFIX) and not on_mcp:
                row = await session.scalar(
                    select(BrowserSession).where(BrowserSession.token_hash == digest)
                )
                if row is None or not session_is_live(row, now):
                    raise unauthenticated()
                row.last_seen_at = now
                return await self._person(session, row.person_id, credential_id=row.id)
            kind = TokenKind.MCP if on_mcp else TokenKind.PERSONAL
            prefix = MCP_PREFIX if on_mcp else PERSONAL_PREFIX
            if credential.startswith(prefix):
                token = await session.scalar(
                    select(Token).where(Token.token_hash == digest, Token.kind == kind)
                )
                if token is None or not token_is_live(token, now):
                    raise unauthenticated()
                caller = await self._person(session, token.person_id, credential_id=token.id)
                if not on_mcp:
                    return caller
                return Caller(
                    CallerKind.PERSON,
                    caller.actor_id,
                    role=caller.role,
                    via=f"mcp:{token.name}",
                    mcp_scopes=mcp_scopes.granted(frozenset(str(scope) for scope in token.scopes)),
                    credential_id=token.id,
                )
        raise unauthenticated()

    async def _person(self, session: AsyncSession, person_id: str, *, credential_id: str) -> Caller:
        person = await session.get(Person, person_id)
        if person is None or person.state != PersonState.ACTIVE:
            raise unauthenticated()
        return Caller(
            CallerKind.PERSON,
            person.id,
            role=InstanceRole(person.role),
            credential_id=credential_id,
        )
