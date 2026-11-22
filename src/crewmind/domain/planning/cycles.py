"""Operate: cycles, the roll and its scorecard, recurring requirements (PRJ-8, 7.13)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.conversation import service as conversation
from crewmind.domain.decisions import flags, reviews
from crewmind.domain.execution import notices
from crewmind.domain.execution.model import RunKind
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import authority, completion, projection
from crewmind.domain.planning.authority import Actor
from crewmind.domain.planning.model import CYCLE_MACHINE, OPEN_SCOPE, CycleState, RequirementState
from crewmind.domain.planning.readiness import PLANNING_JOB, move
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.model import HOLDABLE, Hold, ProjectState, ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Cycle, LedgerLine, Project, Requirement, Run

PRJ_8 = rules.register(
    Rule("PRJ-8", "Only the platform rolls a cycle; two skipped cycles pause the project.")
)
CYCLE_CHANGED = event_type("cycle.state_changed", "A cycle opened or closed (7.13).")
CYCLE_EDITED = event_type("cycle.edited", "A cycle's due time or narrative was written.")
S = CycleState
R = RequirementState
SKIPPED_BEFORE_PAUSE = 2  # PRJ-8: 2 consecutive skipped cycles pause the project
NARRATIVES_SHOWN = 3  # PRJ-8: the CEO gets the last 3 cycle narratives verbatim
NARRATIVE_MIN_CHARACTERS = 20
QUARTER_MONTHS = (1, 4, 7, 10)


def _midnight(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def next_roll(period: str, roll_day: int, after: datetime) -> datetime:
    """The first roll strictly after `after`, a time in the project's timezone (PRJ-8).
    Weekly rolls on weekday `roll_day` (0 is Monday); monthly and quarterly on day
    `roll_day` of the month."""
    if period == "hourly":
        return after.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if period == "daily":
        return _midnight(after) + timedelta(days=1)
    if period == "weekly":
        days = (roll_day - after.weekday()) % 7 or 7
        return _midnight(after) + timedelta(days=days)
    day = min(max(roll_day, 1), 28)
    months = QUARTER_MONTHS if period == "quarterly" else tuple(range(1, 13))
    year = after.year
    while True:
        for month in months:
            candidate = _midnight(after).replace(year=year, month=month, day=day)
            if candidate > after:
                return candidate
        year += 1


async def _calendar(
    session: AsyncSession, settings: SettingsService, project: Project
) -> tuple[ZoneInfo, str, int, Any]:
    values = await settings.effective(session, authority.subject(project))
    return (
        ZoneInfo(str(values["project.timezone"])),
        str(values["cycle.period"]),
        int(values["cycle.roll_day"]),
        values["cycle.due_time"],
    )


async def open_cycle(session: AsyncSession, project_id: str) -> Cycle | None:
    return await session.scalar(
        select(Cycle).where(Cycle.project_id == project_id, Cycle.state == S.OPEN)
    )


async def recent(session: AsyncSession, project_id: str, limit: int) -> list[Cycle]:
    rows = await session.scalars(
        select(Cycle)
        .where(Cycle.project_id == project_id, Cycle.state != S.OPEN)
        .order_by(Cycle.number.desc())
        .limit(limit)
    )
    return list(rows)


def _record(session: AsyncSession, cycle: Cycle, before: str, now: datetime) -> None:
    CYCLE_MACHINE.check(before, cycle.state)
    append_event(
        session,
        type=CYCLE_CHANGED,
        caller=PLANNING_JOB,
        at=now,
        subject=("cycle", str(cycle.number)),
        project_id=cycle.project_id,
        before={"state": before},
        after={"state": cycle.state},
        detail={"scorecard": cycle.scorecard} if cycle.scorecard else None,
    )


async def _open(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> Cycle:
    """7.13: open the one cycle that covers now. Its end is the next roll."""
    zone, period, roll_day, due_time = await _calendar(session, settings, project)
    ends = next_roll(period, roll_day, now.astimezone(zone)).astimezone(now.tzinfo)
    due = ends
    if isinstance(due_time, int):
        length = ends - _previous_roll(period, roll_day, now.astimezone(zone), ends, zone)
        candidate = ends - length + timedelta(seconds=due_time)
        due = candidate if now < candidate <= ends else ends
    last = await session.scalar(
        select(func.max(Cycle.number)).where(Cycle.project_id == project.id)
    )
    cycle = Cycle(
        project_id=project.id,
        number=int(last or 0) + 1,
        state=S.OPEN,
        opened_at=now,
        ends_at=ends,
        due_at=due,
        narrative_by_ceo=False,
    )
    session.add(cycle)
    await session.flush()
    _record(session, cycle, "(new)", now)
    return cycle


def _previous_roll(
    period: str, roll_day: int, local_now: datetime, ends: datetime, zone: ZoneInfo
) -> datetime:
    """The roll that began the period `ends` closes."""
    probe = local_now
    for _ in range(400):
        probe -= timedelta(hours=1) if period == "hourly" else timedelta(days=1)
        if next_roll(period, roll_day, probe).astimezone(ends.tzinfo) < ends:
            return next_roll(period, roll_day, probe).astimezone(ends.tzinfo)
    return ends


async def _scorecard(
    session: AsyncSession, project: Project, cycle: Cycle, now: datetime
) -> tuple[dict[str, Any], bool, int]:
    """What the cycle achieved: each requirement's state, runs and tokens. Returns it with
    whether every recurring requirement was met by the due time, and the work runs."""
    rows = list(
        await session.scalars(
            select(Requirement)
            .where(
                Requirement.project_id == project.id,
                Requirement.state.in_([*OPEN_SCOPE, R.MET]),
            )
            .order_by(Requirement.id)
        )
    )
    work_runs = int(
        await session.scalar(
            select(func.count())
            .select_from(Run)
            .where(
                Run.project_id == project.id,
                Run.kind == RunKind.WORK,
                Run.started_at.is_not(None),
                Run.started_at >= cycle.opened_at,
                Run.started_at <= now,
            )
        )
        or 0
    )
    tokens = int(
        await session.scalar(
            select(func.coalesce(func.sum(LedgerLine.counted), 0)).where(
                LedgerLine.project_id == project.id,
                LedgerLine.unit == "tokens",
                LedgerLine.at >= cycle.opened_at,
                LedgerLine.at <= now,
            )
        )
        or 0
    )
    recurring = [row for row in rows if row.recurring]
    on_time = [
        row
        for row in recurring
        if row.state == R.MET and row.met_at is not None and row.met_at <= cycle.due_at
    ]
    card = {
        "cycle": cycle.number,
        "recurring_met": len(on_time),
        "recurring_total": len(recurring),
        "work_runs": work_runs,
        "tokens": tokens,
        "requirements": [
            {"id": row.id, "text": row.text, "state": row.state, "recurring": row.recurring}
            for row in rows
        ],
    }
    return card, len(on_time) == len(recurring), work_runs


async def _was_stopped(
    session: AsyncSession, project: Project, cycle: Cycle, now: datetime
) -> bool:
    """Whether the project was held or paused at any time in the cycle."""
    running = await projection.intervals_of(session, project.id, now)
    inside = sum(
        (min(end, now) - max(start, cycle.opened_at)).total_seconds()
        for start, end in running
        if min(end, now) > max(start, cycle.opened_at)
    )
    return inside < (now - cycle.opened_at).total_seconds()


async def close(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    cycle: Cycle,
    now: datetime,
) -> Cycle:
    """PRJ-8: close a cycle as completed, missed or skipped; write its scorecard, and a
    stub narrative if the CEO wrote none; reopen recurring requirements."""
    card, all_met, work_runs = await _scorecard(session, project, cycle, now)
    period = (await _calendar(session, settings, project))[1]
    if work_runs == 0 and await _was_stopped(session, project, cycle, now):
        state = S.SKIPPED
    elif all_met:
        state = S.COMPLETED
    else:
        state = S.MISSED
    cycle.state, cycle.scorecard, cycle.closed_at = state, card, now
    if not cycle.narrative:
        cycle.narrative = (
            f"No narrative was written. Cycle {cycle.number} was {state}: "
            f"{card['recurring_met']} of {card['recurring_total']} recurring requirements "
            f"were met on time, in {work_runs} work runs."
        )
    _record(session, cycle, S.OPEN, now)
    if state == S.MISSED:
        await flags.event(
            session, settings, project, "cycle missed",
            f"Cycle {cycle.number} closed as missed: {card['recurring_met']} of "
            f"{card['recurring_total']} recurring requirements were met on time.",
            now, key=str(cycle.number),
        )  # fmt: skip
    if period in reviews.CYCLE_PERIODS:
        await reviews.build(session, settings, project, now)
    reopened = 0
    for requirement in await session.scalars(
        select(Requirement).where(
            Requirement.project_id == project.id,
            Requirement.recurring,
            Requirement.state == R.MET,
        )
    ):
        requirement.met_at, requirement.failures, requirement.escalated = None, 0, False
        move(session, requirement, R.ACCEPTED, PLANNING_JOB, now, {"cycle_roll": cycle.number})
        reopened += 1
    text = (
        f"Cycle {cycle.number} closed as {state}: {card['recurring_met']} of "
        f"{card['recurring_total']} recurring requirements were met on time. "
        f"{reopened} recurring requirements are open again."
    )
    await conversation.platform_line(
        session, project.id, text, now,
        detail={"kind": f"cycle {state}", "cycle": cycle.number},
    )  # fmt: skip
    ceo = await ceo_of(session, project.id)
    notices.notify(session, project.id, ceo.id, "cycle closed", text, now, urgent=True)
    return cycle


async def roll(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """PRJ-8, 7.13: keep exactly one cycle open on a running Operate project. A cycle
    closes at its end whatever the project's state; a new one opens only while it runs,
    so a paused project resumes into exactly one new cycle, however many it missed. Two
    skipped cycles in a row pause the project."""
    if project.type != ProjectType.OPERATE or project.state not in HOLDABLE:
        return
    current = await open_cycle(session, project.id)
    if current is not None and now >= current.ends_at:
        await close(session, settings, project, current, now)
        current = None
        last_two = await recent(session, project.id, SKIPPED_BEFORE_PAUSE)
        if len(last_two) == SKIPPED_BEFORE_PAUSE and all(c.state == S.SKIPPED for c in last_two):
            added = await lifecycle.add_hold(
                session,
                project,
                Hold.SKIPPED_CYCLES,
                caller=PLANNING_JOB,
                now=now,
                note="Two cycles in a row were skipped.",
                detail={"cycles": [c.number for c in last_two]},
            )
            if added:
                await conversation.platform_line(
                    session,
                    project.id,
                    "Two cycles in a row were skipped, so the project is paused. Resume it "
                    "when it should run again.",
                    now,
                    detail={"kind": "skipped cycles", "alarm": True},
                )
    if current is not None and now >= current.due_at:
        await _flag_late_requirements(session, settings, project, current, now)
    if current is None and project.state == ProjectState.RUNNING:
        await _open(session, settings, project, now)


async def _flag_late_requirements(
    session: AsyncSession, settings: SettingsService, project: Project, cycle: Cycle, now: datetime
) -> None:
    """HUM-6: a recurring requirement still open at its cycle's due time is flagged."""
    late = await session.scalars(
        select(Requirement).where(
            Requirement.project_id == project.id,
            Requirement.recurring,
            Requirement.state.in_(OPEN_SCOPE),
        )
    )
    for requirement in late:
        await flags.event(
            session, settings, project, "recurring requirement missed",
            f"Recurring requirement {requirement.id} was still open at the due time of "
            f"cycle {cycle.number}.",
            now, key=f"{cycle.number}:{requirement.id}",
        )  # fmt: skip


