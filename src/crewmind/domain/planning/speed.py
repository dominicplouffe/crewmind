"""Speed is a requirement (SPD-2, SPD-3, SPD-4, SPD-8, SPD-9): the first planning run is
queued at start, the plan shows the longest chain, every stretch of a project's time is
attributed, and slow starts, missing output and idle seats are said out loud."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.domain.artifacts.service import Kind
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import notices
from crewmind.domain.execution.model import RunKind, RunState, SeatKind, SeatState
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import (
    acceptance,
    authority,
    completion,
    estimates,
    graph,
    projection,
)
from crewmind.domain.planning import requirements as scope
from crewmind.domain.planning.model import OPEN_SCOPE, RequirementState, RequirementTest
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.model import HOLDABLE, Hold, ProjectState, ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.domain.work import board
from crewmind.domain.work.model import TaskState
from crewmind.storage.models import (
    Artifact,
    ArtifactVersion,
    Commitment,
    Project,
    ProjectGuard,
    RaiseRequest,
    Requirement,
    ReserveDraw,
    Review,
    Run,
    Seat,
    Task,
    TimeSpan,
)

SLOW_START, NO_OUTPUT, SEAT_IDLE = "slow start", "no output", "seat idle"
WORKING, CHAIRMAN, LIMIT, PROVIDER, REVIEWING = (
    "working",
    "chairman",
    "limit",
    "provider",
    "reviewing",
)
WENT_TO = {
    WORKING: "working",
    CHAIRMAN: "waiting on the chairman",
    LIMIT: "waiting on a limit or the budget",
    PROVIDER: "waiting on a provider",
    REVIEWING: "reviewing",
}
"""SPD-8: where a project's time goes. Waiting on the chairman is shown on its own."""
_HOLD_BUCKET = {
    Hold.BUDGET_WALL: LIMIT,
    Hold.AUTH_FAILURES: PROVIDER,
    Hold.SKIPPED_CYCLES: CHAIRMAN,
    Hold.CHAIRMAN: CHAIRMAN,
}
_HOLD_ORDER = (Hold.BUDGET_WALL, Hold.AUTH_FAILURES, Hold.SKIPPED_CYCLES, Hold.CHAIRMAN)


async def queue_first_planning(session: AsyncSession, project: Project, now: datetime) -> None:
    """SPD-3: on start the CEO's first planning run is queued at once."""
    ceo = await ceo_of(session, project.id)
    what = {
        ProjectType.EXPLORE: "Open the first bets, then create the work that tests them.",
        ProjectType.OPERATE: "Propose the recurring requirements, then create this cycle's work.",
    }.get(
        ProjectType(project.type),
        "Propose a first requirement for the thinnest usable version, get it accepted and "
        "estimated, and create its first task. Write the rest of the plan while work runs.",
    )
    notices.notify(
        session, project.id, ceo.id, "project started",
        f"The project has started. Goal: {project.goal}\n{what}",
        now, urgent=True,
    )  # fmt: skip


lifecycle.started_hooks.append(queue_first_planning)


async def longest_chain(session: AsyncSession, project: Project) -> tuple[int, list[int]]:
    """SPD-2: the longest dependency chain of open scope, in adjusted runs, in order."""
    multiplier = await estimates.multiplier_of(session, project)
    rows = await session.scalars(
        select(Requirement).where(
            Requirement.project_id == project.id, Requirement.state.in_(OPEN_SCOPE)
        )
    )
    lengths = {row.id: estimates.adjusted_runs(row.estimate_runs or 0, multiplier) for row in rows}
    return graph.longest_chain(await scope.dependency_graph(session, project.id), lengths)


async def _count(session: AsyncSession, statement: Any) -> int:
    return int(await session.scalar(statement) or 0)


async def _waits_on_chairman(
    session: AsyncSession, settings: SettingsService, project: Project
) -> bool:
    """Whether something only the chairman can answer is open."""
    if project.state == ProjectState.READY:
        return True
    pending = [
        select(func.count())
        .select_from(Requirement)
        .where(
            Requirement.project_id == project.id,
            Requirement.state == RequirementState.CHECKING,
            Requirement.test_kind == RequirementTest.OBSERVABLE,
        ),
        select(func.count())
        .select_from(Commitment)
        .where(Commitment.project_id == project.id, Commitment.state == "proposed"),
        select(func.count())
        .select_from(ReserveDraw)
        .where(ReserveDraw.project_id == project.id, ReserveDraw.state == "requested"),
        select(func.count())
        .select_from(RaiseRequest)
        .where(RaiseRequest.project_id == project.id, RaiseRequest.state == "pending"),
    ]
    values = [await _count(session, statement) for statement in pending]
    if any(values[1:]):
        return True
    holder = await acceptance.verdict_holder(session, settings, project)
    return bool(values[0]) and holder == acceptance.CHAIRMAN


