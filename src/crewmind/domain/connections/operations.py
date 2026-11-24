"""Operations on what a project has and needs: readiness, attaching, grants, marking a need
done and the project's view of its connections (CON-4, CON-5, CON-14, PRJ-1)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.connections import attach, holds, needs, service
from crewmind.domain.connections.model import Scope
from crewmind.domain.connections.views import ConnectionView, item_view
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.storage.models import Connection, Project, ProjectNeed


class NeedRef(BaseModel):
    kind: str = Field(description="secret, variable or mcp_server.")
    name: str = Field(description="What the need is called, such as wordpress.")


class BlockerItem(BaseModel):
    text: str = Field(description="What is missing, or why a seat cannot run, in plain words.")
    seats: list[str] = Field(description="The names of the agents who would wait for it.")
    need: NeedRef | None = Field(
        default=None,
        description="The need that is missing, to mark it done once it is added; none when "
        "a seat cannot run for another reason.",
    )


class Readiness(BaseModel):
    ready: bool = Field(description="Every agent could work if the project started now.")
    waiting: list[BlockerItem] = Field(
        description="What would hold agents, and who. Starting without it holds exactly them."
    )


@operation(
    "projects.readiness",
    summary="Show what the crew would wait for if the project started now, and who.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def readiness(context: Context, payload: ProjectRef) -> Readiness:
    """CON-5, PRJ-1: the start check's findings, read without starting or changing anything."""
    project = view_of(context).project
    found = await holds.blockers(context.session, project, context.now, context.caller, keep=False)
    return Readiness(
        ready=not found,
        waiting=[
            BlockerItem(
                text=item.text,
                seats=item.seats,
                need=NeedRef(kind=item.need[0], name=item.need[1]) if item.need else None,
            )
            for item in found
        ],
    )


class AttachInput(ProjectRef):
    connection: str = Field(description="The connection's name or id.")
    roles: list[str] | None = Field(
        default=None,
        description="The roles that may use it, or *. By default, the roles that need it.",
    )
    env_name: str | None = Field(
        default=None, description="A variable or file name for this project only."
    )


class GrantsInput(ProjectRef):
    connection: str = Field(description="The connection's name or id.")
    roles: list[str] = Field(description="Every role that may use it, or *.")


class DetachInput(ProjectRef):
    connection: str = Field(description="The connection's name or id.")


class Attached(BaseModel):
    item: ConnectionView
    roles: list[str] = Field(description="The roles granted, or * for every role.")
    env_name: str | None = Field(description="The variable or file name in this project.")


class NeedView(BaseModel):
    kind: str
    name: str
    roles: list[str] = Field(description="The roles that need it.")
    state: str = Field(
        description="open (missing), done (the chairman marked it done), met (a connection of "
        "its name is attached) or waived (started without it)."
    )
    seats: list[str] = Field(description="The agents who wait while it is missing.")


class RoleOption(BaseModel):
    slug: str
    name: str


class ProjectConnections(BaseModel):
    attached: list[Attached]
    available: list[ConnectionView] = Field(description="What you could attach here.")
    needs: list[NeedView]
    roles: list[RoleOption] = Field(description="The roles on the roster, for grants.")


async def _project(context: Context) -> Project:
    project: Project = view_of(context).project
    return project


