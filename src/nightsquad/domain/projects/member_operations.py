"""Project membership: who is on a project and in which role (ACC-5, section 7.11)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import PERSON_AND_MCP, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.accounts.model import (
    MEMBERSHIP_MACHINE,
    REMOVED,
    PersonState,
    ProjectRole,
)
from nightsquad.domain.accounts.people import ACC_5, person_by_email, person_or_refuse
from nightsquad.domain.projects.access import project_not_found, view_of
from nightsquad.domain.projects.operations import MEMBER_ADDED, ProjectRef
from nightsquad.storage.events import event_type
from nightsquad.storage.models import Membership, Person, Project

MEMBER_ROLE_CHANGED = event_type("member.role_changed", "A member's project role changed.")
MEMBER_REMOVED = event_type("member.removed", "A member was removed from a project.")
CHAIR_HANDED_ON = event_type("member.chair_handed_on", "The chair passed to another person.")

AssignableRole = Literal[ProjectRole.CO_CHAIR, ProjectRole.OBSERVER]


class AddMemberInput(ProjectRef):
    email: str = Field(description="The email address of a person on this install.")
    role: AssignableRole = Field(description="co-chair or observer.")


class MemberRef(ProjectRef):
    person_id: str = Field(description="The member's person id, from `members list`.")


class SetMemberRoleInput(MemberRef):
    role: AssignableRole = Field(description="co-chair or observer.")


class BreakGlassInput(MemberRef):
    reason: str = Field(min_length=10, description="Why the chair is being handed on.")


class MemberItem(BaseModel):
    person_id: str
    name: str
    email: str
    role: str
    since: datetime


class MemberList(BaseModel):
    items: list[MemberItem]


async def _members(session: AsyncSession, project_id: str) -> MemberList:
    rows = await session.execute(
        select(Membership, Person)
        .join(Person, Person.id == Membership.person_id)
        .where(Membership.project_id == project_id, Membership.state == "member")
        .order_by(Membership.added_at, Person.email)
    )
    return MemberList(
        items=[
            MemberItem(
                person_id=person.id,
                name=person.name,
                email=person.email,
                role=membership.role,
                since=membership.added_at,
            )
            for membership, person in rows.all()
        ]
    )


async def _membership(session: AsyncSession, project_id: str, person_id: str) -> Membership | None:
    return await session.scalar(
        select(Membership).where(
            Membership.project_id == project_id,
            Membership.person_id == person_id,
            Membership.state == "member",
        )
    )


async def _member_or_refuse(session: AsyncSession, project_id: str, person_id: str) -> Membership:
    membership = await _membership(session, project_id, person_id)
    if membership is None:
        raise Refusal(
            "member_not_found",
            "That person is not a member of this project.",
            kind=RefusalKind.NOT_FOUND,
        )
    return membership


async def _join(context: Context, project_id: str, person: Person, role: ProjectRole) -> None:
    if person.state != PersonState.ACTIVE:
        raise Refusal(
            "person_not_active",
            f"{person.email} is {person.state}; only an active person can join a project.",
            rule=ACC_5.id,
            hint="They must accept their invite first.",
        )
    MEMBERSHIP_MACHINE.check("(new)", role)
    context.session.add(
        Membership(
            project_id=project_id,
            person_id=person.id,
            role=role,
            state="member",
            added_at=context.now,
            removed_at=None,
        )
    )
    await context.session.flush()
    context.record(
        MEMBER_ADDED, subject=("person", person.id), project_id=project_id, after={"role": role}
    )


async def _hand_on(context: Context, project: Project, target: Membership, cause: str) -> None:
    """Section 7.11: the old chairman becomes a co-chair and the new one takes the chair,
    in the same transaction."""
    chairman = await context.session.scalar(
        select(Membership).where(
            Membership.project_id == project.id,
            Membership.role == ProjectRole.CHAIRMAN,
            Membership.state == "member",
        )
    )
    assert chairman is not None
    if chairman.id == target.id:
        raise Refusal("already_chairman", "That person already chairs the project.", rule=ACC_5.id)
    MEMBERSHIP_MACHINE.check(ProjectRole.CHAIRMAN, ProjectRole.CO_CHAIR)
    MEMBERSHIP_MACHINE.check(target.role, ProjectRole.CHAIRMAN)
    before = target.role
    chairman.role = ProjectRole.CO_CHAIR
    await context.session.flush()
    target.role = ProjectRole.CHAIRMAN
    context.record(
        CHAIR_HANDED_ON,
        subject=("person", target.person_id),
        project_id=project.id,
        before={"chairman": chairman.person_id, "role": before},
        after={"chairman": target.person_id, "previous_chairman_role": ProjectRole.CO_CHAIR},
        detail={"cause": cause},
    )


@operation(
    "members.list",
    summary="List a project's members and their roles.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_members(context: Context, payload: ProjectRef) -> MemberList:
    return await _members(context.session, payload.project_id)


@operation(
    "members.add",
    summary="Add a person to a project as a co-chair or an observer.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def add_member(context: Context, payload: AddMemberInput) -> MemberList:
    person = await person_by_email(context.session, payload.email)
    if person is None:
        raise Refusal(
            "person_not_found",
            f"Nobody on this install has the address {payload.email}.",
            kind=RefusalKind.NOT_FOUND,
            hint="Ask an admin to invite them first.",
        )
    if await _membership(context.session, payload.project_id, person.id) is not None:
        raise Refusal(
            "already_member",
            f"{person.email} is already a member of this project.",
            rule=ACC_5.id,
            hint="Change their role instead.",
        )
    await _join(context, payload.project_id, person, ProjectRole(payload.role))
    return await _members(context.session, payload.project_id)


@operation(
    "members.set_role",
    summary="Change a member between co-chair and observer.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_member_role(context: Context, payload: SetMemberRoleInput) -> MemberList:
    membership = await _member_or_refuse(context.session, payload.project_id, payload.person_id)
    if membership.role != payload.role:
        MEMBERSHIP_MACHINE.check(membership.role, payload.role)
        before = membership.role
        membership.role = payload.role
        context.record(
            MEMBER_ROLE_CHANGED,
            subject=("person", membership.person_id),
            project_id=payload.project_id,
            before={"role": before},
            after={"role": payload.role},
        )
    return await _members(context.session, payload.project_id)


@operation(
    "members.remove",
    summary="Remove a member from a project. It takes effect on their next request.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def remove_member(context: Context, payload: MemberRef) -> MemberList:
    """ACC-5, section 7.11: the chairman cannot be removed, only replaced by a hand-on."""
    membership = await _member_or_refuse(context.session, payload.project_id, payload.person_id)
    MEMBERSHIP_MACHINE.check(membership.role, REMOVED)
    before = membership.role
    membership.state = REMOVED
    membership.removed_at = context.now
    context.record(
        MEMBER_REMOVED,
        subject=("person", membership.person_id),
        project_id=payload.project_id,
        before={"role": before},
        after={"role": REMOVED},
    )
    return await _members(context.session, payload.project_id)


@operation(
    "members.hand_on_chair",
    summary="Hand the chair to another member. You become a co-chair.",
    authority=Authority.PROJECT_CHAIRMAN_ONLY,
    reversibility=Reversibility.REVERSIBLE,
)
async def hand_on_chair(context: Context, payload: MemberRef) -> MemberList:
    project = view_of(context).project
    target = await _member_or_refuse(context.session, project.id, payload.person_id)
    await _hand_on(context, project, target, "hand-on by the chairman")
    return await _members(context.session, project.id)


@operation(
    "members.break_glass_hand_on",
    summary="Admin emergency: hand a project's chair to another person. Recorded as break-glass.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def break_glass_hand_on(context: Context, payload: BreakGlassInput) -> MemberList:
    """Section 3, ACC-5: an admin may hand a chair on in an emergency. A person who is not
    yet a member joins as a co-chair first."""
    project = await context.session.get(Project, payload.project_id)
    if project is None:
        raise project_not_found()
    person = await person_or_refuse(context.session, payload.person_id)
    target = await _membership(context.session, project.id, person.id)
    if target is None:
        await _join(context, project.id, person, ProjectRole.CO_CHAIR)
        target = await _member_or_refuse(context.session, project.id, person.id)
    await _hand_on(context, project, target, f"break-glass by an admin: {payload.reason}")
    return await _members(context.session, project.id)
