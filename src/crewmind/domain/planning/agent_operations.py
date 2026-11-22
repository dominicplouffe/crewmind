"""What agents do to the plan through the agent API (IF-6.3, PLN-1, PLN-10). The CEO
acts within the authority the project's settings give it; a reviewer seat gives verdicts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.domain.execution.agent import AgentView, agent_of
from crewmind.domain.execution.agent_operations import work_run_only
from crewmind.domain.execution.model import SeatKind
from crewmind.domain.planning import acceptance, plan_view, readiness, requirements, views
from crewmind.domain.planning.authority import actor_of
from crewmind.domain.planning.model import RequirementTest
from crewmind.domain.planning.plan_view import PlanView
from crewmind.domain.planning.rules import PLN_1, PLN_10
from crewmind.domain.planning.views import RequirementInput
from crewmind.domain.work import checks
from crewmind.services import services_of
from crewmind.storage.models import Task

AGENT = frozenset({Principal.AGENT_RUN})

new_scope_hooks: list[Any] = []
"""Called as `(session, project)` before the CEO proposes a requirement or opens a bet.
One that raises a refusal stops it (FND-16)."""


class RequirementRef(BaseModel):
    requirement_id: int = Field(description="The requirement's id, from agent_plan.")


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


async def _plan(context: Context, view: AgentView, note: str | None = None) -> PlanView:
    return await plan_view.plan_view(
        context.session, services_of(context).settings, view.project, context.now, note
    )


async def _prepare(caller: Any, payload: RequirementInput, services: Any) -> Any:
    return await views.pin_files(str(caller.project_id), payload, services)


@operation(
    "agent.plan",
    summary="Read the plan: requirements, what is ready for work, and the plan's numbers.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def plan(context: Context, payload: Empty) -> PlanView:
    """PLN-1, PLN-2, PLN-3."""
    return await _plan(context, await agent_of(context))


@operation(
    "agent.propose_requirement",
    summary="Propose a requirement, with an estimate in runs. It is not scope until accepted.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
    prepare=_prepare,
)
async def propose_requirement(context: Context, payload: RequirementInput) -> PlanView:
    """PLN-1, GOV-3: the CEO proposes; whoever holds plan authority accepts."""
    view = await agent_of(context)
    work_run_only(view)
    for hook in new_scope_hooks:
        await hook(context.session, view.project)
    if payload.estimate_runs is None:
        raise Refusal(
            "proposal_needs_an_estimate",
            "A proposal carries an estimate in runs, so the plan can be checked against "
            "the budget.",
            rule=PLN_1.id,
            hint="Give `estimate_runs`.",
        )
    services = services_of(context)
    if payload.test_kind == RequirementTest.COMMAND and checks.unsafe_host(
        services.checks, services.allow_agent_checks_unisolated
    ):
        raise Refusal(
            "checks_not_allowed_here",
            "This host runs agents unisolated and holds a container-runtime socket, so a "
            "command test an agent wrote is not run on it.",
            rule=checks.WRK_7.id,
            hint="Use an observable test, or ask the operator to allow agent checks.",
        )
    new = views.new_requirement(view.project, payload, context.prepared, services.blobs)
    requirement = await requirements.propose(
        context.session, services.settings, view.project, actor_of(context.caller), new, context.now
    )
    return await _plan(
        context,
        view,
        f"Requirement {requirement.id} is proposed. No work may be created under it until "
        "it is accepted.",
    )


@operation(
    "agent.accept_requirement",
    summary="Accept a proposed requirement into scope, if you hold plan authority.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def accept_requirement(context: Context, payload: RequirementRef) -> PlanView:
    """PLN-1, PLN-3: refused when the chairman holds plan authority, or when the plan
    would not fit the budget."""
    view = await agent_of(context)
    work_run_only(view)
    requirement = await readiness.get(context.session, view.project.id, payload.requirement_id)
    fit = await requirements.accept(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        requirement,
        context.now,
    )
    return await _plan(context, view, fit.arithmetic)


@operation(
    "agent.decline_requirement",
    summary="Decline a proposed requirement, with a reason, if you hold plan authority.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def decline_requirement(context: Context, payload: ReasonInput) -> PlanView:
    """PLN-1, 7.2."""
    view = await agent_of(context)
    work_run_only(view)
    requirement = await readiness.get(context.session, view.project.id, payload.requirement_id)
    await requirements.decline(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        requirement,
        payload.reason,
        context.now,
    )
    return await _plan(context, view)


@operation(
    "agent.cut_requirement",
    summary="Cut a requirement you wrote from scope, with a reason. Its open tasks are killed.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def cut_requirement(context: Context, payload: ReasonInput) -> PlanView:
    """PLN-1, P7: never a chairman-authored requirement."""
    view = await agent_of(context)
    work_run_only(view)
    requirement = await readiness.get(context.session, view.project.id, payload.requirement_id)
    killed = await requirements.cut(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        requirement,
        payload.reason,
        context.now,
    )
    note = f"{killed} open tasks under it were killed." if killed else None
    return await _plan(context, view, note)


@operation(
    "agent.reopen_requirement",
    summary="Reopen a met or cut requirement you wrote.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def reopen_requirement(context: Context, payload: RequirementRef) -> PlanView:
    """PLN-1, 7.2."""
    view = await agent_of(context)
    work_run_only(view)
    requirement = await readiness.get(context.session, view.project.id, payload.requirement_id)
    await requirements.reopen(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        requirement,
        context.now,
    )
    return await _plan(context, view)


@operation(
    "agent.change_requirement",
    summary="Reword, re-estimate or restage a requirement, or change what it depends on.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def change_requirement(context: Context, payload: ChangeInput) -> PlanView:
    """PLN-1, PLN-2, INV-19, P7."""
    view = await agent_of(context)
    work_run_only(view)
    requirement = await readiness.get(context.session, view.project.id, payload.requirement_id)
    await requirements.change(
        context.session,
        services_of(context).settings,
        view.project,
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
    return await _plan(context, view)


@operation(
    "agent.rule_requirement",
    summary="As a reviewer, give your verdict on a requirement that is waiting for one.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def rule_requirement(context: Context, payload: RuleInput) -> PlanView:
    """PLN-10, P5: only a reviewer seat, and only where reviewers hold verdict authority.
    The CEO never rules on its own scope."""
    view = await agent_of(context)
    work_run_only(view)
    if view.seat.kind != SeatKind.REVIEWER:
        raise Refusal(
            "not_a_reviewer",
            "Only a reviewer seat gives a verdict on a requirement. Nobody marks their own "
            "scope met.",
            rule=PLN_10.id,
            hint="Finish the work; the platform asks a reviewer.",
        )
    requirement = await readiness.get(context.session, view.project.id, payload.requirement_id)
    did_the_work = await context.session.scalar(
        select(Task.id)
        .where(Task.requirement_id == requirement.id, Task.claimant_id == view.seat.id)
        .limit(1)
    )
    if did_the_work is not None:
        raise Refusal(
            "you_did_this_work",
            "You did work under this requirement, so another reviewer gives its verdict.",
            rule=PLN_10.id,
        )
    await acceptance.rule(
        context.session,
        services_of(context).settings,
        view.project,
        requirement,
        passed=payload.passed,
        note=payload.note,
        by=context.caller,
        holder=acceptance.REVIEWER,
        now=context.now,
    )
    return await _plan(context, view)
