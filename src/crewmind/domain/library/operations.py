"""What people do with the role and crew libraries (LIB-1, LIB-2, LIB-3)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.domain.library import service
from crewmind.domain.library.documents import LIB_1, CrewDoc, RoleDoc
from crewmind.storage.events import event_type
from crewmind.storage.models import Crew

ROLE_SAVED = event_type("role.saved", "A role, or a new version of one, was saved (LIB-1).")
CREW_SAVED = event_type("crew.saved", "A crew was saved (LIB-2).")
LIBRARY_RELOADED = event_type("library.reloaded", "The shipped library was loaded again (LIB-3).")

SEARCH_LIMIT_MOST = 50


class RoleRef(BaseModel):
    role: str = Field(description="The role's slug or name, from `roles list`.")


class RoleSaved(BaseModel):
    slug: str
    name: str
    version: int
    changed: bool = Field(description="False when the same content was already the newest.")


class CrewRef(BaseModel):
    crew: str = Field(description="The crew's slug, from `crews list`.")


class CrewItem(BaseModel):
    slug: str
    name: str
    outcome: str
    domains: list[str]
    seats: int = Field(description="Seats in its teams, not counting the CEO.")
    estimate_tokens: int | None


class CrewList(BaseModel):
    items: list[CrewItem]


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Words describing the work.")
    limit: int = Field(10, ge=1, le=SEARCH_LIMIT_MOST)


class SearchHit(BaseModel):
    kind: str = Field(description="role or crew.")
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


def _crew_item(crew: Crew) -> CrewItem:
    return CrewItem(
        slug=crew.slug,
        name=crew.name,
        outcome=crew.outcome,
        domains=[str(domain) for domain in crew.domains],
        seats=sum(len(team["members"]) for team in crew.teams),
        estimate_tokens=crew.estimate_tokens,
    )


@operation(
    "crews.list",
    summary="List the ready-made crews: each is a job with a team already on it.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_crews(context: Context, payload: Empty) -> CrewList:
    await service.load_starter(context.session, context.now)
    rows = await context.session.scalars(select(Crew).order_by(Crew.slug))
    return CrewList(items=[_crew_item(row) for row in rows])


@operation(
    "crews.show",
    summary="Show one crew in full, as the file it can be saved to.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_crew(context: Context, payload: CrewRef) -> CrewDoc:
    await service.load_starter(context.session, context.now)
    return service.crew_doc(await service.crew_named(context.session, payload.crew))


@operation(
    "crews.save",
    summary="Add a crew from a file, or replace one that exists.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def save_crew(context: Context, payload: CrewDoc) -> CrewItem:
    """LIB-2: every role a crew names must be in the library."""
    await service.load_starter(context.session, context.now)
    current = await context.session.scalar(select(Crew).where(Crew.slug == payload.slug))
    if current is not None and service.crew_doc(current) != payload:
        _may_replace(context, "crew", payload.slug)
    crew = await service.save_crew(context.session, payload, service.CUSTOM, context.now)
    context.record(CREW_SAVED, subject=("crew", crew.slug), after={"name": crew.name})
    return _crew_item(crew)


@operation(
    "library.search",
    summary="Find roles and crews that fit a piece of work.",
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
    summary="Load the roles and crews shipped with this version of crewmind again.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def reload(context: Context, payload: Empty) -> CrewList:
    """LIB-3: a shipped role whose text has changed becomes its next version."""
    await service.reload_starter(context.session, context.now)
    context.record(LIBRARY_RELOADED, subject=("library", "starter"))
    rows = await context.session.scalars(select(Crew).order_by(Crew.slug))
    return CrewList(items=[_crew_item(row) for row in rows])
