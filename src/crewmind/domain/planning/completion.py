"""Deliver: the final gap review, ready, complete with a receipt, and reopen (PRJ-4,
PRJ-5, PRJ-6, WRK-11)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.artifacts.service import Kind
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import notices, roster, runs
from crewmind.domain.execution.model import RunKind, SeatKind, SeatState
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import authority, commitments, projection, requirements
from crewmind.domain.planning.authority import CEO, Actor
from crewmind.domain.planning.model import (
    OPEN_SCOPE,
    CommitmentState,
    RequirementState,
    RequirementTest,
)
from crewmind.domain.planning.readiness import PLANNING_JOB, move
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.lifecycle import PROJECT_STATE_CHANGED
from crewmind.domain.projects.model import ProjectState, ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.domain.work.model import OPEN_STATES
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import (
    Artifact,
    ArtifactVersion,
    Event,
    Gap,
    GapReview,
    LedgerLine,
    Project,
    Requirement,
    Seat,
    Task,
)

WRK_11 = rules.register(
    Rule("WRK-11", "A Deliver project is not ready until an independent gap review is settled.")
)
PRJ_6 = rules.register(Rule("PRJ-6", "A completed project is reopened only within its window."))
GAP_CHANGED = event_type("gap.changed", "A gap from the final gap review was filed or settled.")
OPEN, NOTED, CLOSED, WAIVED = "open", "noted", "closed", "waived"
REASON_MIN_CHARACTERS = 10  # WRK-11: each gap and each waiver carries its reason
R = RequirementState


@dataclass(frozen=True)
class NewGap:
    text: str
    must_fix: bool
    reason: str


async def deliverables(session: AsyncSession, project_id: str) -> list[Artifact]:
    rows = await session.scalars(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.kind == Kind.DELIVERABLE)
        .order_by(Artifact.name)
    )
    return list(rows)


async def _authors(session: AsyncSession, project_id: str) -> set[str]:
    """Everyone who wrote a version of a deliverable."""
    rows = await session.scalars(
        select(ArtifactVersion.author_id)
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(Artifact.project_id == project_id, Artifact.kind == Kind.DELIVERABLE)
    )
    return {str(row) for row in rows}


async def pending_review(session: AsyncSession, project_id: str) -> GapReview | None:
    return await session.scalar(
        select(GapReview).where(GapReview.project_id == project_id, GapReview.filed_at.is_(None))
    )


async def review_is_current(session: AsyncSession, project_id: str) -> bool:
    """A filed review covers the scope as long as no requirement of the CEO's or the
    chairman's own was accepted after it. Requirements born from gaps do not reopen it."""
    filed = await session.scalar(
        select(func.max(GapReview.filed_at)).where(GapReview.project_id == project_id)
    )
    if filed is None:
        return False
    newest = await session.scalar(
        select(func.max(Requirement.accepted_at)).where(
            Requirement.project_id == project_id, Requirement.gap_id.is_(None)
        )
    )
    return newest is None or newest <= filed


async def ask_for_review(session: AsyncSession, project: Project, now: datetime) -> GapReview:
    """WRK-11: ask a reviewer seat that authored none of the deliverables. With none to
    ask, the review is recorded as not done and the chairman is told."""
    await roster.ensure_reviewer(session, project, now)
    wrote = await _authors(session, project.id)
    seats = await session.scalars(
        select(Seat)
        .where(
            Seat.project_id == project.id,
            Seat.kind == SeatKind.REVIEWER,
            Seat.state == SeatState.ACTIVE,
        )
        .order_by(Seat.created_at, Seat.name)
    )
    reviewer = next((seat for seat in seats if seat.id not in wrote), None)
    review = GapReview(project_id=project.id, asked_at=now)
    session.add(review)
    if reviewer is None:
        review.filed_at = now
        await conversation.platform_line(
            session,
            project.id,
            "The final gap review was not done: every reviewer seat wrote part of the "
            "deliverables, so none is independent.",
            now,
            detail={"kind": "gap review skipped"},
        )
        return review
    review.reviewer_id = reviewer.id
    names = ", ".join(a.name for a in await deliverables(session, project.id)) or "none published"
    notices.notify(
        session,
        project.id,
        reviewer.id,
        "final gap review",
        f"All scope is met. Review the deliverables against the goal before the project is "
        f"called ready.\nGoal: {project.goal}\nDeliverables: {names}\n"
        "File every gap as must-fix or nice-to-have, each with its reason, with "
        "agent_file_gap_review. File an empty list when there is none.",
        now,
        urgent=True,
    )
    return review


