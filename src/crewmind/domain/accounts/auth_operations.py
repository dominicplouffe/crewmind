"""Signing in and out, and setting a password from a link (ACC-1, ACC-2, ACC-4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.secret import OneTimeSecret
from crewmind.domain.accounts.credentials import (
    SESSION_PREFIX,
    end_sessions,
    hash_secret,
    mint_secret,
)
from crewmind.domain.accounts.model import (
    LINK_MACHINE,
    LOGIN_FAILURES_BEFORE_LOCK,
    LOGIN_LOCK,
    PERSON_MACHINE,
    SESSION_MACHINE,
    SESSION_MAX_AGE,
    LinkKind,
    LinkState,
    PersonState,
    SessionState,
)
from crewmind.domain.accounts.passwords import hash_password, verify_password
from crewmind.domain.accounts.people import (
    ACC_1,
    ACC_4,
    LINK_USED,
    PASSWORD_CHANGED,
    PERSON_ACTIVATED,
    normalize_email,
    person_by_email,
    person_or_refuse,
)
from crewmind.storage.events import event_type
from crewmind.storage.models import BrowserSession, Link, LoginAttempts

SESSION_STARTED = event_type("session.started", "A person signed in (ACC-2).")
SESSION_ENDED = event_type("session.ended", "Sessions ended (ACC-2).")


class LoginInput(BaseModel):
    email: str = Field(description="Your email address.")
    password: SecretStr = Field(description="Your password.")


class LoginOutput(BaseModel):
    person_id: str
    name: str
    role: str
    session: OneTimeSecret = Field(description="The session credential. Shown once.")
    expires_at: datetime


class WhoAmI(BaseModel):
    person_id: str
    email: str
    name: str
    role: str
    via: str


class Done(BaseModel):
    done: bool = True


class ChangePasswordInput(BaseModel):
    current_password: SecretStr = Field(description="Your current password.")
    new_password: SecretStr = Field(description="The new password, 12 characters or more.")


class UseLinkInput(BaseModel):
    link: str = Field(description="The invite or reset link you were given.")
    password: SecretStr = Field(description="The password to set, 12 characters or more.")


class UseLinkOutput(BaseModel):
    person_id: str
    email: str


def _login_failed() -> Refusal:
    return Refusal(
        "login_failed",
        "That address and password do not match an active account.",
        kind=RefusalKind.UNAUTHENTICATED,
        hint="Check both, or ask an admin for a reset link.",
    )


async def _count_failure(context: Context, address: str) -> None:
    """Record a failed login in its own transaction, so it survives the refusal (ACC-1)."""
    async with context.sessions() as session, session.begin():
        attempts = await session.get(LoginAttempts, address)
        if attempts is None:
            attempts = LoginAttempts(address=address, failures=0, locked_until=None)
            session.add(attempts)
        attempts.failures += 1
        if attempts.failures >= LOGIN_FAILURES_BEFORE_LOCK:
            attempts.failures = 0
            attempts.locked_until = context.now + LOGIN_LOCK


@operation(
    "auth.login",
    summary="Sign in with an email address and password.",
    authority=Authority.ANYONE,
    reversibility=Reversibility.REVERSIBLE,
)
async def login(context: Context, payload: LoginInput) -> LoginOutput:
    """ACC-1, ACC-2: unknown, deactivated and wrong-password logins get the same answer in
    the same time, and ten failures lock the address for 15 minutes."""
    address = normalize_email(payload.email)
    attempts = await context.session.get(LoginAttempts, address)
    if attempts is not None and attempts.locked_until and context.now < attempts.locked_until:
        raise Refusal(
            "locked_out",
            f"After {LOGIN_FAILURES_BEFORE_LOCK} failed sign-ins this address is locked until "
            f"{attempts.locked_until.isoformat(timespec='seconds')}.",
            rule=ACC_1.id,
            hint="Wait for the lock to lift, then try again.",
        )
    person = await person_by_email(context.session, address)
    usable = person is not None and person.state == PersonState.ACTIVE
    stored_hash = person.password_hash if person is not None and usable else None
    if not verify_password(stored_hash, payload.password.get_secret_value()) or person is None:
        await _count_failure(context, address)
        raise _login_failed()
    if attempts is not None:
        await context.session.delete(attempts)
    plain, digest = mint_secret(SESSION_PREFIX)
    SESSION_MACHINE.check("(new)", SessionState.ACTIVE)
    row = BrowserSession(
        token_hash=digest,
        person_id=person.id,
        state=SessionState.ACTIVE,
        created_at=context.now,
        last_seen_at=context.now,
        ended_at=None,
    )
    context.session.add(row)
    await context.session.flush()
    context.record(
        SESSION_STARTED,
        subject=("session", row.id),
        after={"state": SessionState.ACTIVE, "person": person.id},
    )
    return LoginOutput(
        person_id=person.id,
        name=person.name,
        role=person.role,
        session=plain,
        expires_at=context.now + SESSION_MAX_AGE,
    )


@operation(
    "auth.logout",
    summary="Sign out. Ends the session on the server.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def logout(context: Context, payload: Empty) -> Done:
    """ACC-2, IF-3.7: signing out ends the session server-side."""
    row = await context.session.get(BrowserSession, context.caller.credential_id or "")
    if row is not None and row.state == SessionState.ACTIVE:
        SESSION_MACHINE.check(SessionState.ACTIVE, SessionState.ENDED)
        row.state = SessionState.ENDED
        row.ended_at = context.now
        context.record(
            SESSION_ENDED,
            subject=("session", row.id),
            before={"state": SessionState.ACTIVE},
            after={"state": SessionState.ENDED},
            detail={"cause": "sign-out"},
        )
    return Done()


@operation(
    "auth.whoami",
    summary="Show who you are signed in as.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def whoami(context: Context, payload: Empty) -> WhoAmI:
    person = await person_or_refuse(context.session, context.caller.actor_id)
    return WhoAmI(
        person_id=person.id,
        email=person.email,
        name=person.name,
        role=person.role,
        via=context.caller.via,
    )


@operation(
    "auth.change_password",
    summary="Change your password. Ends all of your sessions.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def change_password(context: Context, payload: ChangePasswordInput) -> Done:
    """ACC-1, ACC-2: a password change ends every session server-side."""
    person = await person_or_refuse(context.session, context.caller.actor_id)
    if not verify_password(person.password_hash, payload.current_password.get_secret_value()):
        raise _login_failed()
    person.password_hash = hash_password(payload.new_password.get_secret_value())
    ended = await end_sessions(context.session, person.id, context.now)
    context.record(PASSWORD_CHANGED, subject=("person", person.id), detail={"cause": "changed"})
    context.record(
        SESSION_ENDED,
        subject=("person", person.id),
        detail={"cause": "password change", "sessions": ended},
    )
    return Done()


@operation(
    "auth.use_link",
    summary="Set a password from an invite or reset link.",
    authority=Authority.ANYONE,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def use_link(context: Context, payload: UseLinkInput) -> UseLinkOutput:
    """ACC-4: a link works once, for 72 hours. Every failure gets the same answer."""
    token = payload.link.strip().rstrip("/").rsplit("/", 1)[-1]
    link = await context.session.scalar(
        select(Link).where(Link.token_hash == hash_secret(token)).with_for_update()
    )
    if link is None or link.state != LinkState.UNUSED or context.now >= link.expires_at:
        raise Refusal(
            "link_invalid",
            "That link is not valid. Links work once, for 72 hours.",
            rule=ACC_4.id,
            hint="Ask an admin for a new link.",
        )
    person = await person_or_refuse(context.session, link.person_id)
    new_hash = hash_password(payload.password.get_secret_value())
    if link.kind == LinkKind.INVITE:
        PERSON_MACHINE.check(person.state, PersonState.ACTIVE)
        before = person.state
        person.state = PersonState.ACTIVE
        context.record(
            PERSON_ACTIVATED,
            subject=("person", person.id),
            before={"state": before},
            after={"state": PersonState.ACTIVE},
        )
    else:
        ended = await end_sessions(context.session, person.id, context.now)
        context.record(
            PASSWORD_CHANGED,
            subject=("person", person.id),
            detail={"cause": "reset link", "sessions_ended": ended},
        )
    person.password_hash = new_hash
    LINK_MACHINE.check(LinkState.UNUSED, LinkState.USED)
    link.state = LinkState.USED
    link.used_at = context.now
    context.record(
        LINK_USED,
        subject=("link", link.id),
        before={"state": LinkState.UNUSED},
        after={"state": LinkState.USED},
    )
    return UseLinkOutput(person_id=person.id, email=person.email)
