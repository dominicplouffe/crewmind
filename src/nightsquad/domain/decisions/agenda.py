"""The agenda (HUM-12, INV-22): what will happen in the next days, at 0 tokens, from the
same sources the jobs use. Its next time-based wake is the dispatcher's."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.domain.decisions import items, reviews
from nightsquad.domain.decisions.model import ItemState
from nightsquad.domain.execution.heartbeat import next_heartbeat
from nightsquad.domain.execution.model import RunKind, RunState
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.planning import authority, bets, commitments, projection
from nightsquad.domain.settings.service import SettingsService
from nightsquad.storage.models import (
    Bet,
    Cycle,
    DecisionItem,
    HoldReason,
    Project,
    Run,
    Watch,
)


@dataclass(frozen=True)
class Line:
    at: datetime
    what: str
    consequence: str
    wake: bool = False
    """Whether this is a time at which the dispatcher wakes an agent."""


async def next_time_wake(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> datetime | None:
    """INV-22: the next wake that comes from the clock, not from a message: the CEO's
    heartbeat if it will fire, or a queued run's not-before time."""
    times: list[datetime] = []
    if project.state == "running":
        ceo = await ceo_of(session, project.id)
        due, fires = await next_heartbeat(session, settings, project, ceo)
        if fires:
            times.append(max(due, now))
    held_back = await session.scalar(
        select(func.min(Run.not_before)).where(
            Run.project_id == project.id,
            Run.kind == RunKind.WORK,
            Run.state == RunState.QUEUED,
            Run.not_before.is_not(None),
            Run.not_before > now,
        )
    )
    if held_back is not None:
        times.append(held_back)
    return min(times) if times else None


async def build(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    now: datetime,
    days: int,
) -> list[Line]:
    """HUM-12: heartbeats and when they skip, deadlines with their consequences, kill
    dates and the time box, the commitment beside the projection, cycle rolls, review
    dates, watch intervals and the budget reset."""
    until = now + timedelta(days=days)
    found: list[Line] = []
    values = await settings.effective(session, authority.subject(project))
    if project.state == "running":
        ceo = await ceo_of(session, project.id)
        due, fires = await next_heartbeat(session, settings, project, ceo)
        found.append(
            Line(
                max(due, now),
                "The CEO's heartbeat",
                "The CEO is woken to look at what changed."
                if fires
                else "It will skip: nothing has changed since the CEO last ran.",
                wake=fires,
            )
        )
    for run_at in await session.scalars(
        select(Run.not_before).where(
            Run.project_id == project.id,
            Run.state == RunState.QUEUED,
            Run.not_before.is_not(None),
            Run.not_before > now,
        )
    ):
        if run_at is not None:
            found.append(Line(run_at, "A queued run may start", "Its agent is woken.", wake=True))
    for hold in await session.scalars(
        select(HoldReason).where(
            HoldReason.project_id == project.id,
            HoldReason.lifted_at.is_(None),
            HoldReason.lift_at.is_not(None),
        )
    ):
        if hold.lift_at is not None:
            found.append(Line(hold.lift_at, "The hold lifts", "The project resumes by itself."))
    for item in await session.scalars(
        select(DecisionItem).where(
            DecisionItem.project_id == project.id,
            DecisionItem.state == ItemState.OPEN,
            DecisionItem.deadline.is_not(None),
        )
    ):
        if item.deadline is not None:
            found.append(
                Line(
                    item.deadline,
                    f"Deadline: {items.title_of(item)}",
                    f"Unanswered, the outcome is: {item.default_outcome}.",
                )
            )
    for bet in await session.scalars(
        select(Bet).where(Bet.project_id == project.id, Bet.state == "active")
    ):
        found.append(
            Line(bet.kill_at, f"Kill date of bet {bet.id}", "It expires and its tasks block.")
        )
    if project.type == "explore":
        box = await bets.time_box(session, settings, project, now)
        if box is not None:
            found.append(
                Line(box[1], "The time box ends", "The platform assembles the findings report.")
            )
    commitment = await commitments.current(session, project.id)
    if commitment is not None and commitment.date is not None:
        found.append(
            Line(
                commitment.date,
                f"The commitment's date ({commitment.state})",
                "Beside the projection: "
                f"{commitments.gap_text(commitment.date, commitment.projected)}.",
            )
        )
    cycle = await session.scalar(
        select(Cycle).where(Cycle.project_id == project.id, Cycle.state == "open")
    )
    if cycle is not None:
        found.append(
            Line(cycle.due_at, f"Cycle {cycle.number} is due", "Open recurring scope is flagged.")
        )
        found.append(
            Line(cycle.ends_at, f"Cycle {cycle.number} rolls", "It closes with its scorecard.")
        )
    if project.state in ("running", "held", "paused"):
        rows = await reviews.all_reviews(session, project.id)
        last = rows[-1].opened_at if rows else await projection.started_at(session, project.id)
        periodic = not (
            project.type == "operate" and values.get("cycle.period") in reviews.CYCLE_PERIODS
        )
        if last is not None and periodic:
            found.append(
                Line(
                    last + timedelta(seconds=int(values["review.every"])),
                    "The next status review",
                    "The platform builds it at 0 tokens.",
                )
            )
    for watch in await session.scalars(
        select(Watch).where(Watch.project_id == project.id, Watch.state.in_(["passing", "failing"]))
    ):
        last_run = watch.last_run_at or now
        found.append(
            Line(
                max(last_run + timedelta(seconds=watch.interval_seconds), now),
                f"The watch on launch {watch.side_effect_id} runs",
                "A failing watch opens a flag.",
            )
        )
    if project.type == "operate":
        zone = ZoneInfo(str(values["project.timezone"]))
        local = now.astimezone(zone)
        first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        reset = (first + timedelta(days=32)).replace(day=1)
        found.append(
            Line(
                reset.astimezone(now.tzinfo),
                "The monthly budget resets",
                "Spend counts from zero again.",
            )
        )
    return sorted((line for line in found if now <= line.at <= until), key=lambda line: line.at)