async def file_review(
    session: AsyncSession,
    project: Project,
    seat: Seat,
    caller: Caller,
    gaps: list[NewGap],
    now: datetime,
) -> GapReview:
    """WRK-11: the asked reviewer files its gaps. A must-fix gap becomes a CEO-authored
    requirement, proposed, and blocks readiness until it is met or the chairman waives it."""
    review = await pending_review(session, project.id)
    if review is None or review.reviewer_id != seat.id:
        raise Refusal(
            "not_your_review",
            "No final gap review is waiting for you.",
            rule=WRK_11.id,
        )
    if seat.id in await _authors(session, project.id):
        raise Refusal(
            "you_wrote_a_deliverable",
            "The final gap review is done by a seat that wrote none of the deliverables.",
            rule=WRK_11.id,
        )
    for gap in gaps:
        if len(gap.reason.strip()) < REASON_MIN_CHARACTERS:
            raise Refusal(
                "gap_needs_a_reason",
                f"Each gap carries a reason of at least {REASON_MIN_CHARACTERS} characters.",
                rule=WRK_11.id,
            )
    ceo = await ceo_of(session, project.id)
    review.filed_at = now
    await session.flush()
    for gap in gaps:
        row = Gap(
            review_id=review.id,
            project_id=project.id,
            text=gap.text.strip(),
            must_fix=gap.must_fix,
            reason=gap.reason.strip(),
            state=OPEN if gap.must_fix else NOTED,
        )
        session.add(row)
        await session.flush()
        _record(session, row, caller, now)
        if not gap.must_fix:
            continue
        requirement = Requirement(
            project_id=project.id,
            text=f"Close the gap: {row.text}",
            author_kind=CEO,
            author_id=ceo.id,
            state="(new)",
            test_kind=RequirementTest.OBSERVABLE,
            success_test=f"The gap is closed: {row.text} ({row.reason})",
            test_files={},
            stage=1,
            failures=0,
            escalated=False,
            gap_id=row.id,
            created_at=now,
        )
        session.add(requirement)
        await session.flush()
        move(session, requirement, R.PROPOSED, PLANNING_JOB, now, {"gap": row.id})
    must = sum(1 for gap in gaps if gap.must_fix)
    text = (
        f"The final gap review found {must} must-fix and {len(gaps) - must} nice-to-have "
        "gaps."
        + (
            " Each must-fix gap is now a proposed requirement: estimate it, accept it and close it."
            if must
            else ""
        )
    )
    notices.notify(session, project.id, ceo.id, "gap review filed", text, now, urgent=True)
    await conversation.platform_line(
        session, project.id, text, now, detail={"kind": "gap review filed", "must_fix": must}
    )
    return review


def _record(session: AsyncSession, gap: Gap, caller: Caller, now: datetime) -> None:
    append_event(
        session,
        type=GAP_CHANGED,
        caller=caller,
        at=now,
        subject=("gap", str(gap.id)),
        project_id=gap.project_id,
        after={"state": gap.state, "must_fix": gap.must_fix},
        detail={"reason": gap.waived_reason or gap.reason},
    )


async def open_gaps(session: AsyncSession, project_id: str, now: datetime) -> list[Gap]:
    """Must-fix gaps still blocking readiness. One whose requirement is met is closed."""
    rows = await session.execute(
        select(Gap, Requirement)
        .outerjoin(Requirement, Requirement.gap_id == Gap.id)
        .where(Gap.project_id == project_id, Gap.state == OPEN)
        .order_by(Gap.id)
    )
    blocking: list[Gap] = []
    found: list[tuple[Gap, Requirement | None]] = [(row[0], row[1]) for row in rows.all()]
    for gap, requirement in found:
        if requirement is not None and requirement.state == R.MET:
            gap.state = CLOSED
            _record(session, gap, PLANNING_JOB, now)
        else:
            blocking.append(gap)
    return blocking


async def waive(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    gap_id: int,
    reason: str,
    now: datetime,
) -> Gap:
    """WRK-11: the chairman can waive any gap with a reason. Its requirement leaves scope."""
    assert actor.is_chairman
    gap = await session.get(Gap, gap_id)
    if gap is None or gap.project_id != project.id:
        raise Refusal("gap_not_found", "There is no such gap.", kind=RefusalKind.NOT_FOUND)
    if gap.state not in (OPEN, NOTED):
        raise Refusal("gap_settled", f"This gap is already {gap.state}.", rule=WRK_11.id)
    if len(reason.strip()) < REASON_MIN_CHARACTERS:
        raise Refusal(
            "reason_too_short",
            f"Give a reason of at least {REASON_MIN_CHARACTERS} characters.",
            rule=WRK_11.id,
        )
    gap.state, gap.waived_reason = WAIVED, reason.strip()
    _record(session, gap, actor.caller, now)
    requirement = await session.scalar(select(Requirement).where(Requirement.gap_id == gap.id))
    why = f"The chairman waived the gap: {reason.strip()}"
    if requirement is not None and requirement.state == R.PROPOSED:
        await requirements.decline(session, settings, project, actor, requirement, why, now)
    elif requirement is not None and requirement.state in (R.ACCEPTED, R.IN_PROGRESS):
        await requirements.cut(session, settings, project, actor, requirement, why, now)
    return gap


