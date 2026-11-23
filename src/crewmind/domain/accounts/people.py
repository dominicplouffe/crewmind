"""People and single-use links: shared steps used by the account operations (ACC-1, ACC-4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.execute import Context
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.accounts.credentials import LINK_PREFIX, mint_secret
from crewmind.domain.accounts.model import (
    LINK_LIFETIME,
    LINK_MACHINE,
    PERSON_MACHINE,
    LinkKind,
    LinkState,
    PersonState,
)
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import Link, Person

PERSON_INVITED = event_type("person.invited", "A person was invited (ACC-4).")
PERSON_ACTIVATED = event_type("person.activated", "A person set a password or was reactivated.")
PERSON_DEACTIVATED = event_type("person.deactivated", "A person was deactivated.")
PERSON_ROLE_CHANGED = event_type("person.role_changed", "A person's instance role changed.")
PASSWORD_CHANGED = event_type("person.password_changed", "A person's password changed.")
PERSON_RENAMED = event_type("person.renamed", "A person changed the name they are shown by.")
LINK_ISSUED = event_type("link.issued", "A single-use link was issued (ACC-4).")
LINK_USED = event_type("link.used", "A single-use link was used (ACC-4).")
LINK_EXPIRED = event_type("link.expired", "A single-use link expired unused (ACC-4).")

ACC_1 = rules.register(Rule("ACC-1", "Passwords are long, and repeated failures lock an address."))
ACC_2 = rules.register(
    Rule("ACC-2", "Sessions end at sign-out, password change, age and idleness.")
)
ACC_3 = rules.register(Rule("ACC-3", "Tokens are named, expire, and are stored only as hashes."))
ACC_4 = rules.register(Rule("ACC-4", "Invite and reset links work once, for 72 hours."))
ACC_5 = rules.register(Rule("ACC-5", "Instance roles and project membership decide who may act."))
ACC_8 = rules.register(Rule("ACC-8", "A person sets only their own name, and it is never empty."))


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def person_by_email(session: AsyncSession, email: str) -> Person | None:
    return await session.scalar(select(Person).where(Person.email == normalize_email(email)))


async def person_or_refuse(session: AsyncSession, person_id: str) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise Refusal(
            "person_not_found", "There is no person with that id.", kind=RefusalKind.NOT_FOUND
        )
    return person


async def create_invited(context: Context, email: str, name: str, role: str) -> Person:
    """Create a person in the invited state (section 7.8)."""
    email = normalize_email(email)
    if "@" not in email:
        raise Refusal(
            "email_invalid", f"{email!r} is not an email address.", kind=RefusalKind.INVALID
        )
    if await person_by_email(context.session, email) is not None:
        raise Refusal(
            "person_exists",
            f"There is already a person with the address {email}.",
            rule=ACC_5.id,
            hint="Reactivate them, or issue a reset link.",
        )
    PERSON_MACHINE.check("(new)", PersonState.INVITED)
    person = Person(
        email=email,
        name=name,
        role=role,
        state=PersonState.INVITED,
        password_hash=None,
        created_at=context.now,
    )
    context.session.add(person)
    await context.session.flush()
    context.record(
        PERSON_INVITED,
        subject=("person", person.id),
        after={"state": PersonState.INVITED, "role": role, "email": email},
    )
    return person


async def issue_link(context: Context, person: Person, kind: LinkKind) -> tuple[str, datetime]:
    """Issue a single-use link (section 7.9). Returns the link, shown once, and its expiry."""
    plain, digest = mint_secret(LINK_PREFIX)
    LINK_MACHINE.check("(new)", LinkState.UNUSED)
    expires_at = context.now + LINK_LIFETIME
    link = Link(
        token_hash=digest,
        kind=kind,
        person_id=person.id,
        state=LinkState.UNUSED,
        created_at=context.now,
        expires_at=expires_at,
        used_at=None,
    )
    context.session.add(link)
    await context.session.flush()
    context.record(
        LINK_ISSUED,
        subject=("link", link.id),
        after={"state": LinkState.UNUSED, "kind": kind, "person": person.id},
    )
    return f"{services_of(context).base_url}/accept/{plain}", expires_at