async def where_now(session: AsyncSession, settings: SettingsService, project: Project) -> str:
    """SPD-8: what the project's time is going to at this moment."""
    holds = {Hold(row.reason) for row in await lifecycle.active_holds(session, project.id)}
    for hold in _HOLD_ORDER:
        if hold in holds:
            return _HOLD_BUCKET[hold]
    live = (
        await session.execute(
            select(Seat.kind, func.count())
            .join(Run, Run.seat_id == Seat.id)
            .where(
                Run.project_id == project.id,
                Run.kind == RunKind.WORK,
                Run.state.in_([RunState.LEASED, RunState.RUNNING]),
            )
            .group_by(Seat.kind)
        )
    ).all()
    by_kind = {str(kind): int(count) for kind, count in live}
    if any(count for kind, count in by_kind.items() if kind != SeatKind.REVIEWER):
        return WORKING
    in_review = await _count(
        session,
        select(func.count())
        .select_from(Task)
        .where(
            Task.project_id == project.id,
            Task.state.in_([TaskState.REVIEW, TaskState.CHECKING]),
        ),
    )
    if by_kind.get(SeatKind.REVIEWER) or in_review:
        return REVIEWING
    if await _waits_on_chairman(session, settings, project):
        return CHAIRMAN
    queued = await _count(
        session,
        select(func.count())
        .select_from(Run)
        .where(
            Run.project_id == project.id,
            Run.kind == RunKind.WORK,
            Run.state == RunState.QUEUED,
        ),
    )
    return LIMIT if queued and not by_kind else WORKING


