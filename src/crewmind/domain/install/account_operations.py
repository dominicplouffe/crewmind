"""Host-local account recovery: the first admin and reset links (IF-4.2, NFR-2).

These run on the server's own host and work when the server is down.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from crewmind.catalog.caller import Authority, InstanceRole
from crewmind.catalog.define import operation
from crewmind.catalog.execute import HOST_ONLY, Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.accounts.model import LinkKind, PersonState
from crewmind.domain.accounts.people import create_invited, issue_link, person_by_email
from crewmind.domain.accounts.people_operations import LinkOutput
from crewmind.storage.models import Person

IF_4_2 = HOST_ONLY


class BootstrapInput(BaseModel):
    email: str = Field(description="The first admin's email address.")
    name: str = Field("Admin", min_length=1, max_length=200, description="Their name.")


class ResetInput(BaseModel):
    email: str = Field(description="The person's email address.")


@operation(
    "install.bootstrap_admin",
    summary="Create the first admin and print their one-time setup link.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.REVERSIBLE,
)
async def bootstrap_admin(context: Context, payload: BootstrapInput) -> LinkOutput:
    """NFR-2, section 7.8: allowed only while the install has no active admin."""
    admins = await context.session.scalar(
        select(func.count())
        .select_from(Person)
        .where(Person.role == InstanceRole.ADMIN, Person.state == PersonState.ACTIVE)
    )
    if admins:
        raise Refusal(
            "admin_exists",
            f"This install already has {admins} active admin(s).",
            rule=IF_4_2.id,
            hint="Ask an admin to invite people, or use `crewmind reset-link`.",
        )
    person = await person_by_email(context.session, payload.email)
    if person is None:
        person = await create_invited(context, payload.email, payload.name, InstanceRole.ADMIN)
    kind = LinkKind.INVITE if person.state == PersonState.INVITED else LinkKind.RESET
    link, expires_at = await issue_link(context, person, kind)
    return LinkOutput(person_id=person.id, link=link, expires_at=expires_at)


@operation(
    "install.reset_link",
    summary="Issue a one-time password-reset link for a person, from the server's host.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.REVERSIBLE,
)
async def reset_link(context: Context, payload: ResetInput) -> LinkOutput:
    """ACC-4, IF-4.2: the way back in when no admin can sign in."""
    person = await person_by_email(context.session, payload.email)
    if person is None:
        raise Refusal(
            "person_not_found",
            f"Nobody on this install has the address {payload.email}.",
            kind=RefusalKind.NOT_FOUND,
        )
    kind = LinkKind.INVITE if person.state == PersonState.INVITED else LinkKind.RESET
    link, expires_at = await issue_link(context, person, kind)
    return LinkOutput(person_id=person.id, link=link, expires_at=expires_at)
