"""What people do with the role and squad libraries (LIB-1, LIB-2, LIB-3)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import PERSON_AND_MCP, Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.library import service
from nightsquad.domain.library.documents import LIB_1, RoleDoc, SquadDoc
from nightsquad.storage.events import event_type
from nightsquad.storage.models import Squad

ROLE_SAVED = event_type("role.saved", "A role, or a new version of one, was saved (LIB-1).")
SQUAD_SAVED = event_type("squad.saved", "A squad was saved (LIB-2).")
LIBRARY_RELOADED = event_type("library.reloaded", "The shipped library was loaded again (LIB-3).")

SEARCH_LIMIT_MOST = 50


class RoleRef(BaseModel):
    role: str = Field(description="The role's slug or name, from `roles list`.")


class RoleSaved(BaseModel):
    slug: str
    name: str
    version: int
    changed: bool = Field(description="False when the same content was already the newest.")


class SquadRef(BaseModel):
    squad: str = Field(description="The squad's slug, from `squads list`.")


class SquadItem(BaseModel):
    slug: str
    name: str
    outcome: str
    domains: list[str]
    seats: int = Field(description="Seats in its teams, not counting the CEO.")
    estimate_tokens: int | None


class SquadList(BaseModel):
    items: list[SquadItem]


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Words describing the work.")
    limit: int = Field(10, ge=1, le=SEARCH_LIMIT_MOST)


class SearchHit(BaseModel):
    kind: str = Field(description="role or squad.")
    slug: str
    name: str
    summary: str


class SearchResult(BaseModel):
    items: list[SearchHit]


def _may_replace(context: Context, what: str, slug: str) -> None:
    """LIB-3: the library is the install's. Anyone adds to it; only an admin changes
    what is already there, because every later project would pick the change up."""
    if context.caller.role != "admin":
        raise Refusal(
            f"{what}_exists",
            f"There is already a {what} with the slug {slug}, and only an admin may change it.",
            rule=LIB_1.id,
            hint="Give yours another slug.",
        )


@operation(
    "roles.show",
    summary="Show one role in full, as the file it can be saved to.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_role(context: Context, payload: RoleRef) -> RoleDoc:
    """LIB-3: the output is the role's file; save it and it can be loaded elsewhere."""
    await service.load_starter(context.session, context.now)
    return service.role_doc(await service.role_named(context.session, payload.role))


@operation(
    "roles.save",
    summary="Add a role from a file, or a new version of one that exists.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def save_role(context: Context, payload: RoleDoc) -> RoleSaved:
    """LIB-1, LIB-3: a changed role becomes its next version. Teams keep the version they
    were hired from until they are re-pinned."""
    await service.load_starter(context.session, context.now)
    current = await service.newest(context.session, payload.slug)
    if current is not None and service.role_doc(current) != payload:
        _may_replace(context, "role", payload.slug)
    named = await context.session.scalar(
        select(service.Role.slug).where(
            service.Role.name == payload.name, service.Role.slug != payload.slug
        )
    )
    if named is not None:
        raise Refusal(
            "role_name_taken",
            f"The role {named} is already called {payload.name}.",
            rule=LIB_1.id,
            hint="Give yours another name.",
        )
    role = await service.save_role(context.session, payload, service.CUSTOM, context.now)
    changed = current is None or role.id != current.id
    if changed:
        context.record(
            ROLE_SAVED,
            subject=("role", role.slug),
            after={"version": role.version, "name": role.name, "kind": role.seat_kind},
        )
    return RoleSaved(slug=role.slug, name=role.name, version=role.version, changed=changed)


def _squad_item(squad: Squad) -> SquadItem:
    return SquadItem(
        slug=squad.slug,
        name=squad.name,
        outcome=squad.outcome,
        domains=[str(domain) for domain in squad.domains],
        seats=sum(len(team["members"]) for team in squad.teams),
        estimate_tokens=squad.estimate_tokens,
    )


@operation(
    "squads.list",
    summary="List the ready-made squads: each is a job with a team already on it.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_squads(context: Context, payload: Empty) -> SquadList:
    await service.load_starter(context.session, context.now)
    rows = await context.session.scalars(select(Squad).order_by(Squad.slug))
    return SquadList(items=[_squad_item(row) for row in rows])


@operation(
    "squads.show",
    summary="Show one squad in full, as the file it can be saved to.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_squad(context: Context, payload: SquadRef) -> SquadDoc:
    await service.load_starter(context.session, context.now)
    return service.squad_doc(await service.squad_named(context.session, payload.squad))


@operation(
    "squads.save",
    summary="Add a squad from a file, or replace one that exists.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def save_squad(context: Context, payload: SquadDoc) -> SquadItem:
    """LIB-2: every role a squad names must be in the library."""
    await service.load_starter(context.session, context.now)
    current = await context.session.scalar(select(Squad).where(Squad.slug == payload.slug))
    if current is not None and service.squad_doc(current) != payload:
        _may_replace(context, "squad", payload.slug)
    squad = await service.save_squad(context.session, payload, service.CUSTOM, context.now)
    context.record(SQUAD_SAVED, subject=("squad", squad.slug), after={"name": squad.name})
    return _squad_item(squad)


@operation(
    "library.search",
    summary="Find roles and squads that fit a piece of work.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def search(context: Context, payload: SearchInput) -> SearchResult:
    """LIB-3: the same search the Founder uses (FND-2)."""
    await service.load_starter(context.session, context.now)
    hits = await service.search(context.session, payload.query, payload.limit)
    return SearchResult(
        items=[
            SearchHit(kind=hit.kind, slug=hit.slug, name=hit.name, summary=hit.summary)
            for hit in hits
        ]
    )


@operation(
    "library.reload",
    summary="Load the roles and squads shipped with this version of Nightsquad again.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def reload(context: Context, payload: Empty) -> SquadList:
    """LIB-3: a shipped role whose text has changed becomes its next version."""
    await service.reload_starter(context.session, context.now)
    context.record(LIBRARY_RELOADED, subject=("library", "starter"))
    rows = await context.session.scalars(select(Squad).order_by(Squad.slug))
    return SquadList(items=[_squad_item(row) for row in rows])
