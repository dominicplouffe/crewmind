"""Managing people: invite, list, roles, deactivate, reset links (ACC-4, ACC-5, section 7.8)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority, InstanceRole
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.pagination import PageRequest, fetch_page
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.secret import OneTimeSecret
from crewmind.domain.accounts.credentials import end_sessions, revoke_tokens
from crewmind.domain.accounts.model import PERSON_MACHINE, LinkKind, PersonState, ProjectRole
from crewmind.domain.accounts.people import (
    ACC_5,
    PERSON_ACTIVATED,
    PERSON_DEACTIVATED,
    PERSON_ROLE_CHANGED,
    create_invited,
    issue_link,
    person_or_refuse,
)
from crewmind.storage.models import Membership, Person, Project


class InviteInput(BaseModel):
    email: str = Field(description="The person's email address.")
    name: str = Field(min_length=1, max_length=200, description="Their name.")
    role: InstanceRole = Field(InstanceRole.MEMBER, description="admin or member.")


class LinkOutput(BaseModel):
    person_id: str
    link: OneTimeSecret = Field(description="The single-use link. Shown once; pass it on.")
    expires_at: datetime


class PersonItem(BaseModel):
    person_id: str
    email: str
    name: str
    role: str
    state: str
    created_at: datetime


class PeopleList(BaseModel):
    items: list[PersonItem]
    next: str | None = None


class PersonRef(BaseModel):
    person_id: str = Field(description="The person's id, from `people list`.")


class SetRoleInput(PersonRef):
    role: InstanceRole = Field(description="admin or member.")


def _item(person: Person) -> PersonItem:
    return PersonItem(
        person_id=person.id,
        email=person.email,
        name=person.name,
        role=person.role,
        state=person.state,
        created_at=person.created_at,
    )


@operation(
    "people.invite",
    summary="Invite a person. Returns a one-time setup link to pass on.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def invite(context: Context, payload: InviteInput) -> LinkOutput:
    person = await create_invited(context, payload.email, payload.name, payload.role)
    link, expires_at = await issue_link(context, person, LinkKind.INVITE)
    return LinkOutput(person_id=person.id, link=link, expires_at=expires_at)


@operation(
    "people.list",
    summary="List the people on this install.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.READ,
)
async def list_people(context: Context, payload: PageRequest) -> PeopleList:
    rows, cursor = await fetch_page(
        context.session, select(Person), payload, key=Person.id, at=Person.created_at
    )
    return PeopleList(items=[_item(row) for row in rows], next=cursor)


@operation(
    "people.set_role",
    summary="Promote a person to admin or demote them to member.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_role(context: Context, payload: SetRoleInput) -> PersonItem:
    person = await person_or_refuse(context.session, payload.person_id)
    before = person.role
    if before != payload.role:
        person.role = payload.role
        context.record(
            PERSON_ROLE_CHANGED,
            subject=("person", person.id),
            before={"role": before},
            after={"role": payload.role},
        )
    return _item(person)


@operation(
    "people.deactivate",
    summary="Deactivate a person. Ends their sessions and revokes their tokens.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def deactivate(context: Context, payload: PersonRef) -> PersonItem:
    """Section 7.8, ACC-5: refused while the person chairs a project."""
    person = await person_or_refuse(context.session, payload.person_id)
    PERSON_MACHINE.check(person.state, PersonState.DEACTIVATED)
    chaired = list(
        await context.session.scalars(
            select(Project.name)
            .join(Membership, Membership.project_id == Project.id)
            .where(
                Membership.person_id == person.id,
                Membership.role == ProjectRole.CHAIRMAN,
                Membership.state == "member",
            )
            .order_by(Project.name)
        )
    )
    if chaired:
        raise Refusal(
            "chairs_projects",
            f"{person.name} chairs {len(chaired)} project(s): {', '.join(chaired)}. A project "
            "must always have a chairman.",
            rule=ACC_5.id,
            hint="Hand each chair on first, then deactivate.",
        )
    person.state = PersonState.DEACTIVATED
    sessions = await end_sessions(context.session, person.id, context.now)
    tokens = await revoke_tokens(context.session, person.id, context.now)
    context.record(
        PERSON_DEACTIVATED,
        subject=("person", person.id),
        before={"state": PersonState.ACTIVE},
        after={"state": PersonState.DEACTIVATED},
        detail={"sessions_ended": sessions, "tokens_revoked": tokens},
    )
    return _item(person)


@operation(
    "people.reactivate",
    summary="Reactivate a deactivated person.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def reactivate(context: Context, payload: PersonRef) -> PersonItem:
    person = await person_or_refuse(context.session, payload.person_id)
    if person.state != PersonState.DEACTIVATED:
        raise Refusal(
            "not_deactivated",
            f"{person.name} is {person.state}, not deactivated (section 7.8).",
            rule=PERSON_MACHINE.rule_id,
            hint="Only a deactivated person can be reactivated.",
        )
    PERSON_MACHINE.check(person.state, PersonState.ACTIVE)
    person.state = PersonState.ACTIVE
    context.record(
        PERSON_ACTIVATED,
        subject=("person", person.id),
        before={"state": PersonState.DEACTIVATED},
        after={"state": PersonState.ACTIVE},
    )
    return _item(person)


@operation(
    "people.reset_link",
    summary="Issue a one-time password-reset link for a person.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def reset_link(context: Context, payload: PersonRef) -> LinkOutput:
    """ACC-4: until outbound mail exists, an admin issues reset links and passes them on."""
    person = await person_or_refuse(context.session, payload.person_id)
    kind = LinkKind.INVITE if person.state == PersonState.INVITED else LinkKind.RESET
    link, expires_at = await issue_link(context, person, kind)
    return LinkOutput(person_id=person.id, link=link, expires_at=expires_at)
