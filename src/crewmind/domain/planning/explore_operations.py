"""Explore operations: bets, findings, ending the project and promoting it (PRJ-7, SPD-7,
7.4, IF-3.8, IF-6.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.registry import catalog
from crewmind.domain.execution.agent import agent_of
from crewmind.domain.execution.agent_operations import work_run_only
from crewmind.domain.planning import bets, completion, plan_view
from crewmind.domain.planning.agent_operations import new_scope_hooks
from crewmind.domain.planning.authority import actor_of
from crewmind.domain.planning.delivery_operations import Receipt
from crewmind.domain.planning.model import BetState
from crewmind.domain.planning.plan_view import PlanView
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.model import ProjectState, ProjectType
from crewmind.domain.projects.operations import ProjectRef
from crewmind.services import services_of

AGENT = frozenset({Principal.AGENT_RUN})


class OpenBetInput(BaseModel):
    statement: str = Field(min_length=10, max_length=2000, description="What you bet is true.")
    kill_condition: str = Field(
        min_length=10, max_length=2000, description="What would show the bet is wrong."
    )
    window_hours: int | None = Field(
        default=None, ge=1, description="Hours until its kill date. Default: `bet.window`."
    )


class FindingInput(BaseModel):
    bet_id: int = Field(description="The bet's id, from agent_plan.")
    result: Literal["confirmed", "killed", "inconclusive"] = Field(
        description="confirmed, killed or inconclusive."
    )
    text: str = Field(max_length=10_000, description="What was found, in plain words.")
    evidence: list[int] = Field(
        default_factory=list[int], description="Ids of verified evidence that supports it."
    )


class ExtendInput(ProjectRef):
    bet_id: int = Field(description="The bet's id, from `plan show`.")
    until: datetime = Field(description="The new kill date.")
    reason: str = Field(max_length=2000, description="Why it gets more time.")


class Promoted(BaseModel):
    drafting_id: str = Field(description="The drafting conversation that was opened.")
    next: str


class PromoteInput(ProjectRef):
    name: str | None = Field(default=None, max_length=200, description="The new project's name.")


@operation(
    "agent.open_bet",
    summary="Open a bet: what you think is true, what would kill it, and for how long.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def open_bet(context: Context, payload: OpenBetInput) -> PlanView:
    """7.4, SPD-7: refused in the final 20% of the time box, in wrap-up, and after a
    reserve draw."""
    view = await agent_of(context)
    work_run_only(view)
    for hook in new_scope_hooks:
        await hook(context.session, view.project)
    settings = services_of(context).settings
    await bets.open_bet(
        context.session,
        settings,
        view.project,
        actor_of(context.caller),
        statement=payload.statement,
        kill_condition=payload.kill_condition,
        window_hours=payload.window_hours,
        now=context.now,
    )
    return await plan_view.plan_view(context.session, settings, view.project, context.now)


@operation(
    "agent.publish_finding",
    summary="End a bet with its finding: confirmed, killed or inconclusive, with evidence.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def publish_finding(context: Context, payload: FindingInput) -> PlanView:
    """PRJ-7: the finding is published as an artifact. Confirmed needs verified evidence."""
    view = await agent_of(context)
    work_run_only(view)
    services = services_of(context)
    bet = await bets.get(context.session, view.project.id, payload.bet_id)
    name = await bets.publish_finding(
        context.session,
        services.settings,
        services.blobs,
        view.project,
        view.seat,
        context.caller,
        bet,
        result=BetState(payload.result),
        text=payload.text,
        evidence=payload.evidence,
        now=context.now,
    )
    return await plan_view.plan_view(
        context.session, services.settings, view.project, context.now, f"Published as {name}."
    )


@operation(
    "bets.extend",
    summary="Give an expired bet more time, once, with a reason.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def extend_bet(context: Context, payload: ExtendInput) -> PlanView:
    """PRJ-7, 7.4: only the chairman, only once, to a future date."""
    project = view_of(context).project
    bet = await bets.get(context.session, project.id, payload.bet_id)
    await bets.extend(
        context.session,
        project,
        actor_of(context.caller),
        bet,
        payload.until,
        payload.reason,
        context.now,
    )
    return await plan_view.plan_view(
        context.session, services_of(context).settings, project, context.now
    )


@operation(
    "projects.end",
    summary="End an Explore project. The platform writes the findings report.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def end_project(context: Context, payload: ProjectRef) -> Receipt:
    """PRJ-7, 7.1: an Explore project ends when the chairman decides, with a findings
    report assembled from the findings as they stand."""
    project = view_of(context).project
    if project.type != ProjectType.EXPLORE:
        raise Refusal(
            "only_explore_ends",
            "Only an Explore project is ended this way. Sign off a Deliver project when it "
            "is ready; complete an Operate project.",
        )
    if project.state not in (ProjectState.RUNNING, ProjectState.HELD):
        raise Refusal("not_running", f"The project is {project.state}; it cannot be ended now.")
    services = services_of(context)
    await bets.assemble_report(
        context.session, services.settings, services.blobs, project, context.now,
        why="the chairman ended the project",
    )  # fmt: skip
    written = await completion.complete(
        context.session, services.settings, project, context.caller, context.now,
        why="ended by the chairman",
    )  # fmt: skip
    return Receipt(completed=True, receipt=written)


@operation(
    "projects.promote",
    summary="Start drafting a Deliver project from an Explore project's findings.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def promote(context: Context, payload: PromoteInput) -> Promoted:
    """PRJ-7: promote to Deliver, through the Founder. A drafting conversation is opened
    with the findings report as its document, so the report is grilled before anything
    is drafted from it. The Deliver project exists once you confirm that draft."""
    project = view_of(context).project
    if project.type != ProjectType.EXPLORE:
        raise Refusal("only_explore_promotes", "Only an Explore project is promoted.")
    services = services_of(context)
    report = await bets.report_text(context.session, services.blobs, project)
    if report is None:
        await bets.assemble_report(
            context.session, services.settings, services.blobs, project, context.now,
            why="the project was promoted to Deliver",
        )  # fmt: skip
        report = await bets.report_text(context.session, services.blobs, project)
    assert report is not None
    name = payload.name or f"{project.name}: deliver"
    start = catalog.get("founder.start")
    drafting: Any = await context.executor.call(
        context,
        start,
        start.input(
            brief=f"Deliver what the Explore project {project.name} found worth building. "
            f"Call the new project {name}. Its findings report is attached.",
            document=report,
        ),
    )
    context.record(
        bets.PROMOTED,
        subject=("project", project.id),
        project_id=project.id,
        after={"drafting": drafting.drafting_id},
    )
    return Promoted(
        drafting_id=drafting.drafting_id,
        next="The Founder will ask about the findings. Carry on with "
        f"`crewmind draft --resume {drafting.drafting_id}`, or in the app.",
    )
