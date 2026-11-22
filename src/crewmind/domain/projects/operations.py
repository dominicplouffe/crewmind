"""Project operations: create, read, and the lifecycle (PRJ-1 to PRJ-3, PRJ-10, section 7.1)."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.pagination import PageRequest, fetch_page
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.secret import OneTimeSecret
from crewmind.domain.accounts.credentials import hash_secret, mint_secret
from crewmind.domain.accounts.model import MEMBERSHIP_MACHINE, ProjectRole
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.model import (
    GOAL_MAX_LENGTH,
    LIFTED_BY,
    PRJ_1,
    PRJ_2,
    PRJ_10,
    PROJECT_MACHINE,
    Hold,
    ProjectState,
    ProjectType,
)
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import HoldReason, Membership, Project

MEMBER_ADDED = event_type("member.added", "A person joined a project (7.11).")


class CreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="The project's name.")
    type: ProjectType = Field(description="explore, deliver or operate. It never changes.")
    goal: str = Field(min_length=1, max_length=GOAL_MAX_LENGTH, description="The goal, in prose.")
    timezone: str | None = Field(None, description="IANA timezone. Default: your own.")


class ProjectRef(BaseModel):
    project_id: str = Field(description="The project's id, from `projects list`.")


class HoldInput(ProjectRef):
    until: datetime | None = Field(None, description="When to resume automatically.")
    note: str | None = Field(None, max_length=1000, description="Why it is held.")


class ConfirmDeleteInput(ProjectRef):
    confirmation: str = Field(description="The confirmation code from `projects delete`.")
    name: str = Field(description="The project's name, typed in full.")


class HoldItem(BaseModel):
    reason: str
    since: datetime
    lifts_at: datetime | None
    lifted_by: str
    note: str | None


class ProjectItem(BaseModel):
    project_id: str
    name: str
    type: str
    state: str
    your_role: str | None
    created_at: datetime


class ProjectStatus(ProjectItem):
    goal: str
    holds: list[HoldItem]
    delete_at: datetime | None
    health: list[str] = Field(default=[], description="Findings, each with its fix (NFR-5).")


class ProjectList(BaseModel):
    items: list[ProjectItem]
    next: str | None = None


class DeleteRequested(BaseModel):
    project_id: str
    name: str
    confirmation: OneTimeSecret = Field(description="Give this to `projects confirm-delete`.")
    purged_after_days: float


def _hold_item(row: HoldReason) -> HoldItem:
    return HoldItem(
        reason=row.reason,
        since=row.added_at,
        lifts_at=row.lift_at,
        lifted_by=LIFTED_BY[Hold(row.reason)],
        note=row.note,
    )


async def _status(context: Context) -> ProjectStatus:
    view = view_of(context)
    project = view.project
    holds = await lifecycle.active_holds(context.session, project.id)
    return ProjectStatus(
        project_id=project.id,
        name=project.name,
        type=project.type,
        state=project.state,
        your_role=view.role,
        created_at=project.created_at,
        goal=project.goal,
        holds=[_hold_item(row) for row in holds],
        delete_at=project.delete_at,
        health=_health(project),
    )


OLDER_DOCTRINE = (
    "This project was drafted under an earlier version of the Founder's doctrine. Nothing "
    "in it was changed. Rehearse it with `crewmind projects rehearse` to see what the "
    "current doctrine and rules make of it."
)


def _health(project: Project) -> list[str]:
    """FND-14: a later doctrine fix shows as a finding on an older project. It never
    rewrites the project and never blocks it."""
    from crewmind.domain.founder.drafting import doctrine_fingerprint

    drafted_under = project.doctrine_fingerprint
    if drafted_under is not None and drafted_under != doctrine_fingerprint():
        return [OLDER_DOCTRINE]
    return []


@operation(
    "projects.create",
    summary="Create a project in draft. You become its chairman.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def create(context: Context, payload: CreateInput) -> ProjectItem:
    """ACC-5, section 7.11: any active person may create a project and becomes its chairman."""
    services = services_of(context)
    person = Subject(Scope.PERSON, context.caller.actor_id)
    timezone = payload.timezone or await services.settings.get(
        context.session, person, "person.timezone"
    )
    PROJECT_MACHINE.check("(new)", ProjectState.DRAFT)
    project = Project(
        name=payload.name,
        type=payload.type,
        goal=payload.goal,
        state=ProjectState.DRAFT,
        prior_state=None,
        delete_at=None,
        delete_confirmation_hash=None,
        registry_version=services.registry.version,
        created_by=context.caller.actor_id,
        created_at=context.now,
    )
    context.session.add(project)
    await context.session.flush()
    context.record(
        lifecycle.PROJECT_CREATED,
        subject=("project", project.id),
        project_id=project.id,
        after={"state": ProjectState.DRAFT, "name": project.name, "type": project.type},
    )
    MEMBERSHIP_MACHINE.check("(new)", ProjectRole.CHAIRMAN)
    context.session.add(
        Membership(
            project_id=project.id,
            person_id=context.caller.actor_id,
            role=ProjectRole.CHAIRMAN,
            state="member",
            added_at=context.now,
            removed_at=None,
        )
    )
    context.record(
        MEMBER_ADDED,
        subject=("person", context.caller.actor_id),
        project_id=project.id,
        after={"role": ProjectRole.CHAIRMAN},
    )
    for hook in lifecycle.created_hooks:
        await hook(context.session, project, context.now, context.caller)
    await services.settings.change(
        context.session,
        Subject(Scope.PROJECT, project.id, project.type),
        {"project.timezone": timezone},
        reason="Set when the project was created.",
        caller=context.caller,
        now=context.now,
    )
    return ProjectItem(
        project_id=project.id,
        name=project.name,
        type=project.type,
        state=project.state,
        your_role=ProjectRole.CHAIRMAN,
        created_at=project.created_at,
    )


@operation(
    "projects.list",
    summary="List the projects you can see.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_projects(context: Context, payload: PageRequest) -> ProjectList:
    """INV-5: members see their projects. Admins read every project (section 3)."""
    mine = (
        select(Membership.project_id, Membership.role)
        .where(Membership.person_id == context.caller.actor_id, Membership.state == "member")
        .subquery()
    )
    statement = select(Project)
    if not context.caller.is_admin:
        statement = statement.join(mine, mine.c.project_id == Project.id)
    rows, cursor = await fetch_page(
        context.session, statement, payload, key=Project.id, at=Project.created_at
    )
    roles = dict((await context.session.execute(select(mine.c.project_id, mine.c.role))).all())
    return ProjectList(
        items=[
            ProjectItem(
                project_id=row.id,
                name=row.name,
                type=row.type,
                state=row.state,
                your_role=roles.get(row.id),
                created_at=row.created_at,
            )
            for row in rows
        ],
        next=cursor,
    )


@operation(
    "projects.status",
    summary="Show a project: its state, and every hold with what lifts it.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
    slash_command="/status",
)
async def status(context: Context, payload: ProjectRef) -> ProjectStatus:
    return await _status(context)


@operation(
    "projects.start",
    summary="Start a draft project.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def start(context: Context, payload: ProjectRef) -> ProjectStatus:
    """PRJ-1: start is refused unless every start check passes."""
    project = view_of(context).project
    if project.state != ProjectState.DRAFT:
        raise Refusal(
            "not_draft",
            f"The project is {project.state}; only a draft project can be started.",
            rule=PRJ_1.id,
            hint="Resume a held project, or reopen a completed one.",
        )
    for check in lifecycle.start_checks:
        await check(context.session, project, context.now)
    lifecycle.move(
        context.session, project, ProjectState.RUNNING, caller=context.caller, now=context.now
    )
    for hook in lifecycle.started_hooks:
        await hook(context.session, project, context.now)
    return await _status(context)


@operation(
    "projects.hold",
    summary="Hold a project, optionally until a time. Work stops; you can still chat.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/hold",
)
async def hold(context: Context, payload: HoldInput) -> ProjectStatus:
    """PRJ-2: a hold is the chairman's own hold reason, with an optional lift time."""
    project = view_of(context).project
    if payload.until is not None and payload.until <= context.now:
        raise Refusal(
            "lift_time_past",
            f"The resume time {payload.until.isoformat()} is not in the future.",
            rule=PRJ_2.id,
            hint="Give a later time, or none.",
        )
    added = await lifecycle.add_hold(
        context.session,
        project,
        Hold.CHAIRMAN,
        caller=context.caller,
        now=context.now,
        lift_at=payload.until,
        note=payload.note or "Held by the chairman.",
    )
    if not added:
        raise Refusal(
            "already_held",
            "The chairman's hold is already on this project.",
            rule=PRJ_2.id,
            hint="Resume it first to change the hold.",
        )
    return await _status(context)


