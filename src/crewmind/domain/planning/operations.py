"""What the chairman does to the plan (PLN-1, PLN-3, PLN-10, IF-3.8). Each operation is
the chairman's side of a rule in `requirements` and `acceptance`."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.domain.planning import acceptance, plan_view, readiness, requirements, views
from crewmind.domain.planning.authority import actor_of
from crewmind.domain.planning.plan_view import PlanView
from crewmind.domain.planning.views import RequirementInput
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.services import services_of


class AddInput(ProjectRef, RequirementInput):
    pass


class RequirementRef(ProjectRef):
    requirement_id: int = Field(description="The requirement's id, from `plan show`.")


class AcceptInput(RequirementRef):
    anyway: bool = Field(
        default=False, description="Accept it even though the plan does not fit the budget."
    )


class ReasonInput(RequirementRef):
    reason: str = Field(max_length=2000, description="Why.")


class ChangeInput(RequirementRef):
    text: str | None = Field(default=None, min_length=views.TEXT_MIN_CHARACTERS, max_length=2000)
    success_test: str | None = Field(default=None, max_length=4000)
    estimate_runs: int | None = Field(default=None, ge=1, le=views.ESTIMATE_MOST)
    stage: int | None = Field(default=None, ge=1, le=99)
    depends_on: list[int] | None = Field(
        default=None, description="The full list of requirements it depends on."
    )


class RuleInput(RequirementRef):
    passed: bool = Field(description="Whether the requirement is met.")
    note: str | None = Field(default=None, max_length=2000, description="What you found.")


async def _plan(context: Context, note: str | None = None) -> PlanView:
    return await plan_view.plan_view(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        context.now,
        note,
    )


async def _prepare(caller: Any, payload: AddInput, services: Any) -> Any:
    return await views.pin_files(payload.project_id, payload, services)


@operation(
    "plan.show",
    summary="Show the plan: requirements, what is ready for work, and the plan's numbers.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
    slash_command="/plan",
)
async def show_plan(context: Context, payload: ProjectRef) -> PlanView:
    """PLN-1, PLN-2, PLN-3."""
    return await _plan(context)


@operation(
    "requirements.add",
    summary="Add a requirement to the project's scope. It is accepted at once.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    prepare=_prepare,
)
async def add_requirement(context: Context, payload: AddInput) -> PlanView:
    """PLN-1: the chairman adds scope directly and is recorded as its author."""
    project = view_of(context).project
    new = views.new_requirement(project, payload, context.prepared, services_of(context).blobs)
    await requirements.add(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        new,
        context.now,
    )
    return await _plan(context)


@operation(
    "requirements.accept",
    summary="Accept a proposed requirement into scope.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def accept_requirement(context: Context, payload: AcceptInput) -> PlanView:
    """PLN-1, PLN-3: refused with the arithmetic when the plan would not fit, unless the
    chairman accepts it anyway."""
    project = view_of(context).project
    requirement = await readiness.get(context.session, project.id, payload.requirement_id)
    fit = await requirements.accept(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        requirement,
        context.now,
        anyway=payload.anyway,
    )
    return await _plan(context, fit.arithmetic)


@operation(
    "requirements.decline",
    summary="Decline a proposed requirement, with a reason.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def decline_requirement(context: Context, payload: ReasonInput) -> PlanView:
    """PLN-1, 7.2."""
    project = view_of(context).project
    requirement = await readiness.get(context.session, project.id, payload.requirement_id)
    await requirements.decline(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        requirement,
        payload.reason,
        context.now,
    )
    return await _plan(context)


@operation(
    "requirements.cut",
    summary="Cut a requirement from scope, with a reason. Its open tasks are killed.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def cut_requirement(context: Context, payload: ReasonInput) -> PlanView:
    """PLN-1, 7.2, INV-18."""
    project = view_of(context).project
    requirement = await readiness.get(context.session, project.id, payload.requirement_id)
    killed = await requirements.cut(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        requirement,
        payload.reason,
        context.now,
    )
    return await _plan(context, f"{killed} open tasks under it were killed." if killed else None)


@operation(
    "requirements.reopen",
    summary="Reopen a met or cut requirement.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def reopen_requirement(context: Context, payload: RequirementRef) -> PlanView:
    """PLN-1, 7.2."""
    project = view_of(context).project
    requirement = await readiness.get(context.session, project.id, payload.requirement_id)
    await requirements.reopen(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        requirement,
        context.now,
    )
    return await _plan(context)


@operation(
    "requirements.change",
    summary="Reword, re-estimate or restage a requirement, or change what it depends on.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def change_requirement(context: Context, payload: ChangeInput) -> PlanView:
    """PLN-1, PLN-2, INV-19."""
    project = view_of(context).project
    requirement = await readiness.get(context.session, project.id, payload.requirement_id)
    await requirements.change(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        requirement,
        requirements.Change(
            payload.text,
            payload.success_test,
            payload.estimate_runs,
            payload.stage,
            payload.depends_on,
        ),
        context.now,
    )
    return await _plan(context)


@operation(
    "requirements.rule",
    summary="Give your verdict on a requirement that is waiting for one.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def rule_requirement(context: Context, payload: RuleInput) -> PlanView:
    """PLN-10: the chairman's verdict on an observable requirement. A rejection needs a
    note. The platform writes the state."""
    project = view_of(context).project
    requirement = await readiness.get(context.session, project.id, payload.requirement_id)
    await acceptance.rule(
        context.session,
        services_of(context).settings,
        project,
        requirement,
        passed=payload.passed,
        note=payload.note,
        by=context.caller,
        holder=acceptance.CHAIRMAN,
        now=context.now,
    )
    return await _plan(context)
