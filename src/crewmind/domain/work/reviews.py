"""Independent read: a reviewer seat other than the author gives the verdict on an
observable test (WRK-9, WRK-13, WRK-15, INV-3, P5)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.execution import notices, roster
from crewmind.domain.execution.model import SeatKind, SeatState
from crewmind.domain.settings.service import SettingsService
from crewmind.domain.work import tasks
from crewmind.domain.work.model import Label, TaskState
from crewmind.storage.models import AuditSample, Project, Review, Seat, Task

WRK_9 = rules.register(
    Rule("WRK-9", "An observable test is judged by a reviewer seat other than the author.")
)
WRK_13 = rules.register(Rule("WRK-13", "Only the chairman passes or fails an audit sample."))

NOTES_MIN_CHARACTERS = 10  # WRK-9
PERCENT = 100


async def reviewers(session: AsyncSession, project_id: str) -> list[Seat]:
    rows = await session.scalars(
        select(Seat)
        .where(
            Seat.project_id == project_id,
            Seat.kind == SeatKind.REVIEWER,
            Seat.state == SeatState.ACTIVE,
        )
        .order_by(Seat.created_at, Seat.name)
    )
    return list(rows)


async def consider_for_audit(
    session: AsyncSession, settings: SettingsService, project: Project, task: Task, now: datetime
) -> None:
    """WRK-13: every observable close is considered once and recorded as drawn or skipped.
    Sampling never blocks or reopens work."""
    seen = await session.scalar(select(AuditSample.id).where(AuditSample.task_id == task.id))
    if seen is not None:
        return
    values = await settings.effective(session, tasks.subject(project))
    drawn = secrets.randbelow(PERCENT) < int(values["audit.sample_rate"])
    session.add(
        AuditSample(
            task_id=task.id,
            project_id=project.id,
            drawn=drawn,
            considered_at=now,
            expires_at=now + timedelta(seconds=int(values["audit.window"])) if drawn else None,
        )
    )


async def request(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    task: Task,
    caller: Caller,
    now: datetime,
) -> None:
    """Route a completed observable task. With independent read on, exactly one reviewer
    other than the author is woken; with none left, the task closes unread. In a solo
    project with independent read off it is done, labelled self-reported (WRK-6, WRK-9)."""
    independent = bool(await settings.get(session, tasks.subject(project), "review.independent"))
    if not independent and await tasks.is_solo(session, project.id):
        await tasks.passed(session, task, Label.SELF_REPORTED, None, now, caller)
        await consider_for_audit(session, settings, project, task, now)
        return
    if independent:
        # Independent read was turned on a moment ago, or the last reviewer left: staff
        # the seat now, so the work is read rather than closed unread (WRK-9).
        await roster.ensure_reviewer(session, project, now)
    tasks.move(session, task, TaskState.REVIEW, caller, now)
    await assign(session, task, now)


async def assign(session: AsyncSession, task: Task, now: datetime) -> None:
    """Wake exactly one reviewer for a task in review: the one with the fewest reviews
    waiting who did not do the work. With no reviewer left, close it unread (WRK-9)."""
    candidates = [
        seat for seat in await reviewers(session, task.project_id) if seat.id != task.claimant_id
    ]
    if not candidates:
        task.label = Label.CLOSED_UNREAD
        tasks.move(
            session, task, TaskState.CLOSED_UNREAD, tasks.WORK_JOB, now, {"why": "no reviewer seat"}
        )
        return
    waiting = dict(
        (
            await session.execute(
                select(Review.reviewer_id, func.count())
                .where(Review.project_id == task.project_id, Review.ok.is_(None))
                .group_by(Review.reviewer_id)
            )
        ).all()
    )
    chosen = min(candidates, key=lambda seat: (waiting.get(seat.id, 0), seat.name))
    session.add(
        Review(task_id=task.id, project_id=task.project_id, reviewer_id=chosen.id, asked_at=now)
    )
    notices.notify(
        session,
        task.project_id,
        chosen.id,
        "review needed",
        f"Review task {task.id}: {task.title}\nSuccess test: {task.success_test}\n"
        f"The author's evidence: {task.completion_evidence}\n"
        f"Give your verdict with agent_review_task (task_id={task.id}).",
        now,
        urgent=True,
    )


async def close_orphans(session: AsyncSession, project: Project, now: datetime) -> None:
    """WRK-9: a task waiting on a reviewer that is no longer active gets another reviewer,
    or is closed unread when none remains."""
    rows = await session.execute(
        select(Task, Review, Seat)
        .join(Review, Review.task_id == Task.id)
        .join(Seat, Seat.id == Review.reviewer_id)
        .where(
            Task.project_id == project.id,
            Task.state == TaskState.REVIEW,
            Review.ok.is_(None),
            Seat.state != SeatState.ACTIVE,
        )
    )
    for task, review, _ in rows.all():
        await session.delete(review)
        await session.flush()
        await assign(session, task, now)