async def account(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """SPD-8: attribute the time since the last tick to what the project is doing now.
    Spans are contiguous from the first start to the moment the project ends."""
    if project.state not in (*HOLDABLE, ProjectState.READY):
        return
    last = await session.scalar(
        select(TimeSpan)
        .where(TimeSpan.project_id == project.id)
        .order_by(TimeSpan.id.desc())
        .limit(1)
    )
    start = last.ended_at if last else await projection.started_at(session, project.id)
    if start is None or now <= start:
        return
    went = await where_now(session, settings, project)
    if last is not None and last.went_to == went:
        last.ended_at = now
    else:
        session.add(TimeSpan(project_id=project.id, went_to=went, started_at=start, ended_at=now))


async def time_report(session: AsyncSession, project: Project, now: datetime) -> dict[str, Any]:
    """SPD-8: time to first task, first deliverable and done, and where the time went."""
    started = await projection.started_at(session, project.id)
    first_task = await session.scalar(
        select(func.min(Task.claimed_at)).where(Task.project_id == project.id)
    )
    first_deliverable = await session.scalar(
        select(func.min(ArtifactVersion.created_at))
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(Artifact.project_id == project.id, Artifact.kind == Kind.DELIVERABLE)
    )
    done = await completion.entered(session, project.id, ProjectState.COMPLETED)

    def since(moment: datetime | None) -> int | None:
        if started is None or moment is None:
            return None
        return max(int((moment - started).total_seconds()), 0)

    rows = (
        await session.execute(
            select(TimeSpan.went_to, TimeSpan.started_at, TimeSpan.ended_at).where(
                TimeSpan.project_id == project.id
            )
        )
    ).all()
    where = dict.fromkeys(WENT_TO.values(), 0)
    for went, start, end in rows:
        where[WENT_TO[went]] += int((end - start).total_seconds())
    return {
        "to_first_task_seconds": since(first_task),
        "to_first_deliverable_seconds": since(first_deliverable),
        "to_done_seconds": since(done),
        "where": where,
    }


async def add_time(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    now: datetime,
    receipt: dict[str, Any],
) -> None:
    """PRJ-4, SPD-8: the receipt says where the time went."""
    await account(session, settings, project, now)
    await session.flush()
    report = await time_report(session, project, now)
    report["to_done_seconds"] = receipt["wall_clock_seconds"]
    receipt["time"] = report


completion.receipt_parts.append(add_time)


async def _flag(
    session: AsyncSession,
    project: Project,
    kind: str,
    cause: str | None,
    advice: str,
    now: datetime,
) -> None:
    """Open, replace or clear one speed flag. Opening it tells the CEO and the chat once."""
    guard = await board.open_guard(session, project.id, kind)
    if guard is not None and (cause is None or guard.cause != cause):
        guard.cleared_at = now
        board.record_guard(session, guard, now, "cleared")
        guard = None
    if cause is None or guard is not None:
        return
    opened = ProjectGuard(project_id=project.id, kind=kind, cause=cause, opened_at=now)
    session.add(opened)
    await session.flush()
    board.record_guard(session, opened, now, "open")
    ceo = await ceo_of(session, project.id)
    notices.notify(session, project.id, ceo.id, kind, f"{cause} {advice}", now, urgent=True)
    await conversation.platform_line(
        session, project.id, f"{cause} The CEO has been told.", now, detail={"kind": kind}
    )


async def _slow_start_cause(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> str | None:
    """SPD-3: a Deliver project with no task claimed within `start.first_task_within` of
    its start, with the cause named."""
    if project.type != ProjectType.DELIVER or project.state != ProjectState.RUNNING:
        return None
    claimed = await session.scalar(
        select(func.min(Task.claimed_at)).where(Task.project_id == project.id)
    )
    started = await projection.started_at(session, project.id)
    limit = int(await settings.get(session, authority.subject(project), "start.first_task_within"))
    if claimed is not None or started is None or now - started < timedelta(seconds=limit):
        return None
    counts = dict(
        (
            await session.execute(
                select(Requirement.state, func.count())
                .where(Requirement.project_id == project.id)
                .group_by(Requirement.state)
            )
        ).all()
    )
    tasks_made = await _count(
        session, select(func.count()).select_from(Task).where(Task.project_id == project.id)
    )
    estimated = await _count(
        session,
        select(func.count())
        .select_from(Requirement)
        .where(
            Requirement.project_id == project.id,
            Requirement.state.in_(OPEN_SCOPE),
            Requirement.estimate_runs.is_not(None),
        ),
    )
    if tasks_made:
        why = f"{tasks_made} tasks exist but nobody has claimed one"
    elif estimated:
        why = "scope is accepted and estimated but no task has been created"
    elif any(counts.get(state) for state in OPEN_SCOPE):
        why = "the accepted scope has no estimate"
    elif counts.get(RequirementState.PROPOSED):
        why = "the proposed requirements are waiting to be accepted"
    else:
        why = "no requirement has been proposed"
    return f"Slow start: no task was claimed in the first {limit // 60} minutes because {why}."


async def _no_output_cause(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> str | None:
    """SPD-4: a Deliver project that has run for `output.first_within` with no deliverable
    version published."""
    if project.type != ProjectType.DELIVER or project.state != ProjectState.RUNNING:
        return None
    limit = int(await settings.get(session, authority.subject(project), "output.first_within"))
    ran = projection.hours_of(await projection.intervals_of(session, project.id, now))
    published = await _count(
        session,
        select(func.count())
        .select_from(Artifact)
        .where(Artifact.project_id == project.id, Artifact.kind == Kind.DELIVERABLE),
    )
    if published or ran * projection.HOUR < limit:
        return None
    return (
        f"No visible output: the project has run for {limit // 3600} hours and nothing has "
        "been published for the chairman to open."
    )


async def _idle_cause(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> str | None:
    """SPD-9: team seats that have closed nothing in `seat.idle_after`."""
    if project.state != ProjectState.RUNNING:
        return None
    limit = timedelta(
        seconds=int(await settings.get(session, authority.subject(project), "seat.idle_after"))
    )
    seats = await session.scalars(
        select(Seat)
        .where(
            Seat.project_id == project.id,
            Seat.state == SeatState.ACTIVE,
            Seat.team_id.is_not(None),
        )
        .order_by(Seat.name)
    )
    idle: list[str] = []
    for seat in seats:
        closed = await session.scalar(
            select(func.max(Task.closed_at)).where(
                Task.claimant_id == seat.id, Task.state == TaskState.DONE
            )
        )
        reviewed = await session.scalar(
            select(func.max(Review.answered_at)).where(Review.reviewer_id == seat.id)
        )
        last = max(filter(None, [closed, reviewed, seat.created_at]))
        if now - last >= limit:
            idle.append(seat.name)
    if not idle:
        return None
    days = int(limit.total_seconds() // 86_400)
    return f"Seat idle: {', '.join(idle)} closed nothing in {days} days."


async def watch(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """Keep the three speed flags in step with the facts (SPD-3, SPD-4, SPD-9)."""
    await _flag(
        session, project, SLOW_START,
        await _slow_start_cause(session, settings, project, now),
        "Get one requirement accepted and estimated and create its first task now.", now,
    )  # fmt: skip
    await _flag(
        session, project, NO_OUTPUT,
        await _no_output_cause(session, settings, project, now),
        "Publish the thinnest usable version of the deliverable.", now,
    )  # fmt: skip
    await _flag(
        session, project, SEAT_IDLE,
        await _idle_cause(session, settings, project, now),
        "Stand the seat down, or say in the chat what it is for.", now,
    )  # fmt: skip


async def open_flags(session: AsyncSession, project_id: str) -> list[ProjectGuard]:
    rows = await session.scalars(
        select(ProjectGuard)
        .where(ProjectGuard.project_id == project_id, ProjectGuard.cleared_at.is_(None))
        .order_by(ProjectGuard.id)
    )
    return list(rows)