async def write_narrative(
    session: AsyncSession, project: Project, caller: Caller, text: str, now: datetime
) -> Cycle:
    """PRJ-8: the CEO writes the open cycle's narrative; the platform keeps it verbatim."""
    cycle = await open_cycle(session, project.id)
    if cycle is None:
        raise Refusal("no_open_cycle", "No cycle is open to write a narrative for.", rule=PRJ_8.id)
    if len(text.strip()) < NARRATIVE_MIN_CHARACTERS:
        raise Refusal(
            "narrative_too_short",
            f"A narrative says what happened, in at least {NARRATIVE_MIN_CHARACTERS} characters.",
            rule=PRJ_8.id,
        )
    cycle.narrative, cycle.narrative_by_ceo = text.strip(), True
    append_event(
        session,
        type=CYCLE_EDITED,
        caller=caller,
        at=now,
        subject=("cycle", str(cycle.number)),
        project_id=project.id,
        after={"narrative": True},
    )
    return cycle


async def set_due(
    session: AsyncSession,
    project: Project,
    actor: Actor,
    due_at: datetime,
    source: str,
    now: datetime,
) -> Cycle:
    """PRJ-8: a cycle-specific due time with a cited source overrides the calendar."""
    assert actor.is_chairman
    cycle = await open_cycle(session, project.id)
    if cycle is None:
        raise Refusal("no_open_cycle", "No cycle is open.", rule=PRJ_8.id)
    if not cycle.opened_at < due_at <= cycle.ends_at:
        raise Refusal(
            "due_time_outside_the_cycle",
            f"The due time must fall inside the cycle, which ends on "
            f"{cycle.ends_at.strftime('%d %b %Y %H:%M UTC')}.",
            rule=PRJ_8.id,
        )
    cycle.due_at = due_at
    append_event(
        session,
        type=CYCLE_EDITED,
        caller=actor.caller,
        at=now,
        subject=("cycle", str(cycle.number)),
        project_id=project.id,
        after={"due_at": due_at.isoformat()},
        detail={"source": source.strip()},
    )
    return cycle


