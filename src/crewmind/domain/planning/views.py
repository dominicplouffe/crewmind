"""What the plan looks like to a person or an agent: one shape for both (P11)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.refusal import Refusal
from crewmind.domain.budget import service as budget
from crewmind.domain.planning import (
    commitments,
    estimates,
    projection,
    readiness,
    requirements,
    reserve,
)
from crewmind.domain.planning.model import RequirementTest
from crewmind.domain.planning.rules import PLN_1
from crewmind.domain.projects.model import ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.domain.work import checks, tasks
from crewmind.storage.models import (
    Gap,
    GapReview,
    Project,
    RaiseRequest,
    Requirement,
    ReserveDraw,
)

TEXT_MIN_CHARACTERS = 10  # PLN-1: a requirement says what will be true
ESTIMATE_MOST = 10_000  # PLN-3: an estimate is a count of runs


class RequirementInput(BaseModel):
    text: str = Field(min_length=TEXT_MIN_CHARACTERS, max_length=2000, description="The scope.")
    test_kind: RequirementTest = Field(
        description="command (the platform runs it), observable (someone gives a verdict) "
        "or metric (the platform reads a number)."
    )
    success_test: str = Field(
        max_length=4000,
        description="A command that exits 0 when it is met, or what a reviewer will see.",
    )
    test_files: list[str] = Field(
        default_factory=list[str],
        description="For a command test: the workspace files the command uses. They are pinned.",
    )
    estimate_runs: int | None = Field(
        default=None, ge=1, le=ESTIMATE_MOST, description="How many work runs it will take."
    )
    stage: int = Field(default=1, ge=1, le=99, description="Its stage. Lower stages go first.")
    depends_on: list[int] = Field(
        default_factory=list[int], description="Requirements that must be met first."
    )
    recurring: bool = Field(default=False, description="Operate only: it is due again every cycle.")


class RequirementItem(BaseModel):
    id: int
    text: str
    author: str = Field(description="chairman or ceo.")
    state: str
    test_kind: str
    success_test: str
    estimate_runs: int | None
    adjusted_runs: int | None = Field(description="The estimate times the bias multiplier.")
    actual_runs: int | None
    stage: int
    depends_on: list[int]
    recurring: bool
    ready: bool = Field(description="Whether work may be created under it now.")
    not_ready_because: str | None
    failures: int
    ruling: str | None
    ruling_note: str | None
    reason: str | None


class PlanNumbers(BaseModel):
    bias_multiplier: float = Field(description="Actual over estimated runs, never below 1.")
    remaining_runs: int = Field(description="Adjusted runs of all open accepted scope.")
    tokens_per_run: int | None
    plan_tokens: int | None
    plan_tokens_text: str
    tokens_before_wrapup: int = Field(description="Tokens left before wrap-up mode.")
    unestimated: int = Field(description="Open requirements with no estimate.")


class PaceView(BaseModel):
    projection: str = Field(description="When the open scope will be done, in words.")
    projection_kind: str = Field(description="measured, best case, unknown or nothing left.")
    projected_at: datetime | None
    throughput: float | None = Field(description="Work runs per active hour, once measured.")
    burn_rate: int | None = Field(description="Median tokens per active hour, once measured.")
    projected_spend: int | None = Field(description="Spend so far plus plan tokens.")


class CommitmentView(BaseModel):
    id: int
    state: str
    date: datetime | None
    projected_at: datetime | None
    beside_projection: str | None = Field(description="The date, the projection and the gap.")
    resets: int
    reason: str | None


class TargetView(BaseModel):
    date: datetime
    source: str
    beside_projection: str = Field(description="The target, the projection and the gap.")


class DrawView(BaseModel):
    id: int
    state: str = Field(description="requested, drawn, denied or cancelled.")
    tokens: int
    reason: str
    arithmetic: str
    drawn_by: str
    at: datetime


class ReserveView(BaseModel):
    size: int = Field(description="Tokens in the reserve; 0 when it is off.")
    can_draw: bool
    arithmetic: str
    draws: list[DrawView]


class RaiseView(BaseModel):
    id: int
    what: str
    amount: int
    arithmetic: str
    if_declined: str
    state: str
    granted: int | None


class GapView(BaseModel):
    id: int
    text: str
    must_fix: bool
    reason: str
    state: str = Field(description="open, noted, closed or waived.")
    waived_reason: str | None
    requirement_id: int | None


class PlanView(BaseModel):
    requirements: list[RequirementItem]
    lowest_open_stage: int | None
    numbers: PlanNumbers
    pace: PaceView
    commitment: CommitmentView | None
    target: TargetView | None
    reserve: ReserveView
    raises: list[RaiseView]
    gaps: list[GapView]
    gap_review: str = Field(description="not asked, waiting for the reviewer, or filed.")
    note: str | None = Field(default=None, description="What the last change means.")


async def item(
    session: AsyncSession, requirement: Requirement, graph: dict[int, set[int]], multiplier: float
) -> RequirementItem:
    problem = await readiness.why_not_ready(session, requirement)
    return RequirementItem(
        id=requirement.id,
        text=requirement.text,
        author=requirement.author_kind,
        state=requirement.state,
        test_kind=requirement.test_kind,
        success_test=requirement.success_test,
        estimate_runs=requirement.estimate_runs,
        adjusted_runs=None
        if requirement.estimate_runs is None
        else estimates.adjusted_runs(requirement.estimate_runs, multiplier),
        actual_runs=requirement.actual_runs,
        stage=requirement.stage,
        depends_on=sorted(graph.get(requirement.id, set())),
        recurring=requirement.recurring,
        ready=problem is None,
        not_ready_because=problem[1] if problem else None,
        failures=requirement.failures,
        ruling=requirement.ruling,
        ruling_note=requirement.ruling_note,
        reason=requirement.reason,
    )


async def numbers_of(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> PlanNumbers:
    numbers = await estimates.plan(session, project)
    state = await budget.state(session, settings, project, now)
    return PlanNumbers(
        bias_multiplier=round(numbers.multiplier, 2),
        remaining_runs=numbers.remaining_runs,
        tokens_per_run=numbers.tokens_per_run,
        plan_tokens=numbers.tokens,
        plan_tokens_text=numbers.tokens_text(),
        tokens_before_wrapup=max(state.wrapup_at - state.spent, 0),
        unestimated=numbers.unestimated,
    )


async def plan_view(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    now: datetime,
    note: str | None = None,
) -> PlanView:
    rows = list(
        await session.scalars(
            select(Requirement).where(Requirement.project_id == project.id).order_by(Requirement.id)
        )
    )
    graph = await requirements.dependency_graph(session, project.id)
    numbers = await numbers_of(session, settings, project, now)
    pace = await projection.pace(session, settings, project, now)
    commitment = await commitments.latest(session, project.id)
    target = await commitments.target(session, project.id)
    found = await reserve.eligibility(session, settings, project, now)
    draws = await session.scalars(
        select(ReserveDraw).where(ReserveDraw.project_id == project.id).order_by(ReserveDraw.id)
    )
    asked = await session.scalars(
        select(RaiseRequest).where(RaiseRequest.project_id == project.id).order_by(RaiseRequest.id)
    )
    gaps = (
        await session.execute(
            select(Gap, Requirement.id)
            .outerjoin(Requirement, Requirement.gap_id == Gap.id)
            .where(Gap.project_id == project.id)
            .order_by(Gap.id)
        )
    ).all()
    reviews = list(
        await session.scalars(select(GapReview).where(GapReview.project_id == project.id))
    )
    review = (
        "not asked"
        if not reviews
        else "waiting for the reviewer"
        if any(one.filed_at is None for one in reviews)
        else "filed"
    )
    return PlanView(
        requirements=[await item(session, row, graph, numbers.bias_multiplier) for row in rows],
        lowest_open_stage=await readiness.lowest_open_stage(session, project.id),
        numbers=numbers,
        pace=PaceView(
            projection=pace.projection.text(),
            projection_kind=pace.projection.kind,
            projected_at=pace.projection.at,
            throughput=None if pace.throughput is None else round(pace.throughput, 2),
            burn_rate=pace.burn_rate,
            projected_spend=pace.projected_spend,
        ),
        commitment=None
        if commitment is None
        else CommitmentView(
            id=commitment.id,
            state=commitment.state,
            date=commitment.date,
            projected_at=commitment.projected,
            beside_projection=None
            if commitment.date is None
            else commitments.gap_text(commitment.date, pace.projection.at),
            resets=commitment.resets,
            reason=commitment.reason,
        ),
        target=None
        if target is None
        else TargetView(
            date=target.date,
            source=target.source,
            beside_projection=commitments.gap_text(target.date, pace.projection.at),
        ),
        reserve=ReserveView(
            size=found.tokens,
            can_draw=found.ok,
            arithmetic=found.arithmetic,
            draws=[
                DrawView(
                    id=row.id,
                    state=row.state,
                    tokens=row.tokens,
                    reason=row.reason,
                    arithmetic=row.arithmetic,
                    drawn_by=row.drawn_by,
                    at=row.at,
                )
                for row in draws
            ],
        ),
        raises=[
            RaiseView(
                id=row.id,
                what=row.what,
                amount=row.amount,
                arithmetic=row.arithmetic,
                if_declined=row.if_declined,
                state=row.state,
                granted=row.granted,
            )
            for row in asked
        ],
        gaps=[
            GapView(
                id=gap.id,
                text=gap.text,
                must_fix=gap.must_fix,
                reason=gap.reason,
                state=gap.state,
                waived_reason=gap.waived_reason,
                requirement_id=requirement_id,
            )
            for gap, requirement_id in gaps
        ],
        gap_review=review,
        note=note,
    )


async def pin_files(project_id: str, payload: RequirementInput, services: Any) -> checks.Pinned:
    """Read the test files a command requirement names, before the transaction."""
    workspace = Path(services.data_dir) / "workspaces" / project_id
    names = payload.test_files if payload.test_kind == RequirementTest.COMMAND else []
    files, missing = checks.read_test_files(workspace, names)
    return checks.Pinned(files, missing, None)


def new_requirement(
    project: Project, payload: RequirementInput, pinned: checks.Pinned, blobs: Any
) -> requirements.NewRequirement:
    """Check what a requirement says about itself, whoever writes it."""
    if len(payload.success_test.strip()) < tasks.TEST_MIN_CHARACTERS:
        raise Refusal(
            "success_test_too_short",
            f"A success test has at least {tasks.TEST_MIN_CHARACTERS} characters, so that "
            "someone else can tell whether the requirement is met.",
            rule=PLN_1.id,
            hint="Say what will be true, or give the command that shows it.",
        )
    if payload.test_kind == RequirementTest.COMMAND and checks.cannot_fail(payload.success_test):
        raise Refusal(
            "test_cannot_fail",
            "This command passes whatever the work is, so it tests nothing.",
            rule=PLN_1.id,
        )
    if pinned.missing:
        raise Refusal(
            "test_files_missing",
            f"These test files are not in the workspace: {', '.join(pinned.missing)}.",
            rule=PLN_1.id,
            hint="Write the test files first.",
        )
    if payload.recurring and project.type != ProjectType.OPERATE:
        raise Refusal(
            "recurring_is_for_operate",
            "Only an Operate project has recurring requirements.",
            rule=PLN_1.id,
        )
    if payload.test_kind == RequirementTest.METRIC:
        raise Refusal(
            "metric_needs_a_source",
            "A metric requirement names where its number is read. Add it with the metric "
            "operation.",
            rule=PLN_1.id,
        )
    return requirements.NewRequirement(
        text=payload.text,
        test_kind=payload.test_kind,
        success_test=payload.success_test,
        test_files=checks.stored(pinned, blobs),
        estimate_runs=payload.estimate_runs,
        stage=payload.stage,
        depends_on=payload.depends_on,
        recurring=payload.recurring,
    )
