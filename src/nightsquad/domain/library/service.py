"""The role and squad libraries: load, save, look up and search (LIB-1, LIB-2, LIB-3)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.library.documents import (
    LIB_1,
    Estimate,
    RoleDoc,
    SquadDoc,
    SquadTeam,
    parse,
)
from nightsquad.storage.models import Role, Squad

__all__ = ["LIB_1", "Role"]

STARTER, CUSTOM = "starter", "custom"
PACKAGE = "nightsquad.content"


def _packaged(folder: str) -> list[dict[str, Any]]:
    root = resources.files(PACKAGE).joinpath("library", folder)
    return [
        json.loads(entry.read_text(encoding="utf-8"))
        for entry in sorted(root.iterdir(), key=lambda entry: entry.name)
        if entry.name.endswith(".json")
    ]


def starter_roles() -> list[RoleDoc]:
    return [parse(RoleDoc, document, "role") for document in _packaged("roles")]


def starter_squads() -> list[SquadDoc]:
    return [parse(SquadDoc, document, "squad") for document in _packaged("squads")]


def role_doc(role: Role) -> RoleDoc:
    return RoleDoc.model_validate(
        {
            "slug": role.slug,
            "name": role.name,
            "kind": role.seat_kind,
            "category": role.category,
            "domains": role.domains,
            "description": role.description,
            "min_class": role.min_class,
            "needs_vision": role.needs_vision,
            "tools": role.tools,
            "skills": role.skills,
            "credential_names": role.credential_names,
            "charter": role.charter,
        }
    )


def squad_doc(squad: Squad) -> SquadDoc:
    estimate = None
    if squad.estimate_runs is not None and squad.estimate_tokens is not None:
        estimate = Estimate(runs=squad.estimate_runs, tokens=squad.estimate_tokens)
    return SquadDoc(
        slug=squad.slug,
        name=squad.name,
        outcome=squad.outcome,
        ceo_role=squad.ceo_role,
        domains=[str(domain) for domain in squad.domains],
        teams=[SquadTeam.model_validate(team) for team in squad.teams],
        estimate=estimate,
    )


async def newest(session: AsyncSession, slug: str) -> Role | None:
    return await session.scalar(
        select(Role).where(Role.slug == slug).order_by(Role.version.desc()).limit(1)
    )


async def save_role(session: AsyncSession, doc: RoleDoc, source: str, now: datetime) -> Role:
    """Store a role. The same content as the newest version changes nothing; anything else
    becomes the next version, and teams stay pinned to the one they were hired from (LIB-1)."""
    current = await newest(session, doc.slug)
    if current is not None and role_doc(current) == doc:
        return current
    role = Role(
        slug=doc.slug,
        name=doc.name,
        version=(current.version if current else 0) + 1,
        seat_kind=doc.kind,
        category=doc.category,
        domains=list(doc.domains),
        description=doc.description,
        charter=doc.charter,
        tools=list(doc.tools),
        skills=list(doc.skills),
        credential_names=list(doc.credential_names),
        min_class=doc.min_class,
        needs_vision=doc.needs_vision,
        needs_web=False,
        source=source,
        created_at=now,
    )
    session.add(role)
    await session.flush()
    return role


async def save_squad(session: AsyncSession, doc: SquadDoc, source: str, now: datetime) -> Squad:
    """Store a squad, replacing one of the same slug. Every role it names must exist (LIB-2)."""
    for slug in {doc.ceo_role, *(team.role for team in doc.teams)}:
        await role_named(session, slug)
    ceo = await role_named(session, doc.ceo_role)
    if ceo.seat_kind != "ceo":
        raise Refusal("not_a_ceo_role", f"{doc.ceo_role} is not a role that can be the CEO.")
    squad = await session.scalar(select(Squad).where(Squad.slug == doc.slug))
    if squad is None:
        squad = Squad(slug=doc.slug)
        session.add(squad)
    squad.name, squad.outcome, squad.ceo_role = doc.name, doc.outcome, doc.ceo_role
    squad.domains = list(doc.domains)
    squad.teams = [team.model_dump() for team in doc.teams]
    squad.estimate_runs = doc.estimate.runs if doc.estimate else None
    squad.estimate_tokens = doc.estimate.tokens if doc.estimate else None
    squad.source, squad.updated_at = source, now
    await session.flush()
    return squad


async def load_starter(session: AsyncSession, now: datetime) -> None:
    """Load the library shipped with Nightsquad. A role whose shipped text has changed gets
    a new version (LIB-3). Cheap when nothing is missing."""
    roles, squads = starter_roles(), starter_squads()
    have_roles = await session.scalar(
        select(func.count(func.distinct(Role.slug))).where(Role.source == STARTER)
    )
    have_squads = await session.scalar(
        select(func.count()).select_from(Squad).where(Squad.source == STARTER)
    )
    if (have_roles or 0) >= len(roles) and (have_squads or 0) >= len(squads):
        return
    await reload_starter(session, now)


async def reload_starter(session: AsyncSession, now: datetime) -> None:
    for doc in starter_roles():
        await save_role(session, doc, STARTER, now)
    for squad in starter_squads():
        await save_squad(session, squad, STARTER, now)


async def role_named(session: AsyncSession, ref: str) -> Role:
    """The newest version of a role, by its slug or its name."""
    role = await newest(session, ref.strip().lower())
    if role is None:
        role = await session.scalar(
            select(Role)
            .where(func.lower(Role.name) == ref.strip().lower())
            .order_by(Role.version.desc())
            .limit(1)
        )
    if role is None:
        raise Refusal(
            "role_not_found",
            f"There is no role named {ref}.",
            kind=RefusalKind.NOT_FOUND,
            hint="List the roles with `squad roles list`.",
        )
    return role


async def role_version(session: AsyncSession, slug: str, version: int) -> Role:
    role = await session.scalar(select(Role).where(Role.slug == slug, Role.version == version))
    if role is None:
        raise Refusal(
            "role_version_not_found",
            f"There is no version {version} of the role {slug}.",
            kind=RefusalKind.NOT_FOUND,
            hint="Leave the version out to use the newest.",
        )
    return role


async def current_roles(session: AsyncSession) -> list[Role]:
    """The newest version of every role, by slug."""
    newest_of = (
        select(Role.slug, func.max(Role.version).label("version")).group_by(Role.slug).subquery()
    )
    rows = await session.scalars(
        select(Role)
        .join(
            newest_of,
            (Role.slug == newest_of.c.slug) & (Role.version == newest_of.c.version),
        )
        .order_by(Role.slug)
    )
    return list(rows)


async def squad_named(session: AsyncSession, slug: str) -> Squad:
    squad = await session.scalar(select(Squad).where(Squad.slug == slug.strip().lower()))
    if squad is None:
        raise Refusal(
            "squad_not_found",
            f"There is no squad named {slug}.",
            kind=RefusalKind.NOT_FOUND,
            hint="List the squads with `squad squads list`.",
        )
    return squad


@dataclass(frozen=True)
class Hit:
    kind: str
    slug: str
    name: str
    summary: str
    score: int


WORD = re.compile(r"[a-z0-9]+")


def _score(words: set[str], *texts: str) -> int:
    """How many of the query's words a record has, counting a word in its name twice."""
    name = set(WORD.findall(texts[0].lower()))
    rest = set(WORD.findall(" ".join(texts[1:]).lower()))
    return 2 * len(words & name) + len(words & (rest - name))


async def search(session: AsyncSession, query: str, limit: int) -> list[Hit]:
    """Roles and squads whose name, category, domains or description share words with the
    query, best first (LIB-3)."""
    words = set(WORD.findall(query.lower()))
    hits: list[Hit] = []
    for role in await current_roles(session):
        score = _score(
            words,
            f"{role.slug} {role.name}",
            role.category,
            " ".join(str(domain) for domain in role.domains),
            role.description,
        )
        hits.append(Hit("role", role.slug, role.name, role.description, score))
    squads = await session.scalars(select(Squad).order_by(Squad.slug))
    for squad in squads:
        score = _score(
            words,
            f"{squad.slug} {squad.name}",
            " ".join(str(domain) for domain in squad.domains),
            squad.outcome,
        )
        hits.append(Hit("squad", squad.slug, squad.name, squad.outcome, score))
    found = [hit for hit in hits if hit.score > 0]
    return sorted(found, key=lambda hit: (-hit.score, hit.kind, hit.slug))[:limit]
