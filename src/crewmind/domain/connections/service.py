"""The rules every connection operation shares: who may see and change an item, finding it
by name, storing its value, collisions between grants, and meeting needs (CON-1 to CON-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.accounts.model import ProjectRole
from crewmind.domain.connections import holds, needs
from crewmind.domain.connections.mcp import ServerState
from crewmind.domain.connections.model import (
    ALL_ROLES,
    CON_1,
    CON_2,
    CON_4,
    KIND_WORDS,
    SECRET_NAME,
    SECRET_OWNER,
    ConnectionState,
    Delivery,
    Kind,
    Scope,
)
from crewmind.domain.projects.access import project_not_found, role_in
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.registry import Scope as SettingScope
from crewmind.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from crewmind.storage.models import (
    Connection,
    ConnectionSecret,
    McpServer,
    Project,
    ProjectConnection,
    ProjectNeed,
)

LIVE = (ConnectionState.ACTIVE, ConnectionState.EXPIRED)
"""Items that still exist. A deleted item keeps its row for the record, without its value."""
CHAIRS = (ProjectRole.CHAIRMAN, ProjectRole.CO_CHAIR)
INSTALL_OWNER = ""


def not_found(name: str) -> Refusal:
    """The one answer for an item that does not exist and one the caller cannot see."""
    return Refusal(
        "connection_not_found",
        f"There is no connection named {name} that you can see.",
        kind=RefusalKind.NOT_FOUND,
        hint="List them with `crewmind connections list`.",
    )


async def chairs(session: AsyncSession, caller: Caller, project_id: str) -> bool:
    return await role_in(session, caller.person_id, project_id) in CHAIRS


async def can_see(session: AsyncSession, caller: Caller, item: Connection) -> bool:
    """CON-1: install items are seen by everyone, a person's by that person, a project's by
    its members and admins."""
    if item.scope == Scope.INSTALL:
        return caller.person_id is not None
    if item.scope == Scope.PERSON:
        return item.owner_id == caller.person_id
    return caller.is_admin or await role_in(session, caller.person_id, item.owner_id) is not None


async def can_manage(session: AsyncSession, caller: Caller, item: Connection) -> bool:
    """CON-1: an admin changes install items, a person their own, a chair the project's."""
    if item.scope == Scope.INSTALL:
        return caller.is_admin
    if item.scope == Scope.PERSON:
        return item.owner_id == caller.person_id
    return await chairs(session, caller, item.owner_id)


async def check_project(session: AsyncSession, caller: Caller, project_id: str | None) -> None:
    """INV-5, IF-3.3: a project the caller cannot see answers like one that does not exist,
    before anything else is checked."""
    if project_id is None:
        return
    member = await role_in(session, caller.person_id, project_id)
    if await session.get(Project, project_id) is None or (member is None and not caller.is_admin):
        raise project_not_found()


async def check_owner(
    session: AsyncSession, caller: Caller, scope: Scope, project_id: str | None
) -> str:
    """Who would own a new item in this scope, after checking the caller may add it there."""
    if scope == Scope.INSTALL:
        if not caller.is_admin:
            raise Refusal(
                "admin_only",
                "Only an admin adds connections for the whole install.",
                kind=RefusalKind.FORBIDDEN,
                rule=CON_1.id,
                hint="Add it to yourself, or to the project, instead.",
            )
        return INSTALL_OWNER
    if scope == Scope.PERSON:
        assert caller.person_id is not None
        return caller.person_id
    if project_id is None:
        raise Refusal(
            "project_required",
            "A project connection names its project.",
            rule=CON_1.id,
            hint="Give --project-id.",
        )
    if await session.get(Project, project_id) is None or not await chairs(
        session, caller, project_id
    ):
        if await role_in(session, caller.person_id, project_id) is None:
            raise project_not_found()
        raise Refusal(
            "role_required",
            "Only the chairman or a co-chair adds connections to a project.",
            kind=RefusalKind.FORBIDDEN,
            rule=CON_1.id,
        )
    return project_id