@operation(
    "projects.resume",
    summary="Resume a held or paused project.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/resume",
)
async def resume(context: Context, payload: ProjectRef) -> ProjectStatus:
    """PRJ-2: refused while the budget wall holds, with the arithmetic (GOV-9)."""
    await lifecycle.resume(
        context.session, view_of(context).project, caller=context.caller, now=context.now
    )
    return await _status(context)


@operation(
    "projects.stop",
    summary="Stop a project for good. This cannot be undone.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.IRREVERSIBLE,
    slash_command="/stop",
)
async def stop(context: Context, payload: ProjectRef) -> ProjectStatus:
    """PRJ-3: stop is terminal."""
    project = view_of(context).project
    lifecycle.move(
        context.session, project, ProjectState.STOPPED, caller=context.caller, now=context.now
    )
    await lifecycle.clear_holds(context.session, project, context.now)
    for hook in lifecycle.stop_hooks:
        await hook(context.session, project, context.now)
    return await _status(context)


@operation(
    "projects.delete",
    summary="First step of deleting a project. Returns a confirmation code.",
    authority=Authority.PROJECT_CHAIRMAN_ONLY,
    reversibility=Reversibility.REVERSIBLE,
)
async def request_delete(context: Context, payload: ProjectRef) -> DeleteRequested:
    """PRJ-10: deleting needs two steps, and only the chairman may take them."""
    project = view_of(context).project
    PROJECT_MACHINE.check(project.state, ProjectState.DELETING)
    plain, digest = mint_secret("")
    project.delete_confirmation_hash = digest
    grace = await services_of(context).settings.get(
        context.session, Subject(Scope.INSTALL, INSTALL_SUBJECT), "delete.grace"
    )
    context.record(
        lifecycle.DELETE_REQUESTED, subject=("project", project.id), project_id=project.id
    )
    return DeleteRequested(
        project_id=project.id,
        name=project.name,
        confirmation=plain,
        purged_after_days=grace / 86_400,
    )


