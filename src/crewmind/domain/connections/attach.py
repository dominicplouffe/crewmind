"""Attaching a connection to a project and granting it to roles (CON-4, CON-5)."""

from __future__ import annotations

from sqlalchemy import select

from crewmind.catalog.execute import Context
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.connections import needs, service
from crewmind.domain.connections.model import (
    ALL_ROLES,
    ATTACHED,
    CON_4,
    DETACHED,
    GRANTED,
    Kind,
    Scope,
    check_env_name,
)
from crewmind.storage.models import Connection, Project, ProjectConnection


async def roster_roles(context: Context, project: Project) -> list[str]:
    return [role.slug for role in await needs.roles_on_roster(context.session, project.id)]


async def chosen_roles(
    context: Context, project: Project, item: Connection, roles: list[str] | None
) -> list[str]:
    """CON-4: the roles asked for, checked against the roster; with none asked for, the roles
    that declared a need this item meets; with no such need, the chairman must choose."""
    on_roster = await roster_roles(context, project)
    if roles:
        if ALL_ROLES in roles:
            return [ALL_ROLES]
        unknown = sorted(set(roles) - set(on_roster))
        if unknown:
            raise Refusal(
                "role_not_on_roster",
                f"{', '.join(unknown)} is not a role on this project's roster.",
                rule=CON_4.id,
                hint=f"Roles here: {', '.join(on_roster) or 'none yet'}, or * for every role.",
            )
        return sorted(set(roles))
    declared = await needs.declared(context.session, project)
    wanted: set[str] = set()
    for (kind, name), roles_needing in declared.items():
        if kind == item.kind and name.lower() == item.name_key:
            wanted |= roles_needing
    if not wanted:
        raise Refusal(
            "roles_required",
            f"No role of this project declared a need for {item.name}, so choose who may use it.",
            rule=CON_4.id,
            hint=f"Give --roles with any of: {', '.join(on_roster) or 'none yet'}, or *.",
        )
    return sorted(wanted)


def _check_attachable(context: Context, project: Project, item: Connection) -> None:
    if item.scope == Scope.PROJECT and item.owner_id != project.id:
        raise Refusal(
            "connection_of_another_project",
            f"{item.name} belongs to another project and is used only there.",
            kind=RefusalKind.FORBIDDEN,
            rule=CON_4.id,
            hint="Add it to your own connections to use it in several projects.",
        )
    if item.scope == Scope.PERSON and item.owner_id != context.caller.person_id:
        raise service.not_found(item.name)


async def attach(
    context: Context,
    project: Project,
    item: Connection,
    roles: list[str] | None,
    env_name: str | None,
) -> ProjectConnection:
    _check_attachable(context, project, item)
    existing = await context.session.scalar(
        select(ProjectConnection).where(
            ProjectConnection.project_id == project.id,
            ProjectConnection.connection_id == item.id,
        )
    )
    if existing is not None:
        raise Refusal(
            "already_attached",
            f"{item.name} is already attached to this project.",
            rule=CON_4.id,
            hint="Change who may use it with `connections set-grants`.",
        )
    granted = await chosen_roles(context, project, item, roles)
    env = check_env_name(env_name) if env_name else None
    if env and item.kind == Kind.MCP_SERVER:
        env = None
    await service.check_collisions(context.session, project.id, item, granted, env or item.env_name)
    link = ProjectConnection(
        project_id=project.id,
        connection_id=item.id,
        env_name=env,
        roles=granted,
        attached_by=context.caller.actor_id,
        attached_at=context.now,
        changed_at=context.now,
    )
    context.session.add(link)
    await context.session.flush()
    context.record(
        ATTACHED,
        subject=("connection", item.id),
        project_id=project.id,
        after={"name": item.name, "kind": item.kind, "roles": granted, "env_name": env},
    )
    await service.refresh(context.session, project, context.now, context.caller)
    return link


async def set_grants(
    context: Context, project: Project, link: ProjectConnection, item: Connection, roles: list[str]
) -> None:
    granted = await chosen_roles(context, project, item, roles)
    await service.check_collisions(
        context.session, project.id, item, granted, service.env_of(link, item)
    )
    before = list(link.roles or [])
    link.roles, link.changed_at = granted, context.now
    context.record(
        GRANTED,
        subject=("connection", item.id),
        project_id=project.id,
        before={"roles": before},
        after={"name": item.name, "roles": granted},
    )
    await service.refresh(context.session, project, context.now, context.caller)


async def detach(
    context: Context, project: Project, link: ProjectConnection, item: Connection
) -> None:
    """CON-4: takes effect at each seat's next run; seats that needed it are held."""
    await context.session.delete(link)
    await context.session.flush()
    context.record(
        DETACHED,
        subject=("connection", item.id),
        project_id=project.id,
        before={"roles": list(link.roles or [])},
        after={"name": item.name},
    )
    await service.refresh(context.session, project, context.now, context.caller)


async def link_of(context: Context, project: Project, item: Connection) -> ProjectConnection:
    link = await context.session.scalar(
        select(ProjectConnection).where(
            ProjectConnection.project_id == project.id,
            ProjectConnection.connection_id == item.id,
        )
    )
    if link is None:
        raise Refusal(
            "not_attached",
            f"{item.name} is not attached to this project.",
            kind=RefusalKind.NOT_FOUND,
            rule=CON_4.id,
            hint="Attach it with `connections attach`.",
        )
    return link
