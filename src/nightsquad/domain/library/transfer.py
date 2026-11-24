"""Creating a project from a spec, exporting one, and cloning (LIB-4, LIB-5, PRJ-9).

Every step of an import is the operation a person would call by hand, in one
transaction: a refusal anywhere leaves nothing created."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from nightsquad.catalog import catalog
from nightsquad.catalog.execute import Context
from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.connections import drafted
from nightsquad.domain.execution import roster
from nightsquad.domain.execution.model import SeatKind, TeamState
from nightsquad.domain.library import service
from nightsquad.domain.library.spec import (
    LIB_4,
    CredentialGrant,
    Deadline,
    ProjectSpec,
    SpecCeo,
    SpecTeam,
)
from nightsquad.domain.memory.pinned import ORDER_ACTIVE
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import Subject
from nightsquad.services import services_of
from nightsquad.storage.models import (
    ModelCredential,
    Project,
    ProjectCredential,
    Role,
    Seat,
    StandingOrder,
    TargetDate,
    Team,
)

BUDGET, QUALITY = "budget.tokens", "quality"
FROM_SPEC = "From the project spec."


async def _call(context: Context, operation_name: str, /, **values: Any) -> Any:
    operation = catalog.get(operation_name)
    return await context.executor.call(context, operation, operation.input(**values))


async def check(context: Context, spec: ProjectSpec) -> list[str]:
    """What stops this spec from becoming a project, in plain sentences. Empty when
    nothing does."""
    await service.load_starter(context.session, context.now)
    embedded = {role.slug: role for role in spec.roles}
    problems: list[str] = []

    async def kind_of(slug: str) -> str | None:
        if slug in embedded:
            return embedded[slug].kind
        role = await service.newest(context.session, slug)
        return role.seat_kind if role else None

    ceo = await kind_of(spec.ceo.role)
    if ceo is None:
        problems.append(f"The CEO role {spec.ceo.role} is not in the library or the spec.")
    elif ceo != SeatKind.CEO:
        problems.append(f"{spec.ceo.role} is not a role that can be the CEO.")
    names: list[str] = ["CEO"]
    for team in spec.teams:
        kind = await kind_of(team.role)
        if kind is None:
            problems.append(f"Team {team.name}: the role {team.role} is not in the library.")
        elif kind == SeatKind.CEO:
            problems.append(f"Team {team.name}: a team cannot be hired from a CEO role.")
        names.extend(team.members)
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        problems.append(f"Two agents are named {twice[0]}; every agent needs its own name.")
    if len({team.name for team in spec.teams}) < len(spec.teams):
        problems.append("Two teams have the same name.")
    known = services_of(context).registry.settings
    for name in spec.settings:
        if name not in known:
            problems.append(f"There is no setting named {name}.")
    return problems


async def create(context: Context, spec: ProjectSpec) -> tuple[Project, list[str]]:
    """Create a draft project from a spec. Returns it with what is still missing before
    it can start (FND-13)."""
    problems = await check(context, spec)
    if problems:
        raise Refusal(
            "spec_cannot_be_created",
            " ".join(problems),
            rule=LIB_4.id,
            hint="Fix the spec and try again. `squad specs check` lists every problem.",
        )
    for role in spec.roles:
        await _call(context, "roles.save", **role.model_dump())
    created = await _call(
        context, "projects.create", name=spec.name, type=spec.type, goal=spec.goal
    )
    project = await context.session.get(Project, created.project_id)
    assert project is not None
    ref = {"project_id": project.id}
    await roster.set_ceo_role(context.session, project, spec.ceo.role)

    changes = dict(spec.settings)
    if spec.budget_tokens is not None:
        changes[BUDGET] = spec.budget_tokens
    if spec.quality is not None:
        changes[QUALITY] = spec.quality
    if changes:
        await _call(context, "settings.change_project", **ref, changes=changes, reason=FROM_SPEC)
    for team in spec.teams:
        await roster.hire_team(
            context.session,
            services_of(context).settings,
            project,
            name=team.name,
            role_name=team.role,
            role_version=team.version,
            members=len(team.members),
            names=team.members,
            stand_down_when=team.stand_down_when,
            caller=context.caller,
            now=context.now,
        )
    for order in spec.standing_orders:
        await _call(context, "orders.pin", **ref, what=order)
    if spec.deadline is not None:
        await _call(
            context, "plan.set_target", **ref, date=spec.deadline.date, source=spec.deadline.source
        )
    project.extras = {
        "controlled_domains": spec.controlled_domains,
        "integrations": spec.integrations,
        "credentials": [grant.model_dump() for grant in spec.credentials],
    }
    applied = await drafted.apply_grants(context, project)
    return project, [*await _link_payer(context, project, spec), *applied.not_attached]


async def _credentials(context: Context) -> set[str]:
    return set(
        await context.session.scalars(
            select(ModelCredential.name).where(ModelCredential.owner_id == context.caller.actor_id)
        )
    )


async def _link_payer(context: Context, project: Project, spec: ProjectSpec) -> list[str]:
    """Link the paying credential when the person has one by that name, and say what is
    still missing. A spec never carries the value (LIB-4)."""
    if spec.paying_credential in await _credentials(context):
        await _call(
            context, "models.set_payer", project_id=project.id, credential=spec.paying_credential
        )
    return await missing_setup(context, spec)


async def missing_setup(context: Context, spec: ProjectSpec) -> list[str]:
    """What this person still has to set up before a project from this spec can start,
    on this install (FND-13). It changes nothing."""
    missing: list[str] = []
    if spec.paying_credential is None:
        missing.append(
            "No credential pays for this project yet. Choose one with `models set-payer`."
        )
    elif spec.paying_credential not in await _credentials(context):
        missing.append(
            f"You have no credential named {spec.paying_credential}. Add it with "
            "`credentials add`, then choose it with `models set-payer`."
        )
    # A role's secrets are needs of the project, shown with what they hold (CON-5).
    for integration in spec.integrations:
        missing.append(f"The spec asks for {integration}, which is not available in this version.")
    return missing


async def export(context: Context, project: Project) -> ProjectSpec:
    """The project as a spec: what it is and how it is set up, with no history and no
    secret value (PRJ-9, LIB-4)."""
    session = context.session
    stored = await services_of(context).settings.stored(
        session, Subject(Scope.PROJECT, project.id, project.type)
    )
    settings = {name: row.value for name, row in stored.items()}
    budget, quality = settings.pop(BUDGET, None), settings.pop(QUALITY, None)
    target = await session.scalar(select(TargetDate).where(TargetDate.project_id == project.id))
    payer = await session.scalar(
        select(ModelCredential.name)
        .join(ProjectCredential, ProjectCredential.credential_id == ModelCredential.id)
        .where(
            ProjectCredential.project_id == project.id,
            ProjectCredential.use == "primary",
            ProjectCredential.seat_id == "",
        )
    )
    ceo_role = await session.scalar(
        select(Role)
        .join(Seat, Seat.role_id == Role.id)
        .where(Seat.project_id == project.id, Seat.kind == SeatKind.CEO)
    )
    assert ceo_role is not None
    used: dict[str, Role] = {ceo_role.slug: ceo_role}
    teams: list[SpecTeam] = []
    rows = await session.execute(
        select(Team, Role)
        .join(Role, Role.id == Team.role_id)
        .where(Team.project_id == project.id, Team.state == TeamState.ACTIVE)
        .order_by(Team.created_at, Team.name)
    )
    for team, role in rows.all():
        members = await session.scalars(
            select(Seat.name)
            .where(Seat.team_id == team.id)
            .order_by(Seat.is_lead.desc(), Seat.created_at, Seat.name)
        )
        used[role.slug] = role
        teams.append(
            SpecTeam(
                name=team.name,
                role=role.slug,
                version=role.version,
                members=list(members),
                stand_down_when=team.stand_down_when,
            )
        )
    orders = await session.scalars(
        select(StandingOrder.text)
        .where(StandingOrder.project_id == project.id, StandingOrder.state == ORDER_ACTIVE)
        .order_by(StandingOrder.id)
    )
    extras: dict[str, list[Any]] = project.extras or {}
    return ProjectSpec(
        name=project.name,
        goal=project.goal,
        type=project.type,  # pyright: ignore[reportArgumentType]
        deadline=Deadline(date=target.date, source=target.source) if target else None,
        budget_tokens=int(budget) if budget is not None else None,
        quality=quality,
        paying_credential=payer,
        settings=settings,
        ceo=SpecCeo(role=ceo_role.slug),
        teams=teams,
        standing_orders=list(orders),
        controlled_domains=list(extras.get("controlled_domains", [])),
        integrations=list(extras.get("integrations", [])),
        roles=[service.role_doc(role) for role in used.values() if role.source == service.CUSTOM],
        credentials=[
            CredentialGrant.model_validate(grant) for grant in extras.get("credentials", [])
        ],
    )