async def entered(session: AsyncSession, project_id: str, state: ProjectState) -> datetime | None:
    """When the project last entered `state`."""
    rows = await session.execute(
        select(Event.at, Event.after)
        .where(Event.project_id == project_id, Event.type == PROJECT_STATE_CHANGED)
        .order_by(Event.id.desc())
    )
    for at, after in rows.all():
        if (after or {}).get("state") == state:
            return at
    return None


async def follow_scope(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """7.1: scope added to or reopened in a ready project sets it running again."""
    if project.state != ProjectState.READY:
        return
    still_open = await session.scalar(
        select(func.count())
        .select_from(Requirement)
        .where(Requirement.project_id == project.id, Requirement.state.in_(OPEN_SCOPE))
    )
    if still_open:
        lifecycle.move(
            session, project, ProjectState.RUNNING, caller=PLANNING_JOB, now=now,
            detail={"why": "scope was added or reopened"},
        )  # fmt: skip


requirements.scope_hooks.append(follow_scope)


async def become_ready(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> bool:
    """PRJ-4: a running Deliver project becomes ready when every accepted requirement is
    met, no top-level task is open, and the final gap review has no open must-fix gap.
    The deliverables are posted in the chat the moment it is ready."""
    if project.type != ProjectType.DELIVER or project.state != ProjectState.RUNNING:
        return False
    counts = dict(
        (
            await session.execute(
                select(Requirement.state, func.count())
                .where(Requirement.project_id == project.id)
                .group_by(Requirement.state)
            )
        ).all()
    )
    if any(counts.get(state) for state in OPEN_SCOPE) or not counts.get(R.MET):
        return False
    open_tasks = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.project_id == project.id, Task.parent_id.is_(None), Task.state.in_(OPEN_STATES))
    )
    if open_tasks:
        return False
    if await pending_review(session, project.id) is not None:
        return False
    if not await review_is_current(session, project.id):
        review = await ask_for_review(session, project, now)
        if review.filed_at is None:
            return False
    if await open_gaps(session, project.id, now):
        return False
    lifecycle.move(session, project, ProjectState.READY, caller=PLANNING_JOB, now=now)
    await runs.revoke(
        session,
        project.id,
        now,
        kinds=frozenset({RunKind.WORK, RunKind.CHECK}),
        cause="the project is ready",
    )
    names = [artifact.name for artifact in await deliverables(session, project.id)]
    listed = ", ".join(names) if names else "no file was published as a deliverable"
    after = int(await settings.get(session, authority.subject(project), "completion.auto_after"))
    closing = (
        f"It completes by itself in {after // 3600} hours unless scope changes."
        if after
        else "It stays ready until you sign it off."
    )
    await conversation.platform_line(
        session,
        project.id,
        f"The project is ready: every requirement is met. Deliverables: {listed}. Sign it "
        f"off to complete it. {closing}",
        now,
        detail={"kind": "project ready", "deliverables": names},
    )
    return True


