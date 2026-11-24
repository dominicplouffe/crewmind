"""The board as a run sees it in its context pack, and the runaway guards that watch for
work that is not moving (EXE-15, EXE-16, GOV-7, WRK-2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.execution import notices, runs
from nightsquad.domain.execution.model import RunKind, RunState, SeatKind
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.integrations import push
from nightsquad.domain.projects import lifecycle
from nightsquad.domain.projects.model import ProjectState
from nightsquad.domain.settings.service import SettingsService
from nightsquad.domain.work import tasks
from nightsquad.domain.work.model import MAX_FAILURES, OPEN_STATES, TaskState
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import (
    ArtifactVersion,
    Event,
    Project,
    ProjectGuard,
    Review,
    Run,
    Seat,
    SideEffect,
    Suggestion,
    Task,
)

GUARD_CHANGED = event_type("guard.changed", "A runaway guard opened or cleared (EXE-16, GOV-7).")
STALLED, SPINNING = "stalled", "spinning"
SPINNING_CONCURRENCY = 1  # GOV-7: while spinning, concurrency drops to 1


def _line(task: Task) -> str:
    return f"- [task {task.id}, {task.state}] {task.title}"


async def section(session: AsyncSession, seat: Seat, run: Run, now: datetime) -> str | None:
    """What this agent holds, reviews and may claim; for the CEO, every open task and the
    suggestions waiting. Suggestions shown to a CEO work run are handed to it (WRK-2)."""
    open_now = list(
        await session.scalars(
            select(Task)
            .where(Task.project_id == seat.project_id, Task.state.in_(OPEN_STATES))
            .order_by(Task.id)
        )
    )
    parts: list[str] = []
    held = [task for task in open_now if task.claimant_id == seat.id]
    for task in held:
        if task.state != TaskState.CLAIMED:
            continue
        parts.append(
            f"You hold task {task.id}: {task.title}\nGoal: {task.goal}\n"
            f"Success test ({task.test_kind}): {task.success_test}\n"
            + (
                f"It has failed {task.failures} of {MAX_FAILURES} times:\n"
                f"{await tasks.attempt_history(session, task)}\n"
                if task.failures
                else ""
            )
            + f"When it is done, call agent_complete_task (task_id={task.id}) with evidence."
        )
    reviewing = list(
        await session.scalars(
            select(Task)
            .join(Review, Review.task_id == Task.id)
            .where(
                Review.reviewer_id == seat.id, Review.ok.is_(None), Task.state == TaskState.REVIEW
            )
        )
    )
    if reviewing:
        parts.append(
            "Waiting for your review:\n"
            + "\n".join(
                f"- [task {t.id}] {t.title}\n  Test: {t.success_test}\n"
                f"  The author's evidence: {t.completion_evidence}"
                for t in reviewing
            )
        )
    claimable: list[Task] = []
    for task in open_now:
        if task.state != TaskState.READY:
            continue
        try:
            await tasks.check_claim(session, task, seat, now)
        except Refusal:
            continue
        claimable.append(task)
    if claimable:
        parts.append(
            "Ready for you to claim (agent_claim_task):\n" + "\n".join(_line(t) for t in claimable)
        )
    if seat.kind == SeatKind.CEO:
        if open_now:
            parts.append("Open tasks:\n" + "\n".join(_line(t) for t in open_now))
        waiting = (
            await session.execute(
                select(Suggestion, Seat)
                .join(Seat, Seat.id == Suggestion.seat_id)
                .where(Suggestion.project_id == seat.project_id, Suggestion.handed_to_run.is_(None))
                .order_by(Suggestion.id)
            )
        ).all()
        if waiting:
            parts.append(
                "Suggestions from the team (they create no work until you do):\n"
                + "\n".join(f"- {author.name}: {row.text}" for row, author in waiting)
            )
            if run.kind == RunKind.WORK:
                for row, _ in waiting:
                    row.handed_to_run = run.id
    return "# The board\n\n" + "\n\n".join(parts) if parts else None


async def _give_back_suggestions(session: AsyncSession, run: Run, now: datetime) -> None:
    """WRK-2: if the planning run a suggestion was handed to fails, it is given back."""
    rows = await session.scalars(select(Suggestion).where(Suggestion.handed_to_run == run.id))
    for row in rows:
        row.handed_to_run = None


runs.failed_hooks.append(_give_back_suggestions)


async def earlier_effects(session: AsyncSession, run: Run) -> str | None:
    """WRK-16: a retried run sees what earlier attempts of it already declared and fired."""
    if run.attempt <= 1:
        return None
    attempts = select(Run.id).where(Run.wake_id == run.wake_id, Run.id != run.id)
    rows = list(
        await session.scalars(
            select(SideEffect).where(SideEffect.run_id.in_(attempts)).order_by(SideEffect.id)
        )
    )
    if not rows:
        return None
    words = {True: "it fired", False: "it did not fire", None: "it was never finished"}
    return (
        "# Side effects from earlier attempts of this run\n\nCheck these before doing "
        "anything outside the project again. Do not repeat one that fired.\n\n"
        + "\n".join(f"- [key {row.idempotency_key}] {row.what}: {words[row.fired]}" for row in rows)
    )


async def open_guard(session: AsyncSession, project_id: str, kind: str) -> ProjectGuard | None:
    return await session.scalar(
        select(ProjectGuard).where(
            ProjectGuard.project_id == project_id,
            ProjectGuard.kind == kind,
            ProjectGuard.cleared_at.is_(None),
        )
    )


def record_guard(session: AsyncSession, guard: ProjectGuard, now: datetime, state: str) -> None:
    append_event(
        session,
        type=GUARD_CHANGED,
        caller=tasks.WORK_JOB,
        at=now,
        subject=("guard", guard.kind),
        project_id=guard.project_id,
        after={"state": state, "cause": guard.cause},
    )


async def _open(
    session: AsyncSession, project: Project, kind: str, cause: str, now: datetime
) -> ProjectGuard:
    guard = ProjectGuard(project_id=project.id, kind=kind, cause=cause, opened_at=now)
    session.add(guard)
    await session.flush()
    record_guard(session, guard, now, "open")
    return guard


async def _clear(session: AsyncSession, guard: ProjectGuard, now: datetime) -> None:
    guard.cleared_at = now
    record_guard(session, guard, now, "cleared")


async def _last_work_start(session: AsyncSession, project_id: str) -> datetime | None:
    return await session.scalar(
        select(func.max(Run.started_at)).where(
            Run.project_id == project_id, Run.kind == RunKind.WORK
        )
    )


async def watch_for_stall(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """EXE-16: in a running project with open work, if no work run has started for
    `stall.after` and no hold explains it, the CEO is woken and the chairman gets one alarm
    naming the cause. The guard clears when a work run starts."""
    guard = await open_guard(session, project.id, STALLED)
    open_count = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.project_id == project.id, Task.state.in_(OPEN_STATES))
    )
    last = await _last_work_start(session, project.id)
    if guard is not None:
        if not open_count or (last is not None and last > guard.opened_at):
            await _clear(session, guard, now)
        return
    if project.state != ProjectState.RUNNING or not open_count:
        return
    if await lifecycle.active_holds(session, project.id):
        return
    after = timedelta(
        seconds=int(await settings.get(session, tasks.subject(project), "stall.after"))
    )
    oldest = await session.scalar(
        select(func.min(Task.created_at)).where(
            Task.project_id == project.id, Task.state.in_(OPEN_STATES)
        )
    )
    since = max(filter(None, [last, oldest]), default=now)
    if now - since < after:
        return
    by_state = dict(
        (
            await session.execute(
                select(Task.state, func.count())
                .where(Task.project_id == project.id, Task.state.in_(OPEN_STATES))
                .group_by(Task.state)
            )
        ).all()
    )
    listed = ", ".join(f"{count} {state}" for state, count in sorted(by_state.items()))
    minutes = int(after.total_seconds() // 60)
    cause = f"No work run has started for {minutes} minutes while tasks are open ({listed})."
    await _open(session, project, STALLED, cause, now)
    ceo = await ceo_of(session, project.id)
    notices.notify(
        session, project.id, ceo.id, "work stalled",
        f"{cause} Find what is in the way: re-plan, kill what is blocked, or hire.",
        now, urgent=True,
    )  # fmt: skip
    await push.raise_alarm(session, project, f"Stalled. {cause}", now)
    await conversation.platform_line(
        session, project.id, f"Work has stalled. {cause} The CEO has been woken.", now,
        detail={"kind": "stalled", "alarm": True},
    )  # fmt: skip


async def _changed_something(session: AsyncSession, run: Run) -> bool:
    """Whether a work run changed work state or published a file (GOV-7)."""
    via = f"run:{run.id}"
    event = await session.scalar(
        select(Event.id)
        .where(Event.project_id == run.project_id, Event.via == via, Event.type.like("task.%"))
        .limit(1)
    )
    if event is not None:
        return True
    published = await session.scalar(
        select(ArtifactVersion.id).where(ArtifactVersion.run_id == run.id).limit(1)
    )
    return published is not None


async def watch_for_spinning(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """GOV-7: when the last `spin.window` finished work runs changed no work state and
    published no file, a spinning guard opens and concurrency drops to 1. It clears when a
    work run changes something."""
    window = int(await settings.get(session, tasks.subject(project), "spin.window"))
    recent = list(
        await session.scalars(
            select(Run)
            .where(
                Run.project_id == project.id,
                Run.kind == RunKind.WORK,
                Run.state == RunState.FINISHED,
            )
            .order_by(Run.ended_at.desc())
            .limit(window)
        )
    )
    guard = await open_guard(session, project.id, SPINNING)
    if guard is not None:
        since = await session.scalars(
            select(Run).where(
                Run.project_id == project.id,
                Run.kind == RunKind.WORK,
                Run.ended_at >= guard.opened_at,
            )
        )
        for run in since:
            if await _changed_something(session, run):
                await _clear(session, guard, now)
                break
        return
    if len(recent) < window:
        return
    for run in recent:
        if await _changed_something(session, run):
            return
    cause = (
        f"The last {window} work runs changed no task and published no file. Runs are now "
        "one at a time until one of them changes something."
    )
    await _open(session, project, SPINNING, cause, now)
    ceo = await ceo_of(session, project.id)
    notices.notify(session, project.id, ceo.id, "spinning", cause, now, urgent=True)
    await conversation.platform_line(
        session, project.id, f"The team is spinning. {cause}", now, detail={"kind": "spinning"}
    )


async def concurrency_limit(session: AsyncSession, project_id: str, configured: int) -> int:
    """GOV-7: the concurrency a project may use now."""
    spinning = await open_guard(session, project_id, SPINNING)
    return min(configured, SPINNING_CONCURRENCY) if spinning else configured


runs.concurrency_limit = concurrency_limit
