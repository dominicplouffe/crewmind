"""Roster and run operations for people (EXE-1, EXE-4, EXE-11, GOV-2, IF-3.8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.pagination import PageRequest, fetch_page
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import corrections
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import roster, runs
from crewmind.domain.execution.model import RunKind, TeamState
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.services import services_of
from crewmind.storage.models import LedgerLine, Role, Run, RunStep, Seat, Team, Wake


class RoleItem(BaseModel):
    name: str
    version: int
    seat_kind: str
    description: str
    tools: list[str]


class RoleList(BaseModel):
    items: list[RoleItem]


class SeatItem(BaseModel):
    name: str
    kind: str
    role: str
    team: str | None
    lead: bool
    state: str
    pause_reason: str | None
    replies: int | None = Field(default=None, description="Its replies in the project chat.")
    corrections: int | None = Field(default=None, description="Times you said: not what I asked.")
    listening_score: float | None = Field(
        default=None, description="Corrections per 100 replies. Lower is better."
    )


class Roster(BaseModel):
    seats: list[SeatItem]
    teams: list[str]


class HireInput(ProjectRef):
    team: str = Field(min_length=1, max_length=60, description="A name for the team.")
    role: str = Field(description="The role its members take, from `roles list`.")
    members: int = Field(1, description="How many members.")


class TeamRef(ProjectRef):
    team: str = Field(description="The team's name.")


class RunListInput(ProjectRef, PageRequest):
    pass


class RunItem(BaseModel):
    run_id: str
    seat: str
    kind: str
    state: str
    attempt: int
    reasons: list[str]
    model: str | None
    provider: str | None
    queued_at: datetime
    ended_at: datetime | None
    end_detail: str | None
    tokens_counted: int


class RunList(BaseModel):
    items: list[RunItem]
    next: str | None = None


class RunRef(ProjectRef):
    run_id: str = Field(description="The run's id, from `runs list`.")


class RunTrace(RunItem):
    system_prompt: str | None
    context_pack: str | None
    steps: list[dict[str, Any]]


class BudgetView(BaseModel):
    spent: int
    wall: int
    remaining: int
    warn_at: int
    wrapup_at: int
    at_wall: bool
    summary: str
    by_kind: dict[str, int] = Field(description="Tokens by kind. Cache reads do not count.")


async def _roster(context: Context, project_id: str) -> Roster:
    rows = await context.session.execute(
        select(Seat, Role, Team)
        .join(Role, Role.id == Seat.role_id)
        .outerjoin(Team, Team.id == Seat.team_id)
        .where(Seat.project_id == project_id)
        .order_by(Seat.created_at, Seat.name)
    )
    teams = await context.session.scalars(
        select(Team.name).where(Team.project_id == project_id).order_by(Team.name)
    )
    heard = await corrections.listening(context.session, project_id)
    return Roster(
        seats=[
            SeatItem(
                name=seat.name,
                kind=seat.kind,
                role=role.name,
                team=team.name if team else None,
                lead=seat.is_lead,
                state=seat.state,
                pause_reason=seat.pause_reason,
                replies=heard.get(seat.id, (0, 0))[0],
                corrections=heard.get(seat.id, (0, 0))[1],
                listening_score=corrections.listening_score(*heard.get(seat.id, (0, 0))),
            )
            for seat, role, team in rows.all()
        ],
        teams=list(teams),
    )


@operation(
    "roles.list",
    summary="List the roles agents can be hired from.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_roles(context: Context, payload: Empty) -> RoleList:
    await roster.ensure_starter_roles(context.session, context.now)
    rows = await context.session.scalars(select(Role).order_by(Role.name, Role.version))
    return RoleList(
        items=[
            RoleItem(
                name=row.name,
                version=row.version,
                seat_kind=row.seat_kind,
                description=row.description,
                tools=[str(tool) for tool in row.tools],
            )
            for row in rows
        ]
    )


@operation(
    "roster.show",
    summary="Show a project's agents: the CEO, the teams and every seat.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_roster(context: Context, payload: ProjectRef) -> Roster:
    return await _roster(context, payload.project_id)


@operation(
    "roster.hire_team",
    summary="Hire a team from a role.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def hire_team(context: Context, payload: HireInput) -> Roster:
    """EXE-1: a chairman hire and a CEO hire take the same path."""
    await roster.hire_team(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        name=payload.team,
        role_name=payload.role,
        members=payload.members,
        caller=context.caller,
        now=context.now,
    )
    return await _roster(context, payload.project_id)


@operation(
    "roster.stand_down_team",
    summary="Stand a team down. Its history is kept and it can be recalled.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def stand_down_team(context: Context, payload: TeamRef) -> Roster:
    await roster.set_team_state(
        context.session,
        view_of(context).project,
        payload.team,
        TeamState.STOOD_DOWN,
        caller=context.caller,
        now=context.now,
    )
    return await _roster(context, payload.project_id)


@operation(
    "roster.recall_team",
    summary="Recall a team that was stood down.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def recall_team(context: Context, payload: TeamRef) -> Roster:
    await roster.set_team_state(
        context.session,
        view_of(context).project,
        payload.team,
        TeamState.ACTIVE,
        caller=context.caller,
        now=context.now,
    )
    return await _roster(context, payload.project_id)


async def _run_item(context: Context, run: Run) -> RunItem:
    seat = await context.session.get(Seat, run.seat_id)
    wake = await context.session.get(Wake, run.wake_id)
    counted = await context.session.scalar(
        select(func.coalesce(func.sum(LedgerLine.counted), 0)).where(LedgerLine.run_id == run.id)
    )
    return RunItem(
        run_id=run.id,
        seat=seat.name if seat else "",
        kind=run.kind,
        state=run.state,
        attempt=run.attempt,
        reasons=[str(reason) for reason in (wake.reasons if wake else [])],
        model=run.model,
        provider=run.provider,
        queued_at=run.queued_at,
        ended_at=run.ended_at,
        end_detail=run.end_detail,
        tokens_counted=int(counted or 0),
    )


@operation(
    "runs.list",
    summary="List a project's runs: who ran, why, on what, and how it ended.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_runs(context: Context, payload: RunListInput) -> RunList:
    rows, cursor = await fetch_page(
        context.session,
        select(Run).where(Run.project_id == payload.project_id),
        payload,
        key=Run.id,
        at=Run.queued_at,
    )
    return RunList(items=[await _run_item(context, row) for row in rows], next=cursor)


@operation(
    "runs.trace",
    summary="Show one run's trace: the exact prompt and context it got, and every step.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def trace(context: Context, payload: RunRef) -> RunTrace:
    """EXE-11: every run stores its trace and the exact prompt and context pack sent."""
    run = await context.session.get(Run, payload.run_id)
    if run is None or run.project_id != payload.project_id:
        raise Refusal("run_not_found", "There is no run with that id.", kind=RefusalKind.NOT_FOUND)
    steps = await context.session.scalars(
        select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.id)
    )
    item = await _run_item(context, run)
    return RunTrace(
        **item.model_dump(),
        system_prompt=run.system_prompt,
        context_pack=run.context_pack,
        steps=[{"kind": step.kind, "at": step.at.isoformat(), **step.data} for step in steps],
    )


@operation(
    "budget.show",
    summary="Show the token budget: used, remaining and the wall.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_budget(context: Context, payload: ProjectRef) -> BudgetView:
    """GOV-2: used, remaining and the wall. Only non-cached tokens count."""
    project = view_of(context).project
    state = await budget.state(context.session, services_of(context).settings, project, context.now)
    totals = (
        await context.session.execute(
            select(
                func.coalesce(func.sum(LedgerLine.input_tokens), 0),
                func.coalesce(func.sum(LedgerLine.output_tokens), 0),
                func.coalesce(func.sum(LedgerLine.cache_write_tokens), 0),
                func.coalesce(func.sum(LedgerLine.cache_read_tokens), 0),
            ).where(LedgerLine.project_id == project.id)
        )
    ).one()
    return BudgetView(
        spent=state.spent,
        wall=state.wall,
        remaining=state.remaining,
        warn_at=state.warn_at,
        wrapup_at=state.wrapup_at,
        at_wall=state.at_wall,
        summary=budget.arithmetic(state),
        by_kind={
            "input": int(totals[0]),
            "output": int(totals[1]),
            "cache_write": int(totals[2]),
            "cache_read": int(totals[3]),
        },
    )


class Interrupted(BaseModel):
    run_id: str
    state: str


@operation(
    "runs.interrupt",
    summary="Interrupt a run in progress, such as a reply you no longer want.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def interrupt(context: Context, payload: RunRef) -> Interrupted:
    """CHAT-4, EXE-9: Esc interrupts a reply. The run is killed and its token revoked; the
    runner stops the sandbox at its next heartbeat."""
    run = await context.session.get(Run, payload.run_id)
    if run is None or run.project_id != payload.project_id:
        raise Refusal("run_not_found", "There is no run with that id.", kind=RefusalKind.NOT_FOUND)
    await runs.kill(context.session, run, context.now, caller=context.caller)
    seat = await context.session.get(Seat, run.seat_id)
    if run.kind == RunKind.CHAT and seat is not None:
        await conversation.stop_reply(context.session, seat, context.now)
    return Interrupted(run_id=run.id, state=run.state)