async def receipt(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> dict[str, Any]:
    """PRJ-4: what the project cost against what was estimated, where the time went, and
    whether the commitment was kept."""
    rows = await session.scalars(
        select(Requirement)
        .where(Requirement.project_id == project.id, Requirement.state.in_([R.MET, R.CUT]))
        .order_by(Requirement.id)
    )
    kinds = (
        await session.execute(
            select(
                func.coalesce(func.sum(LedgerLine.input_tokens), 0),
                func.coalesce(func.sum(LedgerLine.output_tokens), 0),
                func.coalesce(func.sum(LedgerLine.cache_write_tokens), 0),
                func.coalesce(func.sum(LedgerLine.cache_read_tokens), 0),
                func.coalesce(func.sum(LedgerLine.counted), 0),
            ).where(LedgerLine.project_id == project.id, LedgerLine.unit == "tokens")
        )
    ).one()
    intervals = await projection.intervals_of(session, project.id, now)
    started = intervals[0][0] if intervals else project.created_at
    wall_clock = (now - started).total_seconds()
    commitment = await commitments.latest(session, project.id)
    kept: bool | None = None
    if commitment is not None and commitment.date is not None:
        kept = commitment.state == CommitmentState.MET or (
            commitment.state == CommitmentState.ACCEPTED and now <= commitment.date
        )
    return {
        "requirements": [
            {
                "id": row.id,
                "text": row.text,
                "state": row.state,
                "estimate_runs": row.estimate_runs,
                "actual_runs": row.actual_runs,
                "actual_tokens": row.actual_tokens,
            }
            for row in rows
        ],
        "tokens": {
            "input": int(kinds[0]),
            "output": int(kinds[1]),
            "cache_write": int(kinds[2]),
            "cache_read": int(kinds[3]),
            "counted": int(kinds[4]),
        },
        "reserve_drawn": await budget.reserve_drawn(session, settings, project, now),
        "wall_clock_seconds": int(wall_clock),
        "commitment": None
        if commitment is None or commitment.date is None
        else {
            "kept": kept,
            "date": commitment.date.isoformat(),
            "resets": commitment.resets,
            "state": commitment.state,
        },
    }


receipt_parts: list[Any] = []
"""Called as `(session, settings, project, now, receipt)` to add to a receipt: the time
accounting, findings and the final scorecard register here."""


async def complete(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    caller: Caller,
    now: datetime,
    *,
    why: str,
) -> dict[str, Any]:
    """Complete a project and write its receipt."""
    await commitments.reproject(session, settings, project, now)
    written = await receipt(session, settings, project, now)
    for part in receipt_parts:
        await part(session, settings, project, now, written)
    lifecycle.move(
        session, project, ProjectState.COMPLETED, caller=caller, now=now,
        detail={"why": why, "receipt": written},
    )  # fmt: skip
    await lifecycle.clear_holds(session, project, now)
    await runs.revoke(
        session, project.id, now,
        kinds=frozenset({RunKind.WORK, RunKind.CHECK}), cause="the project is completed",
    )  # fmt: skip
    tokens = written["tokens"]["counted"]
    hours = written["wall_clock_seconds"] / projection.HOUR
    await conversation.platform_line(
        session,
        project.id,
        f"The project is completed ({why}). It used {tokens:,} tokens over {hours:.1f} "
        "hours. The receipt is in the plan.",
        now,
        detail={"kind": "project completed"},
    )
    return written


async def sign_off(
    session: AsyncSession, settings: SettingsService, project: Project, actor: Actor, now: datetime
) -> dict[str, Any]:
    """PRJ-4: the chairman signs off a ready project."""
    if project.state != ProjectState.READY:
        raise Refusal(
            "not_ready",
            f"The project is {project.state}. A Deliver project is signed off once it is ready.",
        )
    return await complete(session, settings, project, actor.caller, now, why="signed off")


async def auto_complete(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> bool:
    """PRJ-4: a ready project completes after `completion.auto_after`; 0 turns this off."""
    if project.state != ProjectState.READY:
        return False
    after = int(await settings.get(session, authority.subject(project), "completion.auto_after"))
    since = await entered(session, project.id, ProjectState.READY)
    if not after or since is None or now - since < timedelta(seconds=after):
        return False
    await complete(
        session, settings, project, PLANNING_JOB, now, why="nobody changed scope after it was ready"
    )
    return True


async def receipt_of(session: AsyncSession, project_id: str) -> dict[str, Any] | None:
    rows = await session.execute(
        select(Event.after, Event.detail)
        .where(Event.project_id == project_id, Event.type == PROJECT_STATE_CHANGED)
        .order_by(Event.id.desc())
    )
    for after, detail in rows.all():
        if (after or {}).get("state") == ProjectState.COMPLETED:
            return (detail or {}).get("receipt")
    return None


async def reopen(
    session: AsyncSession, settings: SettingsService, project: Project, actor: Actor, now: datetime
) -> None:
    """PRJ-6: reopen within `reopen.window` of completion; after that, clone it."""
    assert actor.is_chairman
    if project.state != ProjectState.COMPLETED:
        raise Refusal("not_completed", f"The project is {project.state}, not completed.")
    window = int(await settings.get(session, authority.subject(project), "reopen.window"))
    since = await entered(session, project.id, ProjectState.COMPLETED)
    if since is None or now - since > timedelta(seconds=window):
        raise Refusal(
            "reopen_window_passed",
            f"This project completed more than {window // 86_400} days ago "
            "(`reopen.window`), so it can no longer be reopened.",
            rule=PRJ_6.id,
            hint="Clone it into a new project instead.",
        )
    lifecycle.move(
        session, project, ProjectState.RUNNING, caller=actor.caller, now=now,
        detail={"why": "reopened"},
    )  # fmt: skip
