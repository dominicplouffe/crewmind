"""Connections before a project exists (CON-14, LIB-4, FND-9): what a person could attach,
what a drafted spec's roster needs and whether the person has it, and, at creation, the
spec's grants applied to the connections the creator can see."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.execute import Context
from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.connections import attach, needs
from nightsquad.domain.connections.model import ConnectionState, Scope
from nightsquad.domain.library import service as library
from nightsquad.storage.models import Connection, Project, ProjectConnection


class Attachable(BaseModel):
    name: str
    kind: str = Field(description="secret, variable or mcp_server.")
    description: str
    scope: str = Field(description="install (everyone's) or person (yours).")


class DraftNeed(BaseModel):
    kind: str = Field(description="secret, variable or mcp_server.")
    name: str
    roles: list[str] = Field(description="The roles of the draft that need it.")
    have: bool = Field(description="You have a connection by this name and kind to attach.")
    granted: bool = Field(description="The draft grants it, so creating the project attaches it.")


async def attachable(session: AsyncSession, person_id: str | None) -> list[Connection]:
    """CON-1: what a person may attach to a project they chair: the install's connections
    and their own. Never a value (INV-6)."""
    if person_id is None:
        return []
    rows = await session.scalars(
        select(Connection)
        .where(
            Connection.state == ConnectionState.ACTIVE,
            or_(
                Connection.scope == Scope.INSTALL,
                (Connection.scope == Scope.PERSON) & (Connection.owner_id == person_id),
            ),
        )
        .order_by(Connection.name_key, Connection.scope)
    )
    return list(rows)


def listed(items: list[Connection]) -> list[Attachable]:
    return [
        Attachable(name=item.name, kind=item.kind, description=item.description, scope=item.scope)
        for item in items
    ]


def _match(items: list[Connection], kind: str, name: str) -> Connection | None:
    """CON-1: a need is met by a connection of its kind whose name matches whatever its case.
    The person's own comes before the install's."""
    found = [item for item in items if item.kind == kind and item.name_key == name.lower()]
    found.sort(key=lambda item: item.scope != Scope.PERSON)
    return found[0] if found else None


def _entries(value: Any) -> list[dict[str, Any]]:
    """The objects of a list in a spec held as JSON."""
    found = cast(list[Any], value) if isinstance(value, list) else []
    return [cast(dict[str, Any], entry) for entry in found if isinstance(entry, dict)]


def _strings(value: Any) -> list[str]:
    return [str(entry) for entry in cast(list[Any], value)] if isinstance(value, list) else []


def grants_of(source: dict[str, Any]) -> list[tuple[str, str, set[str]]]:
    """Each grant of a spec, or of a project's extras: kind, name and roles."""
    return [
        (str(grant.get("kind", needs.NeedKind.SECRET)), str(grant.get("name", "")),
         set(_strings(grant.get("roles"))))
        for grant in _entries(source.get("credentials"))
    ]  # fmt: skip


async def _role_needs(session: AsyncSession, spec: dict[str, Any]) -> dict[str, list[str]]:
    """Each role of the draft and the secrets it declares, custom roles included."""
    custom = {str(role.get("slug")): role for role in _entries(spec.get("roles"))}
    found: dict[str, list[str]] = {}
    ceo = spec.get("ceo")
    slugs = [str(cast(dict[str, Any], ceo).get("role", ""))] if isinstance(ceo, dict) else []
    slugs += [str(team.get("role", "")) for team in _entries(spec.get("teams"))]
    for slug in filter(None, slugs):
        if slug in custom:
            found[slug] = _strings(custom[slug].get("credential_names"))
            continue
        role = await library.newest(session, slug)
        if role is not None:
            found[slug] = [str(name) for name in role.credential_names or []]
    return found


async def draft_needs(
    session: AsyncSession, person_id: str | None, spec: dict[str, Any] | None
) -> list[DraftNeed]:
    """FND-9, CON-14: every need of a drafted roster, whether the person has it, and whether
    the draft grants it."""
    if not spec:
        return []
    wanted: dict[tuple[str, str], set[str]] = {}
    spelled: dict[tuple[str, str], tuple[str, str]] = {}

    def key_of(kind: str, name: str) -> tuple[str, str]:
        """CON-1: names match whatever their case; the first spelling is kept."""
        return spelled.setdefault((kind, name.lower()), (kind, name))

    role_needs = await _role_needs(session, spec)
    for slug, names in role_needs.items():
        for name in names:
            wanted.setdefault(key_of(needs.NeedKind.SECRET, name), set()).add(slug)
    granted: set[tuple[str, str]] = set()
    for kind, name, asked in grants_of(spec):
        key = key_of(kind, name)
        roles = asked & set(role_needs)
        if roles:
            wanted.setdefault(key, set()).update(roles)
            granted.add(key)
    items = await attachable(session, person_id)
    return [
        DraftNeed(
            kind=kind,
            name=name,
            roles=sorted(roles),
            have=_match(items, kind, name) is not None,
            granted=(kind, name) in granted,
        )
        for (kind, name), roles in sorted(wanted.items())
    ]


@dataclass(frozen=True)
class Applied:
    attached: list[str]
    not_attached: list[str]
    """Grants that could not be applied, each in plain words."""


async def apply_grants(context: Context, project: Project) -> Applied:
    """LIB-4, CON-4: each connection the spec grants that the creator can see is attached,
    granted to the roles named that are on the roster. What the creator does not have
    stays an open need (CON-5); a grant that would collide is left for the chairman."""
    items = await attachable(context.session, context.caller.person_id)
    on_roster = set(await attach.roster_roles(context, project))
    done: list[str] = []
    skipped: list[str] = []
    for kind, name, asked in grants_of(project.extras or {}):
        roles = sorted(asked & on_roster)
        item = _match(items, kind, name)
        if item is None or not roles:
            continue
        linked = await context.session.scalar(
            select(ProjectConnection.connection_id).where(
                ProjectConnection.project_id == project.id,
                ProjectConnection.connection_id == item.id,
            )
        )
        if linked is not None:
            continue
        try:
            await attach.attach(context, project, item, roles, None)
        except Refusal as refusal:
            skipped.append(f"{item.name}: {refusal.envelope.message}")
            continue
        done.append(item.name)
    return Applied(done, skipped)
