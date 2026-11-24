"""What the chairman does about dates, budget requests and finishing a project (PLN-6 to
PLN-9, GOV-5, GOV-10, PRJ-4, PRJ-6, WRK-11, IF-3.8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import PERSON_AND_MCP, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.planning import commitments, completion, plan_view, raises, reserve
from nightsquad.domain.planning.authority import actor_of
from nightsquad.domain.planning.plan_view import PlanView
from nightsquad.domain.projects.access import view_of
from nightsquad.domain.projects.operations import ProjectRef
from nightsquad.services import services_of


class AcceptDateInput(ProjectRef):
    date: datetime | None = Field(
        default=None, description="A later date of your own. Leave out to take the projection."
    )


class ReasonInput(ProjectRef):
    reason: str = Field(max_length=2000, description="Why.")


class DateInput(ProjectRef):
    date: datetime = Field(description="The new date.")


class TargetInput(ProjectRef):
    date: datetime | None = Field(default=None, description="The date; leave out to clear it.")
    source: str = Field(
        default="", max_length=500, description="Where it comes from: a fact or your wish."
    )


class DrawRef(ProjectRef):
    draw_id: int = Field(description="The draw's id, from `plan show`.")


class DrawAnswerInput(DrawRef):
    approve: bool = Field(description="Whether the CEO may draw the reserve.")


class RaiseAnswerInput(ProjectRef):
    request_id: int = Field(description="The request's id, from `plan show`.")
    approve: bool = Field(description="Whether to grant a raise.")
    amount: int | None = Field(
        default=None, ge=1, description="Grant this number instead of the one asked for."
    )


class WaiveInput(ProjectRef):
    gap_id: int = Field(description="The gap's id, from `plan show`.")
    reason: str = Field(max_length=2000, description="Why the gap does not need closing.")


class Receipt(BaseModel):
    completed: bool
    receipt: dict[str, Any] | None = Field(
        description="Per requirement estimated and actual runs and tokens, total tokens by "
        "kind, any reserve drawn, where the time went, and whether the commitment was kept."
    )


async def _plan(context: Context, note: str | None = None) -> PlanView:
    return await plan_view.plan_view(
        context.session, services_of(context).settings, view_of(context).project, context.now, note
    )


@operation(
    "commitments.accept",
    summary="Accept the proposed commitment, at the projection or a later date of your own.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def accept_commitment(context: Context, payload: AcceptDateInput) -> PlanView:
    """PLN-6: accepting fixes the settings version and the scope in force."""
    await commitments.accept(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        actor_of(context.caller),
        context.now,
        date=payload.date,
    )
    return await _plan(context)


@operation(
    "commitments.decline",
    summary="Decline the proposed commitment, with a reason.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def decline_commitment(context: Context, payload: ReasonInput) -> PlanView:
    """PLN-6, 7.6."""
    await commitments.decline(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        actor_of(context.caller),
        payload.reason,
        context.now,
    )
    return await _plan(context)


@operation(
    "commitments.move",
    summary="Move the commitment's date. It is re-projected at once.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def move_commitment(context: Context, payload: DateInput) -> PlanView:
    """PLN-8: only the chairman moves a commitment's date."""
    await commitments.move_date(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        actor_of(context.caller),
        payload.date,
        context.now,
    )
    return await _plan(context)


@operation(
    "commitments.reset",
    summary="Reset an at-risk or breached commitment to the current projection.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def reset_commitment(context: Context, payload: ProjectRef) -> PlanView:
    """PLN-6: each reset shows the running count."""
    row = await commitments.reset(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        actor_of(context.caller),
        context.now,
    )
    return await _plan(context, f"This is reset number {row.resets}.")


@operation(
    "plan.set_target",
    summary="Set or clear the date you would like, with where it comes from.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_target(context: Context, payload: TargetInput) -> PlanView:
    """PLN-9: a target is stored with its source and always shown beside the projection."""
    if payload.date is not None and not payload.source.strip():
        raise Refusal(
            "target_needs_a_source",
            "Say where the date comes from: an outside fact, or your own wish.",
            kind=RefusalKind.INVALID,
        )
    await commitments.set_target(
        context.session,
        view_of(context).project,
        actor_of(context.caller),
        payload.date,
        payload.source,
        context.now,
    )
    return await _plan(context)


@operation(
    "reserve.answer",
    summary="Approve or deny the CEO's request to draw the CEO reserve.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def answer_draw(context: Context, payload: DrawAnswerInput) -> PlanView:
    """GOV-10: under supervised authority a draw waits for the chairman."""
    project = view_of(context).project
    row = await reserve.get(context.session, project.id, payload.draw_id)
    await reserve.answer(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        row,
        payload.approve,
        context.now,
    )
    return await _plan(context)


@operation(
    "reserve.cancel",
    summary="Cancel a reserve draw. If spend is past the budget, the project pauses.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def cancel_draw(context: Context, payload: DrawRef) -> PlanView:
    """GOV-10: the chairman can cancel a draw at any time."""
    project = view_of(context).project
    row = await reserve.get(context.session, project.id, payload.draw_id)
    await reserve.cancel(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        row,
        context.now,
    )
    return await _plan(context)


@operation(
    "raises.answer",
    summary="Approve or decline the CEO's request for a higher budget or concurrency.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def answer_raise(context: Context, payload: RaiseAnswerInput) -> PlanView:
    """GOV-5: approving applies the change; a yes never lowers anything."""
    project = view_of(context).project
    row = await raises.get(context.session, project.id, payload.request_id)
    await raises.answer(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        row,
        approve=payload.approve,
        amount=payload.amount,
        now=context.now,
    )
    return await _plan(context)


@operation(
    "gaps.waive",
    summary="Waive a gap from the final gap review, with a reason.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def waive_gap(context: Context, payload: WaiveInput) -> PlanView:
    """WRK-11: only the chairman waives a gap."""
    await completion.waive(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        actor_of(context.caller),
        payload.gap_id,
        payload.reason,
        context.now,
    )
    return await _plan(context)


@operation(
    "projects.sign_off",
    summary="Sign off a ready project. It is completed and its receipt is written.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def sign_off(context: Context, payload: ProjectRef) -> Receipt:
    """PRJ-4."""
    written = await completion.sign_off(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        actor_of(context.caller),
        context.now,
    )
    return Receipt(completed=True, receipt=written)


@operation(
    "projects.reopen",
    summary="Reopen a completed project, within its reopen window.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def reopen(context: Context, payload: ProjectRef) -> Receipt:
    """PRJ-6: after `reopen.window` the answer is to clone it."""
    project = view_of(context).project
    await completion.reopen(
        context.session,
        services_of(context).settings,
        project,
        actor_of(context.caller),
        context.now,
    )
    return Receipt(
        completed=False, receipt=await completion.receipt_of(context.session, project.id)
    )


@operation(
    "projects.receipt",
    summary="Show a completed project's receipt.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_receipt(context: Context, payload: ProjectRef) -> Receipt:
    """PRJ-4."""
    project = view_of(context).project
    written = await completion.receipt_of(context.session, project.id)
    return Receipt(completed=project.state == "completed", receipt=written)
