"""Throughput, projection and burn rate (PLN-4, PLN-5, GOV-4). The arithmetic is pure
functions over times; the loaders below read those times from the database."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.domain.budget import service as budget
from crewmind.domain.execution.model import RunKind, RunState
from crewmind.domain.planning import estimates
from crewmind.domain.projects.lifecycle import PROJECT_STATE_CHANGED
from crewmind.domain.projects.model import ProjectState
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.models import Event, LedgerLine, Project, Run

WINDOW = timedelta(hours=24)  # PLN-4, GOV-4: the trailing 24 active hours
RUNS_NEEDED = 10  # PLN-4, GOV-4: shown once at least 10 runs exist
HOUR = 3600.0
MEASURED, BEST_CASE, UNKNOWN, NOTHING_LEFT = "measured", "best case", "unknown", "nothing left"

Interval = tuple[datetime, datetime]


def running_intervals(changes: list[tuple[datetime, str]], now: datetime) -> list[Interval]:
    """The stretches a project was running, from its state changes in time order (PLN-4:
    active hours exclude time held or paused)."""
    intervals: list[Interval] = []
    since: datetime | None = None
    for at, state in changes:
        if state == ProjectState.RUNNING and since is None:
            since = at
        elif state != ProjectState.RUNNING and since is not None:
            intervals.append((since, at))
            since = None
    if since is not None and now > since:
        intervals.append((since, now))
    return [(start, end) for start, end in intervals if end > start]


def trailing(intervals: list[Interval], window: timedelta = WINDOW) -> list[Interval]:
    """The most recent active time, up to `window` of it."""
    kept: list[Interval] = []
    left = window
    for start, end in reversed(intervals):
        if left <= timedelta(0):
            break
        length = end - start
        kept.append((end - left, end) if length > left else (start, end))
        left -= min(length, left)
    return list(reversed(kept))


def hours_of(intervals: list[Interval]) -> float:
    return sum((end - start).total_seconds() for start, end in intervals) / HOUR


def active_offset(intervals: list[Interval], at: datetime) -> float | None:
    """How many active hours into `intervals` the moment `at` falls, or None when it is
    outside them."""
    before = 0.0
    for start, end in intervals:
        if start <= at <= end:
            return before + (at - start).total_seconds() / HOUR
        before += (end - start).total_seconds() / HOUR
    return None


def throughput(run_ends: list[datetime], intervals: list[Interval]) -> float | None:
    """PLN-4: completed work runs per active hour over the trailing 24 active hours, once
    at least 10 runs exist."""
    if len(run_ends) < RUNS_NEEDED:
        return None
    window = trailing(intervals)
    hours = hours_of(window)
    if hours <= 0:
        return None
    inside = sum(1 for at in run_ends if active_offset(window, at) is not None)
    return inside / hours if inside else None


def burn_rate(spends: list[tuple[datetime, int]], intervals: list[Interval]) -> int | None:
    """GOV-4: median tokens per active hour over the last 24 active hours."""
    window = trailing(intervals)
    hours = hours_of(window)
    if hours <= 0:
        return None
    buckets = [0] * max(math.ceil(hours), 1)
    for at, tokens in spends:
        offset = active_offset(window, at)
        if offset is not None:
            buckets[min(int(offset), len(buckets) - 1)] += tokens
    return int(statistics.median(buckets))


@dataclass(frozen=True)
class Projection:
    """PLN-5: when the open scope will be done. `kind` says how far to trust it."""

    kind: str
    hours: float | None
    at: datetime | None
    remaining_runs: int
    throughput: float | None

    @property
    def known(self) -> bool:
        return self.at is not None

    def text(self) -> str:
        if self.kind == NOTHING_LEFT:
            return "nothing is left to do"
        if self.hours is None or self.at is None:
            return "unknown: open scope has no estimate, or no run has finished yet"
        length = f"{self.hours:.1f} hours" if self.hours < 48 else f"{self.hours / 24:.1f} days"
        when = self.at.strftime("%d %b %Y %H:%M UTC")
        if self.kind == BEST_CASE:
            return f"{length} at best (best case, by {when}): {self.remaining_runs} runs remain"
        return (
            f"{length} (by {when}): {self.remaining_runs} runs remain at "
            f"{self.throughput:.1f} runs per active hour"
        )


def projection_of(
    *,
    remaining_runs: int,
    unestimated: int,
    rate: float | None,
    median_run_seconds: float | None,
    concurrency: int,
    now: datetime,
) -> Projection:
    """PLN-5: remaining adjusted runs / throughput; without a measured throughput, the
    best case; with no estimates, unknown."""
    if remaining_runs == 0 and unestimated == 0:
        return Projection(NOTHING_LEFT, 0.0, now, 0, rate)
    if remaining_runs == 0:
        return Projection(UNKNOWN, None, None, 0, rate)
    if rate:
        hours = remaining_runs / rate
        return Projection(MEASURED, hours, now + timedelta(hours=hours), remaining_runs, rate)
    if median_run_seconds is None:
        return Projection(UNKNOWN, None, None, remaining_runs, None)
    hours = remaining_runs * median_run_seconds / max(concurrency, 1) / HOUR
    return Projection(BEST_CASE, hours, now + timedelta(hours=hours), remaining_runs, None)


async def intervals_of(session: AsyncSession, project_id: str, now: datetime) -> list[Interval]:
    rows = await session.execute(
        select(Event.at, Event.after)
        .where(Event.project_id == project_id, Event.type == PROJECT_STATE_CHANGED)
        .order_by(Event.id)
    )
    changes = [(at, str((after or {}).get("state", ""))) for at, after in rows.all()]
    return running_intervals(changes, now)


async def _work_runs(session: AsyncSession, project_id: str | None) -> list[tuple[datetime, float]]:
    wanted = select(Run.started_at, Run.ended_at).where(
        Run.kind == RunKind.WORK,
        Run.state == RunState.FINISHED,
        Run.started_at.is_not(None),
        Run.ended_at.is_not(None),
    )
    if project_id is not None:
        wanted = wanted.where(Run.project_id == project_id)
    found: list[tuple[datetime, float]] = []
    for started, ended in (await session.execute(wanted)).all():
        if started is not None and ended is not None:
            found.append((ended, (ended - started).total_seconds()))
    return found


@dataclass(frozen=True)
class Pace:
    """Everything the plan shows about speed and spend at one moment."""

    projection: Projection
    throughput: float | None
    burn_rate: int | None
    projected_spend: int | None
    plan: estimates.Plan


async def pace(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> Pace:
    intervals = await intervals_of(session, project.id, now)
    runs = await _work_runs(session, project.id)
    durations = [seconds for _, seconds in runs] or [
        seconds for _, seconds in await _work_runs(session, None)
    ]
    rate = throughput([ended for ended, _ in runs], intervals)
    numbers = await estimates.plan(session, project)
    concurrency = int(await settings.get(session, estimates.subject(project), "run.concurrency"))
    projection = projection_of(
        remaining_runs=numbers.remaining_runs,
        unestimated=numbers.unestimated,
        rate=rate,
        median_run_seconds=statistics.median(durations) if durations else None,
        concurrency=concurrency,
        now=now,
    )
    burn: int | None = None
    if len(runs) >= RUNS_NEEDED:
        spends = (
            await session.execute(
                select(LedgerLine.at, LedgerLine.counted).where(
                    LedgerLine.project_id == project.id, LedgerLine.unit == "tokens"
                )
            )
        ).all()
        burn = burn_rate([(at, int(tokens)) for at, tokens in spends], intervals)
    spent = await budget.spent(session, settings, project, now)
    return Pace(
        projection=projection,
        throughput=rate,
        burn_rate=burn,
        projected_spend=None if numbers.tokens is None else spent + numbers.tokens,
        plan=numbers,
    )