async def check_free(session: AsyncSession, scope: Scope, owner_id: str, name: str) -> None:
    taken = await session.scalar(
        select(Connection.id).where(
            Connection.scope == scope,
            Connection.owner_id == owner_id,
            Connection.name_key == name.lower(),
            Connection.state.in_(LIVE),
        )
    )
    if taken:
        raise Refusal(
            "connection_exists",
            f"A connection named {name} already exists here.",
            rule=CON_1.id,
            hint="Replace its value or choose another name.",
        )


async def find(
    session: AsyncSession, caller: Caller, ref: str, project_id: str | None = None
) -> Connection:
    """An item the caller can see, by id or by name. A name is looked for in the project
    first, then the caller's own items, then the install's."""
    await check_project(session, caller, project_id)
    item = await session.get(Connection, ref)
    if item is not None and item.state in LIVE and await can_see(session, caller, item):
        return item
    rows = await session.scalars(
        select(Connection).where(Connection.name_key == ref.lower(), Connection.state.in_(LIVE))
    )
    order = {Scope.PROJECT: 0, Scope.PERSON: 1, Scope.INSTALL: 2}
    found: list[Connection] = []
    for row in rows:
        if row.scope == Scope.PROJECT and row.owner_id != project_id:
            continue
        if await can_see(session, caller, row):
            found.append(row)
    if not found:
        raise not_found(ref)
    return min(found, key=lambda row: order[Scope(row.scope)])


async def manageable(
    session: AsyncSession, caller: Caller, ref: str, project_id: str | None = None
) -> Connection:
    item = await find(session, caller, ref, project_id)
    if not await can_manage(session, caller, item):
        who = {
            Scope.INSTALL: "an admin",
            Scope.PERSON: "its owner",
            Scope.PROJECT: "the project's chairman or a co-chair",
        }[Scope(item.scope)]
        raise Refusal(
            "not_yours",
            f"Only {who} changes {item.name}.",
            kind=RefusalKind.FORBIDDEN,
            rule=CON_1.id,
        )
    return item


async def check_value(
    session: AsyncSession, settings: SettingsService, value: str, name: str
) -> None:
    """CON-2: a value too short to mask reliably, or too large, is refused. The refusal
    never repeats the value."""
    install = Subject(SettingScope.INSTALL, INSTALL_SUBJECT)
    shortest = int(await settings.get(session, install, "secret.min_length"))
    largest = int(await settings.get(session, install, "secret.max_size"))
    if len(value) < shortest:
        raise Refusal(
            "secret_too_short",
            f"The value of {name} is shorter than {shortest} characters, so it could not be "
            "hidden reliably in what agents write.",
            rule=CON_2.id,
            hint="Use the full key or password.",
        )
    if len(value.encode()) > largest:
        raise Refusal(
            "secret_too_large",
            f"The value of {name} is larger than {largest} bytes.",
            rule=CON_2.id,
            hint="An admin can raise secret.max_size.",
        )


async def put_value(
    session: AsyncSession, store: SecretStore, item: Connection, value: str, now: datetime
) -> None:
    await store.put(session, (SECRET_OWNER, item.id), SECRET_NAME, value, now)
    item.value_set_at = now


async def attachments(
    session: AsyncSession, item_id: str
) -> list[tuple[ProjectConnection, Project]]:
    rows = await session.execute(
        select(ProjectConnection, Project)
        .join(Project, Project.id == ProjectConnection.project_id)
        .where(ProjectConnection.connection_id == item_id)
        .order_by(Project.name)
    )
    return [(link, project) for link, project in rows.all()]


async def attached(
    session: AsyncSession, project_id: str
) -> list[tuple[ProjectConnection, Connection]]:
    rows = await session.execute(
        select(ProjectConnection, Connection)
        .join(Connection, Connection.id == ProjectConnection.connection_id)
        .where(ProjectConnection.project_id == project_id, Connection.state.in_(LIVE))
        .order_by(Connection.name)
    )
    return [(link, item) for link, item in rows.all()]