async def complete_operation(
    session: AsyncSession, settings: SettingsService, project: Project, actor: Actor, now: datetime
) -> dict[str, Any]:
    """PRJ-8, R-62: the chairman completes an Operate project, with a final scorecard."""
    assert actor.is_chairman
    if project.type != ProjectType.OPERATE:
        raise Refusal("only_operate_completes", "Only an Operate project is completed this way.")
    if project.state not in HOLDABLE:
        raise Refusal("not_running", f"The project is {project.state}; it cannot be completed now.")
    current = await open_cycle(session, project.id)
    if current is not None:
        await close(session, settings, project, current, now)
    return await completion.complete(
        session, settings, project, actor.caller, now, why="completed by the chairman"
    )


async def add_scorecards(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    now: datetime,
    receipt: dict[str, Any],
) -> None:
    """An Operate receipt carries every cycle with how it closed, and the final scorecard."""
    if project.type != ProjectType.OPERATE:
        return
    rows = list(
        await session.scalars(
            select(Cycle).where(Cycle.project_id == project.id).order_by(Cycle.number)
        )
    )
    receipt["cycles"] = [{"number": row.number, "state": row.state} for row in rows]
    receipt["final_scorecard"] = rows[-1].scorecard if rows else None


completion.receipt_parts.append(add_scorecards)


async def narratives(session: AsyncSession, project_id: str) -> list[Cycle]:
    """The last 3 closed cycles, oldest first, for the CEO's context pack (PRJ-8)."""
    return list(reversed(await recent(session, project_id, NARRATIVES_SHOWN)))