@operation(
    "connections.attach",
    summary="Attach a secret, variable or MCP server to a project and choose who may use it.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def attach_connection(context: Context, payload: AttachInput) -> Attached:
    """CON-4, CON-5: granted by default to the roles that declared the need; a collision is
    refused; seats waiting for it go back to work."""
    project = await _project(context)
    item = await service.find(context.session, context.caller, payload.connection, project.id)
    link = await attach.attach(context, project, item, payload.roles, payload.env_name)
    return Attached(
        item=await item_view(context.session, context.caller, item),
        roles=list(link.roles),
        env_name=service.env_of(link, item),
    )


@operation(
    "connections.set_grants",
    summary="Set the roles of a project that may use an attached connection.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_grants(context: Context, payload: GrantsInput) -> Attached:
    """CON-4: takes effect at each seat's next run; seats whose need is no longer met are
    held."""
    project = await _project(context)
    item = await service.find(context.session, context.caller, payload.connection, project.id)
    link = await attach.link_of(context, project, item)
    await attach.set_grants(context, project, link, item, payload.roles)
    return Attached(
        item=await item_view(context.session, context.caller, item),
        roles=list(link.roles),
        env_name=service.env_of(link, item),
    )


@operation(
    "connections.detach",
    summary="Detach a connection from a project. Agents that needed it wait.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def detach_connection(context: Context, payload: DetachInput) -> ConnectionView:
    """CON-4, CON-14: takes effect at each seat's next run; seats that needed it are held."""
    project = await _project(context)
    item = await service.find(context.session, context.caller, payload.connection, project.id)
    link = await attach.link_of(context, project, item)
    await attach.detach(context, project, link, item)
    return await item_view(context.session, context.caller, item)


@operation(
    "connections.for_project",
    summary="Show what a project has, what its crew needs, and what could be attached.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def for_project(context: Context, payload: ProjectRef) -> ProjectConnections:
    """CON-4, CON-5, CON-14, CON-15: one read for the project's Connections tab. Nothing is
    written."""
    project = await _project(context)
    session = context.session
    links = await service.attached(session, project.id)
    attached_ids = {item.id for _, item in links}
    attached_views = [
        Attached(
            item=await item_view(session, context.caller, item),
            roles=[str(role) for role in link.roles or []],
            env_name=service.env_of(link, item),
        )
        for link, item in links
    ]
    available: list[ConnectionView] = []
    rows = await session.scalars(
        select(Connection)
        .where(Connection.state.in_(service.LIVE))
        .order_by(Connection.scope, Connection.name_key)
    )
    for row in rows:
        if row.id in attached_ids:
            continue
        mine = row.scope == Scope.PERSON and row.owner_id == context.caller.person_id
        here = row.scope == Scope.PROJECT and row.owner_id == project.id
        if row.scope == Scope.INSTALL or mine or here:
            available.append(await item_view(session, context.caller, row))
    seats = await holds.roster_seats(session, project.id)
    need_views = [
        NeedView(
            kind=need.kind,
            name=need.name,
            roles=[str(role) for role in need.roles or []],
            state=need.state,
            seats=[seat.display_name for seat, role in seats if role.slug in (need.roles or [])]
            if need.state in needs.UNMET
            else [],
        )
        for need in await needs.preview(session, project)
    ]
    roster = await needs.roles_on_roster(session, project.id)
    return ProjectConnections(
        attached=attached_views,
        available=available,
        needs=need_views,
        roles=[RoleOption(slug=role.slug, name=role.name) for role in roster],
    )


class NeedInput(ProjectRef):
    need: str = Field(description="What the need is called, such as wordpress.")
    kind: str | None = Field(
        default=None, description="secret, variable or mcp_server, when two needs share a name."
    )


class NeedChanged(BaseModel):
    kind: str
    name: str
    state: str = Field(description="The need's state now.")


async def _need(context: Context, project: Project, payload: NeedInput) -> ProjectNeed:
    current = await needs.sync(context.session, project, context.now, context.caller)
    found = [
        need
        for need in current
        if need.name.lower() == payload.need.lower()
        and (payload.kind is None or need.kind == payload.kind)
        and need.state != needs.NeedState.DROPPED
    ]
    if len(found) == 1:
        return found[0]
    if found:
        raise Refusal(
            "need_ambiguous",
            f"More than one need is called {payload.need}.",
            rule=needs.CON_5.id,
            hint="Say which kind: secret, variable or mcp_server.",
        )
    listed = ", ".join(
        sorted({need.name for need in current if need.state != needs.NeedState.DROPPED})
    )
    raise Refusal(
        "need_not_found",
        f"No role of this project needs {payload.need}.",
        kind=RefusalKind.NOT_FOUND,
        rule=needs.CON_5.id,
        hint=f"Needs here: {listed or 'none'}.",
    )


@operation(
    "connections.mark_need_done",
    summary="Say a need is taken care of: what it asks for is added, under any names.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def mark_need_done(context: Context, payload: NeedInput) -> NeedChanged:
    """CON-5: the chairman's word is final; nothing compares names to second-guess it. The
    agents that waited for it go back to work by themselves, and work out from the names
    and descriptions of what they are granted which is which."""
    project = await _project(context)
    need = await _need(context, project, payload)
    if need.state not in (needs.NeedState.MET, needs.NeedState.DONE):
        needs.mark_done(context.session, need, context.now, context.caller)
        await service.refresh(context.session, project, context.now, context.caller)
    return NeedChanged(kind=need.kind, name=need.name, state=need.state)


@operation(
    "connections.reopen_need",
    summary="Take back a need marked done: it is missing again.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def reopen_need(context: Context, payload: NeedInput) -> NeedChanged:
    """CON-5: only a need the chairman marked done is reopened; one met by a connection of
    its name is reopened by detaching that connection. A started project holds the seats
    that need it again."""
    project = await _project(context)
    need = await _need(context, project, payload)
    if need.state != needs.NeedState.DONE:
        raise Refusal(
            "need_not_done",
            f"{need.name} is not marked done.",
            rule=needs.CON_5.id,
            hint="Only a need marked done can be reopened. One met by a connection of its "
            "name opens again when that connection is detached.",
        )
    needs.reopen(context.session, need, context.now, context.caller)
    await service.refresh(context.session, project, context.now, context.caller)
    return NeedChanged(kind=need.kind, name=need.name, state=need.state)
