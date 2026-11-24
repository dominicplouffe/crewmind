"""Operate operations: the cycle narrative, a cycle's due time, and completing an
operation (PRJ-8, IF-3.8, IF-6.3). No operation rolls a cycle: the platform does."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.domain.execution.agent import agent_of
from nightsquad.domain.execution.agent_operations import work_run_only
from nightsquad.domain.planning import cycles, plan_view
from nightsquad.domain.planning.authority import actor_of
from nightsquad.domain.planning.delivery_operations import Receipt
from nightsquad.domain.planning.plan_view import PlanView
from nightsquad.domain.projects.access import view_of
from nightsquad.domain.projects.operations import ProjectRef
from nightsquad.services import services_of

AGENT = frozenset({Principal.AGENT_RUN})


class NarrativeInput(BaseModel):
    text: str = Field(max_length=10_000, description="What happened this cycle, in plain words.")


class DueInput(ProjectRef):
    due_at: datetime = Field(description="When this cycle's recurring scope is due.")
    source: str = Field(min_length=3, max_length=500, description="Where the time comes from.")


@operation(
    "agent.write_cycle_narrative",
    summary="Write the open cycle's narrative. The platform keeps it word for word.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def write_narrative(context: Context, payload: NarrativeInput) -> PlanView:
    """PRJ-8: the scorecard is the platform's; the narrative is the CEO's."""
    view = await agent_of(context)
    work_run_only(view)
    await cycles.write_narrative(
        context.session, view.project, context.caller, payload.text, context.now
    )
    return await plan_view.plan_view(
        context.session, services_of(context).settings, view.project, context.now
    )


@operation(
    "cycles.set_due",
    summary="Give the open cycle its own due time, with where it comes from.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_due(context: Context, payload: DueInput) -> PlanView:
    """PRJ-8: a cycle-specific due time with a cited source overrides the calendar."""
    project = view_of(context).project
    await cycles.set_due(
        context.session,
        project,
        actor_of(context.caller),
        payload.due_at,
        payload.source,
        context.now,
    )
    return await plan_view.plan_view(
        context.session, services_of(context).settings, project, context.now
    )


@operation(
    "projects.complete",
    summary="Complete an Operate project, with its final scorecard.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def complete(context: Context, payload: ProjectRef) -> Receipt:
    """PRJ-8, R-62: a finished operation is completed, not stopped."""
    written = await cycles.complete_operation(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        actor_of(context.caller),
        context.now,
    )
    return Receipt(completed=True, receipt=written)