def env_of(link: ProjectConnection, item: Connection) -> str | None:
    return link.env_name or item.env_name


def _overlap(left: list[str], right: list[str]) -> bool:
    return ALL_ROLES in left or ALL_ROLES in right or bool(set(left) & set(right))


@dataclass(frozen=True)
class Gives:
    """What one attachment puts in a run: an environment variable or file name, and sites."""

    env: str | None
    sites: frozenset[str]


async def gives(session: AsyncSession, item: Connection, env: str | None) -> Gives:
    if item.kind == Kind.VARIABLE:
        return Gives(env, frozenset())
    if item.kind != Kind.SECRET:
        return Gives(None, frozenset())
    secret = await session.get(ConnectionSecret, item.id)
    assert secret is not None
    if secret.delivery == Delivery.GIVEN:
        return Gives(env, frozenset())
    return Gives(None, frozenset(str(site) for site in secret.sites or []))


async def check_collisions(
    session: AsyncSession,
    project_id: str,
    item: Connection,
    roles: list[str],
    env: str | None,
    *,
    sites: frozenset[str] | None = None,
) -> None:
    """CON-4: two attachments that would give the same variable, file or site to the same
    role are refused, naming both. Nothing is shadowed."""
    mine = await gives(session, item, env)
    if sites is not None:
        mine = Gives(mine.env, sites)
    for link, other in await attached(session, project_id):
        if other.id == item.id or not _overlap(roles, list(link.roles or [])):
            continue
        theirs = await gives(session, other, env_of(link, other))
        clash = (
            f"the variable {mine.env}"
            if mine.env and theirs.env and mine.env.upper() == theirs.env.upper()
            else None
        )
        common = mine.sites & theirs.sites
        if common:
            clash = f"the site {sorted(common)[0]}"
        if clash:
            raise Refusal(
                "connection_collision",
                f"{item.name} and {other.name} would both give {clash} to the same role.",
                rule=CON_4.id,
                hint="Choose another variable name, or grant them to different roles.",
            )


async def met_by_connection(session: AsyncSession, project: Project, need: ProjectNeed) -> bool:
    """CON-5: a need is met by an active attached connection of its kind and name, granted
    to every role that has the need."""
    rows = await session.execute(
        select(ProjectConnection.roles)
        .join(Connection, Connection.id == ProjectConnection.connection_id)
        .outerjoin(McpServer, McpServer.connection_id == Connection.id)
        .where(
            ProjectConnection.project_id == project.id,
            Connection.kind == need.kind,
            Connection.name_key == need.name.lower(),
            Connection.state == ConnectionState.ACTIVE,
            # CON-14: a server waiting for someone to sign in meets nothing yet.
            or_(McpServer.state.is_(None), McpServer.state != ServerState.NEEDS_SIGN_IN),
        )
    )
    wanted = set(need.roles or [])
    for (roles,) in rows.all():
        granted = set(roles or [])
        if ALL_ROLES in granted or wanted <= granted:
            return True
    return False


async def refresh(session: AsyncSession, project: Project, now: datetime, caller: Caller) -> None:
    """After a change to what a project has: needs are brought up to date, and seats held or
    released (CON-5)."""
    if project.state in ("deleting", "deleted", "stopped"):
        return
    if project.state == "draft":
        await needs.sync(session, project, now, caller)
    else:
        await holds.apply(session, project, now, caller)


async def refresh_users(
    session: AsyncSession, item: Connection, now: datetime, caller: Caller
) -> None:
    for _, project in await attachments(session, item.id):
        await refresh(session, project, now, caller)


def label(item: Connection) -> str:
    return f"the {KIND_WORDS[Kind(item.kind)]} {item.name}"


needs.meets.append(met_by_connection)
