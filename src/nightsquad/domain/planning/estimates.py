"""The plan's arithmetic: bias, tokens per run, plan tokens and whether scope fits the
budget (PLN-3). Every refusal that cites arithmetic takes its numbers from here."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.domain.budget import service as budget
from nightsquad.domain.execution.model import RunKind, RunState
from nightsquad.domain.planning.model import OPEN_SCOPE, RequirementState
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject
from nightsquad.storage.models import Event, LedgerLine, Project, Requirement, Run, Task


def subject(project: Project) -> Subject:
    return Subject(Scope.PROJECT, project.id, project.type)


BIAS_SAMPLE = 12  # PLN-3: the 12 most recently settled requirements
BIAS_MIN_SAMPLE = 2  # PLN-3: at least 2 needed
PROJECT_RUNS_NEEDED = 5  # PLN-3: on this project once 5 runs exist


def bias_multiplier(settled: list[tuple[int, int]]) -> float:
    """Actual runs over estimated runs across recently settled requirements, never below 1
    (PLN-3). `settled` is (estimate, actual) pairs, newest first."""
    sample = [(estimate, actual) for estimate, actual in settled[:BIAS_SAMPLE] if estimate > 0]
    if len(sample) < BIAS_MIN_SAMPLE:
        return 1.0
    return max(1.0, sum(actual for _, actual in sample) / sum(estimate for estimate, _ in sample))


def adjusted_runs(estimate: int, multiplier: float) -> int:
    return math.ceil(estimate * multiplier)


@dataclass(frozen=True)
class Plan:
    """The plan's numbers at one moment."""

    multiplier: float
    tokens_per_run: int | None
    tokens_per_run_from: str
    remaining_runs: int
    unestimated: int

    @property
    def tokens(self) -> int | None:
        """Plan tokens (PLN-3), or None when tokens per run are unknown."""
        return None if self.tokens_per_run is None else self.remaining_runs * self.tokens_per_run

    def tokens_text(self) -> str:
        if self.tokens is None:
            return "unknown: no work run has finished on this install yet"
        return (
            f"{self.tokens:,} tokens ({self.remaining_runs} runs x {self.tokens_per_run:,} "
            f"tokens per run, measured on {self.tokens_per_run_from})"
        )


async def _tokens_of_runs(session: AsyncSession, project_id: str | None) -> list[int]:
    wanted = (
        select(func.coalesce(func.sum(LedgerLine.counted), 0))
        .select_from(Run)
        .outerjoin(LedgerLine, LedgerLine.run_id == Run.id)
        .where(Run.kind == RunKind.WORK, Run.state == RunState.FINISHED)
        .group_by(Run.id)
    )
    if project_id is not None:
        wanted = wanted.where(Run.project_id == project_id)
    return [int(value) for value in await session.scalars(wanted)]


async def tokens_per_run(session: AsyncSession, project: Project) -> tuple[int | None, str]:
    """Median tokens per work run: on this project once 5 runs exist, otherwise on this
    install, otherwise unknown (PLN-3)."""
    here = await _tokens_of_runs(session, project.id)
    if len(here) >= PROJECT_RUNS_NEEDED:
        return int(statistics.median(here)), "this project"
    everywhere = await _tokens_of_runs(session, None)
    if everywhere:
        return int(statistics.median(everywhere)), "this install"
    return None, "nothing yet"


async def runs_spent(session: AsyncSession, requirement: Requirement) -> int:
    """The work runs that have changed a task under this requirement."""
    task_ids = [
        str(task_id)
        for task_id in await session.scalars(
            select(Task.id).where(Task.requirement_id == requirement.id)
        )
    ]
    if not task_ids:
        return 0
    found = await session.scalar(
        select(func.count(func.distinct(Event.via))).where(
            Event.project_id == requirement.project_id,
            Event.subject_kind == "task",
            Event.subject_id.in_(task_ids),
            Event.via.like("run:%"),
        )
    )
    return int(found or 0)


async def tokens_spent(session: AsyncSession, requirement: Requirement) -> int:
    """The tokens of the runs that changed a task under this requirement."""
    task_ids = [
        str(task_id)
        for task_id in await session.scalars(
            select(Task.id).where(Task.requirement_id == requirement.id)
        )
    ]
    if not task_ids:
        return 0
    vias = await session.scalars(
        select(func.distinct(Event.via)).where(
            Event.project_id == requirement.project_id,
            Event.subject_kind == "task",
            Event.subject_id.in_(task_ids),
            Event.via.like("run:%"),
        )
    )
    run_ids = [via.removeprefix("run:") for via in vias]
    if not run_ids:
        return 0
    found = await session.scalar(
        select(func.coalesce(func.sum(LedgerLine.counted), 0)).where(LedgerLine.run_id.in_(run_ids))
    )
    return int(found or 0)


async def multiplier_of(session: AsyncSession, project: Project) -> float:
    rows = await session.execute(
        select(Requirement.estimate_runs, Requirement.actual_runs)
        .where(
            Requirement.project_id == project.id,
            Requirement.state == RequirementState.MET,
            Requirement.estimate_runs.is_not(None),
            Requirement.actual_runs.is_not(None),
        )
        .order_by(Requirement.met_at.desc())
        .limit(BIAS_SAMPLE)
    )
    return bias_multiplier([(int(e or 0), int(a or 0)) for e, a in rows.all()])


async def plan(session: AsyncSession, project: Project, *, including: int = 0) -> Plan:
    """The plan now: remaining adjusted runs of all open accepted scope, plus `including`
    estimated runs of a requirement about to be accepted."""
    multiplier = await multiplier_of(session, project)
    per_run, source = await tokens_per_run(session, project)
    open_scope = list(
        await session.scalars(
            select(Requirement).where(
                Requirement.project_id == project.id, Requirement.state.in_(OPEN_SCOPE)
            )
        )
    )
    remaining = adjusted_runs(including, multiplier) if including else 0
    unestimated = 0
    for requirement in open_scope:
        if requirement.estimate_runs is None:
            unestimated += 1
            continue
        spent = await runs_spent(session, requirement)
        remaining += max(adjusted_runs(requirement.estimate_runs, multiplier) - spent, 1)
    return Plan(multiplier, per_run, source, remaining, unestimated)


@dataclass(frozen=True)
class Fit:
    fits: bool
    arithmetic: str


async def fits_budget(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    now: datetime,
    *,
    including: int,
) -> Fit:
    """PLN-3: whether the plan, with `including` more estimated runs, fits in the tokens
    left before `budget.wrapup_at`. When tokens per run are unknown, nothing is refused."""
    state = await budget.state(session, settings, project, now)
    numbers = await plan(session, project, including=including)
    left = max(state.wrapup_at - state.spent, 0)
    if numbers.tokens is None:
        return Fit(True, f"Plan tokens are {numbers.tokens_text()}.")
    arithmetic = (
        f"The plan would need {numbers.tokens_text()}, and {left:,} tokens are left before "
        f"wrap-up ({state.wrapup_at:,} of the {state.wall:,} budget, with {state.spent:,} spent)."
    )
    return Fit(numbers.tokens <= left, arithmetic)
