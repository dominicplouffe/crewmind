"""Ready for work (PLN-2, INV-18, INV-19): what task creation asks before it creates.

This module is what `work` imports from planning, so it imports nothing from `work`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller, platform_job
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.budget import service as budget
from nightsquad.domain.planning.model import (
    OPEN_SCOPE,
    REQUIREMENT_MACHINE,
    BetState,
    RequirementState,
)
from nightsquad.domain.planning.rules import INV_18, INV_19
from nightsquad.domain.projects.model import ProjectType
from nightsquad.domain.settings.service import SettingsService
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import Bet, Project, Requirement, RequirementDependency, Task

R = RequirementState
REQUIREMENT_CHANGED = event_type("requirement.state_changed", "A requirement changed state (7.2).")
PLANNING_JOB = platform_job("planning: requirements")


def move(
    session: AsyncSession,
    requirement: Requirement,
    target: RequirementState,
    caller: Caller,
    now: datetime,
    detail: dict[str, object] | None = None,
) -> None:
    """The one place a requirement changes state. A transition not in 7.2 is refused."""
    REQUIREMENT_MACHINE.check(requirement.state, target)
    before = requirement.state
    requirement.state = target
    append_event(
        session,
        type=REQUIREMENT_CHANGED,
        caller=caller,
        at=now,
        subject=("requirement", str(requirement.id)),
        project_id=requirement.project_id,
        before={"state": before},
        after={"state": target},
        detail=detail,
    )


async def get(session: AsyncSession, project_id: str, requirement_id: int) -> Requirement:
    requirement = await session.get(Requirement, requirement_id)
    if requirement is None or requirement.project_id != project_id:
        raise Refusal(
            "requirement_not_found",
            f"There is no requirement {requirement_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
        )
    return requirement


async def lowest_open_stage(session: AsyncSession, project_id: str) -> int | None:
    """The lowest stage that still has accepted scope not yet met (INV-19)."""
    return await session.scalar(
        select(func.min(Requirement.stage)).where(
            Requirement.project_id == project_id, Requirement.state.in_(OPEN_SCOPE)
        )
    )


async def unmet_dependencies(session: AsyncSession, requirement: Requirement) -> list[int]:
    rows = await session.scalars(
        select(Requirement.id)
        .join(RequirementDependency, RequirementDependency.depends_on == Requirement.id)
        .where(
            RequirementDependency.requirement_id == requirement.id,
            Requirement.state.not_in([R.MET, R.CUT, R.DECLINED]),
        )
        .order_by(Requirement.id)
    )
    return [int(row) for row in rows]


async def why_not_ready(
    session: AsyncSession, requirement: Requirement
) -> tuple[str, str, str] | None:
    """PLN-2: why work may not be created under this requirement now, as (code, message,
    hint), or None when it is ready."""
    number = requirement.id
    if requirement.state not in (R.ACCEPTED, R.IN_PROGRESS):
        return (
            "requirement_not_accepted",
            f"Requirement {number} is {requirement.state}. Work is created only under an "
            "accepted requirement.",
            "A proposed requirement is not scope until it is accepted.",
        )
    if requirement.estimate_runs is None:
        return (
            "requirement_not_estimated",
            f"Requirement {number} has no estimate in runs.",
            "Estimate it first.",
        )
    unmet = await unmet_dependencies(session, requirement)
    if unmet:
        listed = ", ".join(str(one) for one in unmet)
        return (
            "dependencies_not_met",
            f"Requirement {number} depends on {listed}, which is not met yet.",
            "Work on what it depends on first.",
        )
    lowest = await lowest_open_stage(session, requirement.project_id)
    if lowest is not None and requirement.stage > lowest:
        return (
            "stage_not_open",
            f"Requirement {number} is in stage {requirement.stage}, and stage {lowest} still "
            "has open scope.",
            f"Finish stage {lowest} first.",
        )
    return None


async def is_ready(session: AsyncSession, requirement: Requirement) -> bool:
    return await why_not_ready(session, requirement) is None


async def in_wrapup(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> budget.BudgetState | None:
    """The budget state when the project is in wrap-up mode (GOV-3), otherwise None."""
    state = await budget.state(session, settings, project, now)
    return state if state.spent >= state.wrapup_at else None


async def check_task_scope(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    *,
    requirement_id: int | None,
    bet_id: int | None,
    parent: Task | None,
    now: datetime,
) -> tuple[int | None, int | None]:
    """INV-18, INV-19, GOV-3: the requirement or bet a new task serves, checked, as
    (requirement, bet). A subtask serves what its parent serves. An Explore task serves
    an active bet; any other task serves a requirement that is ready for work."""
    if parent is not None:
        requirement_id, bet_id = parent.requirement_id, parent.bet_id
    if project.type == ProjectType.EXPLORE:
        if bet_id is None:
            raise Refusal(
                "task_needs_a_bet",
                "In an Explore project a task serves an active bet. Name it with `bet_id`.",
                rule=INV_18.id,
                hint="Read the plan with agent_plan. Open a bet if none fits.",
            )
        bet = await session.get(Bet, bet_id)
        if bet is None or bet.project_id != project.id:
            raise Refusal(
                "bet_not_found", f"There is no bet {bet_id} in this project.",
                kind=RefusalKind.NOT_FOUND,
            )  # fmt: skip
        if bet.state != BetState.ACTIVE:
            raise Refusal(
                "bet_not_active",
                f"Bet {bet.id} is {bet.state}. Work is created only under an active bet.",
                rule=INV_18.id,
                hint="Publish its finding, or open another bet.",
            )
        return None, bet.id
    if requirement_id is None:
        raise Refusal(
            "task_needs_a_requirement",
            "A task serves an accepted requirement. Name it with `requirement_id`.",
            rule=INV_18.id,
            hint="Read the plan with agent_plan. Propose a requirement if none fits.",
        )
    requirement = await get(session, project.id, requirement_id)
    problem = await why_not_ready(session, requirement)
    if problem is not None:
        code, message, hint = problem
        rule = INV_19 if code == "stage_not_open" else INV_18
        raise Refusal(code, message, rule=rule.id, hint=hint)
    wrapup = await in_wrapup(session, settings, project, now)
    if wrapup is not None and requirement.state != R.IN_PROGRESS:
        raise Refusal(
            "wrap_up_mode",
            f"The project is in wrap-up mode ({budget.arithmetic(wrapup)}). New tasks may only "
            "serve a requirement already in progress.",
            rule=budget.GOV_3.id,
            hint="Finish what is in progress, or ask the chairman to raise the budget.",
        )
    return requirement.id, None


async def task_claimed(session: AsyncSession, task: Task, now: datetime) -> None:
    """7.2: the first task claimed under an accepted requirement puts it in progress."""
    if task.requirement_id is None:
        return
    requirement = await session.get(Requirement, task.requirement_id)
    if requirement is not None and requirement.state == R.ACCEPTED:
        move(session, requirement, R.IN_PROGRESS, PLANNING_JOB, now, {"task": task.id})
