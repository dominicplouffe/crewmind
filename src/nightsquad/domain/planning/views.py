"""What the plan looks like to a person or an agent: one shape for both (P11)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.budget import service as budget
from nightsquad.domain.planning import (
    estimates,
    metrics,
    readiness,
    requirements,
)
from nightsquad.domain.planning.model import RequirementTest
from nightsquad.domain.planning.rules import PLN_1
from nightsquad.domain.projects.model import ProjectType
from nightsquad.domain.settings.service import SettingsService
from nightsquad.domain.work import checks, tasks
from nightsquad.storage.models import (
    Project,
    Requirement,
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
        default="",
        max_length=4000,
        description="A command that exits 0 when it is met, or what a reviewer will see. "
        "Leave out for a metric.",
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
    metric_url: str | None = Field(
        default=None, max_length=2000, description="Metric only: the public page to read."
    )
    metric_pattern: str | None = Field(
        default=None, description="Metric only: a pattern with one group around the number."
    )
    metric_target: float | None = Field(default=None, description="Metric only: the target.")
    metric_at_least: bool = Field(
        default=True, description="Metric only: true to reach the target from below."
    )


class MetricView(BaseModel):
    url: str
    target: float
    at_least: bool
    latest: float | None = Field(description="The newest reading, if one was read.")
    read_at: datetime | None
    failure: str | None = Field(description="Why the newest reading failed, if it did.")
    losing_ground: bool


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
    metric: MetricView | None


class PlanNumbers(BaseModel):
    bias_multiplier: float = Field(description="Actual over estimated runs, never below 1.")
    remaining_runs: int = Field(description="Adjusted runs of all open accepted scope.")
    tokens_per_run: int | None
    plan_tokens: int | None
    plan_tokens_text: str
    tokens_before_wrapup: int = Field(description="Tokens left before wrap-up mode.")
    unestimated: int = Field(description="Open requirements with no estimate.")


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
        metric=await metric_view(session, requirement),
    )


async def metric_view(session: AsyncSession, requirement: Requirement) -> MetricView | None:
    if requirement.metric is None:
        return None
    reading = await metrics.latest(session, requirement.id)
    return MetricView(
        url=str(requirement.metric["url"]),
        target=float(requirement.metric["target"]),
        at_least=bool(requirement.metric["at_least"]),
        latest=reading.value if reading else None,
        read_at=reading.at if reading else None,
        failure=reading.failure if reading else None,
        losing_ground=bool(requirement.metric.get("losing")),
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
    is_metric = payload.test_kind == RequirementTest.METRIC
    if not is_metric and len(payload.success_test.strip()) < tasks.TEST_MIN_CHARACTERS:
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
    metric: dict[str, Any] | None = None
    success_test = payload.success_test
    if is_metric:
        metrics.check_source(payload.metric_url, payload.metric_pattern, payload.metric_target)
        metric = {
            "url": payload.metric_url,
            "pattern": payload.metric_pattern,
            "target": payload.metric_target,
            "at_least": payload.metric_at_least,
        }
        success_test = metrics.describe(metric)
    return requirements.NewRequirement(
        text=payload.text,
        test_kind=payload.test_kind,
        success_test=success_test,
        metric=metric,
        test_files=checks.stored(pinned, blobs),
        estimate_runs=payload.estimate_runs,
        stage=payload.stage,
        depends_on=payload.depends_on,
        recurring=payload.recurring,
    )