@operation(
    "projects.confirm_delete",
    summary="Second step of deleting: everything is purged after the grace period.",
    authority=Authority.PROJECT_CHAIRMAN_ONLY,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def confirm_delete(context: Context, payload: ConfirmDeleteInput) -> ProjectStatus:
    """PRJ-10: needs the code from the first step and the project's name typed in full."""
    project = view_of(context).project
    PROJECT_MACHINE.check(project.state, ProjectState.DELETING)
    confirmed = (
        project.delete_confirmation_hash is not None
        and hash_secret(payload.confirmation) == project.delete_confirmation_hash
        and payload.name == project.name
    )
    if not confirmed:
        raise Refusal(
            "delete_not_confirmed",
            "Deleting needs the confirmation code from `projects delete` and the project's "
            "exact name.",
            rule=PRJ_10.id,
            hint="Run `projects delete` first, then confirm with its code and the name.",
        )
    grace = await services_of(context).settings.get(
        context.session, Subject(Scope.INSTALL, INSTALL_SUBJECT), "delete.grace"
    )
    purge_at = context.now + timedelta(seconds=grace)
    project.prior_state = project.state
    project.delete_at = purge_at
    project.delete_confirmation_hash = None
    lifecycle.move(
        context.session,
        project,
        ProjectState.DELETING,
        caller=context.caller,
        now=context.now,
        detail={"purge_at": purge_at.isoformat()},
    )
    await lifecycle.clear_holds(context.session, project, context.now)
    return await _status(context)


@operation(
    "projects.cancel_delete",
    summary="Cancel a deletion during its grace period.",
    authority=Authority.PROJECT_CHAIRMAN_ONLY,
    reversibility=Reversibility.REVERSIBLE,
)
async def cancel_delete(context: Context, payload: ProjectRef) -> ProjectStatus:
    """PRJ-10, section 7.1: a deleting project returns to its prior state."""
    project = view_of(context).project
    if project.state != ProjectState.DELETING or project.prior_state is None:
        raise Refusal(
            "not_deleting",
            f"The project is {project.state}, not being deleted.",
            rule=PROJECT_MACHINE.rule_id,
            hint="Only a deletion in its grace period can be cancelled.",
        )
    lifecycle.move(
        context.session,
        project,
        ProjectState(project.prior_state),
        caller=context.caller,
        now=context.now,
    )
    project.prior_state = None
    project.delete_at = None
    return await _status(context)
