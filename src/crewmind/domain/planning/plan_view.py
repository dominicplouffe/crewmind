"""The whole plan as a person or an agent sees it: one shape for both (P11)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.domain.planning import (
    bets,
    commitments,
    projection,
    readiness,
    requirements,
    reserve,
)
from crewmind.domain.planning.views import PlanNumbers, RequirementItem, item, numbers_of
from crewmind.domain.projects.model import ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.models import (
    Bet,
    Cycle,
    Gap,
    GapReview,
    Project,
    RaiseRequest,
    Requirement,
    ReserveDraw,
)

CYCLES_SHOWN = 12  # the open cycle and the closed ones before it


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


class BetView(BaseModel):
    id: int
    statement: str
    kill_condition: str
    kill_at: datetime
    state: str = Field(description="active, expired, confirmed, killed or inconclusive.")
    extended: bool
    extension_reason: str | None
    finding: str | None = Field(description="The artifact that holds its finding.")


class TimeBoxView(BaseModel):
    started_at: datetime
    ends_at: datetime
    new_bets_until: datetime = Field(description="No new bet opens in the final 20%.")


class CycleView(BaseModel):
    number: int
    state: str = Field(description="open, completed, missed or skipped.")
    opened_at: datetime
    ends_at: datetime
    due_at: datetime
    narrative: str | None
    narrative_by_ceo: bool
    scorecard: dict[str, Any] | None


class PlanView(BaseModel):
    requirements: list[RequirementItem]
    bets: list[BetView]
    time_box: TimeBoxView | None
    cycles: list[CycleView]
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
        **await explore_part(session, settings, project, now),
        cycles=await cycle_part(session, project),
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


async def explore_part(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> dict[str, Any]:
    """The Explore side of the plan: bets and the time box."""
    if project.type != ProjectType.EXPLORE:
        return {"bets": [], "time_box": None}
    rows = await session.scalars(select(Bet).where(Bet.project_id == project.id).order_by(Bet.id))
    box = await bets.time_box(session, settings, project, now)
    return {
        "bets": [
            BetView(
                id=bet.id,
                statement=bet.statement,
                kill_condition=bet.kill_condition,
                kill_at=bet.kill_at,
                state=bet.state,
                extended=bet.extended,
                extension_reason=bet.extension_reason,
                finding=bet.finding,
            )
            for bet in rows
        ],
        "time_box": None
        if box is None
        else TimeBoxView(
            started_at=box[0],
            ends_at=box[1],
            new_bets_until=box[1] - (box[1] - box[0]) * bets.LAST_SHARE,
        ),
    }


async def cycle_part(session: AsyncSession, project: Project) -> list[CycleView]:
    """The Operate side of the plan: the open cycle and the last few closed ones."""
    if project.type != ProjectType.OPERATE:
        return []
    rows = await session.scalars(
        select(Cycle)
        .where(Cycle.project_id == project.id)
        .order_by(Cycle.number.desc())
        .limit(CYCLES_SHOWN)
    )
    return [
        CycleView(
            number=row.number,
            state=row.state,
            opened_at=row.opened_at,
            ends_at=row.ends_at,
            due_at=row.due_at,
            narrative=row.narrative,
            narrative_by_ceo=row.narrative_by_ceo,
            scorecard=row.scorecard,
        )
        for row in reversed(list(rows))
    ]
