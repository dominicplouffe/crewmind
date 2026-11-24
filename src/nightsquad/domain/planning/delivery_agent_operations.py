"""What agents do about dates, the reserve, raises and the final gap review (IF-6.3,
PLN-6, GOV-5, GOV-10, WRK-11). No request here carries a date."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.domain.execution.agent import AgentView, agent_of
from nightsquad.domain.execution.agent_operations import work_run_only
from nightsquad.domain.planning import commitments, completion, plan_view, raises, reserve
from nightsquad.domain.planning.authority import actor_of
from nightsquad.domain.planning.plan_view import PlanView
from nightsquad.services import services_of

AGENT = frozenset({Principal.AGENT_RUN})


class DrawInput(BaseModel):
    reason: str = Field(max_length=2000, description="What the reserve will finish.")


class RaiseInput(BaseModel):
    what: Literal["budget", "concurrency"] = Field(description="budget or concurrency.")
    amount: int = Field(ge=1, description="The new value you ask for.")
    if_declined: str = Field(max_length=2000, description="What happens if it is declined.")


class GapInput(BaseModel):
    text: str = Field(min_length=10, max_length=2000, description="What is missing or wrong.")
    must_fix: bool = Field(description="True for must-fix, false for nice-to-have.")
    reason: str = Field(max_length=2000, description="Why it matters against the goal.")


class GapReviewInput(BaseModel):
    gaps: list[GapInput] = Field(
        default_factory=list[GapInput], max_length=30, description="Every gap; empty for none."
    )


async def _plan(context: Context, view: AgentView, note: str | None = None) -> PlanView:
    return await plan_view.plan_view(
        context.session, services_of(context).settings, view.project, context.now, note
    )


@operation(
    "agent.propose_commitment",
    summary="Propose a commitment. It has no date field: the date is the platform's projection.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def propose_commitment(context: Context, payload: Empty) -> PlanView:
    """PLN-6: once a projection exists, one at a time."""
    view = await agent_of(context)
    work_run_only(view)
    await commitments.propose(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        context.now,
    )
    return await _plan(context, view)


@operation(
    "agent.accept_commitment",
    summary="Accept the proposed commitment at the projection, if you hold date authority.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def accept_commitment(context: Context, payload: Empty) -> PlanView:
    """PLN-6: the CEO never chooses the date; it is the projection as it is now."""
    view = await agent_of(context)
    work_run_only(view)
    await commitments.accept(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        context.now,
    )
    return await _plan(context, view)


@operation(
    "agent.reset_commitment",
    summary="Reset an at-risk or breached commitment to the current projection.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def reset_commitment(context: Context, payload: Empty) -> PlanView:
    """PLN-6: only to the projection, only while at risk or breached, and counted."""
    view = await agent_of(context)
    work_run_only(view)
    row = await commitments.reset(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        context.now,
    )
    return await _plan(context, view, f"This is reset number {row.resets}.")


@operation(
    "agent.draw_reserve",
    summary="Draw the CEO reserve to finish scope that is nearly done. Once per project.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def draw_reserve(context: Context, payload: DrawInput) -> PlanView:
    """GOV-10: refused with the arithmetic unless the project is in wrap-up and nearly
    done. Where the chairman holds the verb, this asks instead of drawing."""
    view = await agent_of(context)
    work_run_only(view)
    row = await reserve.draw(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        payload.reason,
        context.now,
    )
    note = (
        f"The reserve of {row.tokens:,} tokens is drawn. It finishes existing scope only."
        if row.state == reserve.DRAWN
        else "The chairman has been asked. Nothing is drawn until they approve."
    )
    return await _plan(context, view, note)


@operation(
    "agent.request_raise",
    summary="Ask the chairman for a higher budget or concurrency, saying what happens if not.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def request_raise(context: Context, payload: RaiseInput) -> PlanView:
    """GOV-5: only the CEO asks, and the platform adds the arithmetic."""
    view = await agent_of(context)
    work_run_only(view)
    await raises.request(
        context.session,
        services_of(context).settings,
        view.project,
        actor_of(context.caller),
        what=payload.what,
        amount=payload.amount,
        if_declined=payload.if_declined,
        now=context.now,
    )
    return await _plan(context, view, "The chairman has been asked.")


@operation(
    "agent.file_gap_review",
    summary="As the reviewer asked, file the final gap review: every gap, or an empty list.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def file_gap_review(context: Context, payload: GapReviewInput) -> PlanView:
    """WRK-11: only the reviewer the platform asked, who wrote none of the deliverables."""
    view = await agent_of(context)
    work_run_only(view)
    await completion.file_review(
        context.session,
        view.project,
        view.seat,
        context.caller,
        [completion.NewGap(gap.text, gap.must_fix, gap.reason) for gap in payload.gaps],
        context.now,
    )
    return await _plan(context, view)
