"""Changing a project's state and hold reasons (section 7.1, PRJ-1 to PRJ-3, INV-21).

Operations and scheduled jobs both go through these functions, so a state changes in one
way only. Later phases add their start checks, stop hooks and purge hooks to the registries.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal
from crewmind.domain.projects.model import (
    HOLDABLE,
    LIFTED_BY,
    PRJ_2,
    PROJECT_MACHINE,
    Hold,
    ProjectState,
    state_under,
)
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Event, HoldReason, Membership, Project, SettingValue

PROJECT_CREATED = event_type("project.created", "A project was created in draft.")
PROJECT_STATE_CHANGED = event_type("project.state_changed", "A project changed state (7.1).")
HOLD_ADDED = event_type("project.hold_added", "A hold reason was added (7.1).")
HOLD_LIFTED = event_type("project.hold_lifted", "A hold reason was lifted (7.1).")
DELETE_REQUESTED = event_type("project.delete_requested", "First step of deleting (PRJ-10).")
PROJECT_PURGED = event_type("project.purged", "A deleted project was purged (PRJ-10).")

ProjectHook = Callable[[AsyncSession, Project, datetime], Awaitable[None]]

start_checks: list[ProjectHook] = []
"""Checks run before a project starts (PRJ-1). Each raises a Refusal to block the start."""
stop_hooks: list[ProjectHook] = []
"""Steps run when a project stops (PRJ-3): later phases revoke runs and void decision items."""
purge_hooks: list[ProjectHook] = []
"""Steps run when a project is purged (PRJ-10): later phases remove chat, memory, artifacts."""


async def active_holds(session: AsyncSession, project_id: str) -> list[HoldReason]:
    rows = await session.scalars(
        select(HoldReason)
        .where(HoldReason.project_id == project_id, HoldReason.lifted_at.is_(None))
        .order_by(HoldReason.added_at)
    )
    return list(rows)


def move(
    session: AsyncSession,
    project: Project,
    target: ProjectState,
    *,
    caller: Caller,
    now: datetime,
    detail: dict[str, Any] | None = None,
) -> None:
    """Move a project to `target`, refusing any transition section 7.1 does not list."""
    source = project.state
    PROJECT_MACHINE.check(source, target)
    project.state = target
    append_event(
        session,
        type=PROJECT_STATE_CHANGED,
        caller=caller,
        at=now,
        subject=("project", project.id),
        project_id=project.id,
        before={"state": source},
        after={"state": target},
        detail=detail,
    )


async def _follow_holds(
    session: AsyncSession, project: Project, *, caller: Caller, now: datetime
) -> None:
    if project.state not in HOLDABLE:
        return
    holds = frozenset(Hold(row.reason) for row in await active_holds(session, project.id))
    target = state_under(holds)
    if target != project.state:
        move(session, project, target, caller=caller, now=now, detail={"holds": sorted(holds)})


async def add_hold(
    session: AsyncSession,
    project: Project,
    hold: Hold,
    *,
    caller: Caller,
    now: datetime,
    lift_at: datetime | None = None,
    note: str | None = None,
    detail: dict[str, Any] | None = None,
) -> bool:
    """Add a hold reason and let the state follow. Returns False if it was already active."""
    if project.state not in HOLDABLE:
        raise Refusal(
            "not_holdable",
            f"A {project.state} project cannot be held or paused (section 7.1).",
            rule=PROJECT_MACHINE.rule_id,
            hint="Only a running, held or paused project takes a hold.",
        )
    if any(row.reason == hold for row in await active_holds(session, project.id)):
        return False
    row = HoldReason(
        project_id=project.id,
        reason=hold,
        note=note,
        lift_at=lift_at,
        detail=detail,
        added_at=now,
        lifted_at=None,
    )
    session.add(row)
    await session.flush()
    append_event(
        session,
        type=HOLD_ADDED,
        caller=caller,
        at=now,
        subject=("project", project.id),
        project_id=project.id,
        after={"hold": hold, "lift_at": lift_at.isoformat() if lift_at else None},
        detail={"note": note, "lifted_by": LIFTED_BY[hold], **(detail or {})},
    )
    await _follow_holds(session, project, caller=caller, now=now)
    return True


async def lift_holds(
    session: AsyncSession,
    project: Project,
    holds: frozenset[Hold],
    *,
    caller: Caller,
    now: datetime,
    cause: str,
) -> list[Hold]:
    """Lift the named hold reasons that are active, and let the state follow."""
    lifted: list[Hold] = []
    for row in await active_holds(session, project.id):
        if Hold(row.reason) in holds:
            row.lifted_at = now
            lifted.append(Hold(row.reason))
            append_event(
                session,
                type=HOLD_LIFTED,
                caller=caller,
                at=now,
                subject=("project", project.id),
                project_id=project.id,
                before={"hold": row.reason},
                detail={"cause": cause},
            )
    if lifted:
        await session.flush()
        await _follow_holds(session, project, caller=caller, now=now)
    return lifted


async def resume(session: AsyncSession, project: Project, *, caller: Caller, now: datetime) -> None:
    """`/resume` (PRJ-2): lift what a chairman may lift; refuse while the budget wall holds."""
    active = await active_holds(session, project.id)
    if not active:
        raise Refusal(
            "not_held",
            f"The project is {project.state}; there is nothing to resume.",
            rule=PROJECT_MACHINE.rule_id,
            hint="Only a held or paused project can be resumed.",
        )
    by_reason = {Hold(row.reason): row for row in active}
    wall = by_reason.get(Hold.BUDGET_WALL)
    if wall is not None:
        numbers = wall.detail or {}
        spent, limit = numbers.get("spent", "unknown"), numbers.get("wall", "unknown")
        raise Refusal(
            "at_budget_wall",
            f"The project is at its budget wall: {spent} tokens spent of a wall of {limit}. "
            "Resuming would spend past it.",
            rule=PRJ_2.id,
            hint=f"The wall lifts by {LIFTED_BY[Hold.BUDGET_WALL]}.",
        )
    if Hold.AUTH_FAILURES in by_reason:
        raise Refusal(
            "credential_failing",
            "The project is paused after 3 authentication failures, and the credential has "
            "not passed a check since.",
            rule=PRJ_2.id,
            hint="Fix the credential and check it, then resume.",
        )
    await lift_holds(
        session,
        project,
        frozenset({Hold.CHAIRMAN, Hold.SKIPPED_CYCLES}),
        caller=caller,
        now=now,
        cause="resume",
    )


async def clear_holds(session: AsyncSession, project: Project, now: datetime) -> None:
    """Stop and delete clear every hold reason (section 7.1)."""
    for row in await active_holds(session, project.id):
        row.lifted_at = now


async def purge(session: AsyncSession, project: Project, *, caller: Caller, now: datetime) -> None:
    """Remove a project and everything it owns (PRJ-10). Only its id survives, in one install
    event, so the purge itself stays on the record (INV-21)."""
    move(session, project, ProjectState.DELETED, caller=caller, now=now)
    for hook in purge_hooks:
        await hook(session, project, now)
    project_id = project.id
    await session.flush()
    for model, column in (
        (HoldReason, HoldReason.project_id),
        (Membership, Membership.project_id),
        (Event, Event.project_id),
    ):
        await session.execute(delete(model).where(column == project_id))
    await session.execute(
        delete(SettingValue).where(
            SettingValue.scope == "project", SettingValue.subject_id == project_id
        )
    )
    await session.delete(project)
    append_event(
        session,
        type=PROJECT_PURGED,
        caller=caller,
        at=now,
        subject=("project", project_id),
        before={"state": ProjectState.DELETING},
        after={"state": ProjectState.DELETED},
    )
