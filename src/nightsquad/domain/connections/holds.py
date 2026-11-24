"""Holding the seats that cannot work, and the start check (CON-5, PRJ-1, LLM-6, EXE-4).

A seat is held while its role needs a connection the project does not have, or while its
seat check fails (no credential pays it, no model, no search for a role that needs the
web). A held seat is paused with the reason on its card, is never woken, and is never
leased. It goes back to work by itself once what it was waiting for is there.

Starting a project shows everything that would hold a seat. The chairman adds what is
missing, or starts without it, and then exactly the seats that need it are held.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller, platform_job
from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.connections import needs
from nightsquad.domain.connections.needs import CON_5
from nightsquad.domain.execution import roster, runs
from nightsquad.domain.execution.model import SEAT_MACHINE, SeatState
from nightsquad.domain.execution.runs import Wait
from nightsquad.domain.projects import lifecycle
from nightsquad.storage.events import append_event
from nightsquad.storage.models import Project, ProjectNeed, Role, Seat

HOLDS = platform_job("connections: seat holds")
SEAT_CHECK = "seat check"
"""The reason a seat is held when its seat check fails, beside the names of open needs."""


@dataclass(frozen=True)
class Blocker:
    """One thing that would hold a seat: an unmet need, or a seat that cannot run."""

    text: str
    seats: list[str]


def _need_key(need: ProjectNeed) -> str:
    return f"{need.kind}:{need.name}"


def _reason(waiting: list[ProjectNeed], check: str | None) -> str:
    parts = [needs.describe(need) for need in waiting]
    said = "Waiting for " + "; ".join(parts) + "." if parts else ""
    if check:
        said = f"{said} It cannot run yet: {check}".strip()
    return said + " It starts working by itself once this is in place."


async def _seat_check(session: AsyncSession, project: Project, seat: Seat) -> str | None:
    """The reason the seat check fails (LLM-6), or None when it passes or will pass soon."""
    try:
        await runs.seat_resolver(session, project, seat)
    except Wait:
        return None
    except Refusal as refusal:
        return refusal.envelope.message
    return None


async def roster_seats(session: AsyncSession, project_id: str) -> list[tuple[Seat, Role]]:
    rows = await session.execute(
        select(Seat, Role)
        .join(Role, Role.id == Seat.role_id)
        .where(Seat.project_id == project_id, Seat.state != SeatState.STOOD_DOWN)
        .order_by(Seat.created_at, Seat.name)
    )
    return [(seat, role) for seat, role in rows.all()]


def _set(
    session: AsyncSession, seat: Seat, target: SeatState, now: datetime, caller: Caller
) -> None:
    if seat.state == target:
        return
    SEAT_MACHINE.check(seat.state, target)
    append_event(
        session,
        type=roster.SEAT_STATE_CHANGED,
        caller=caller,
        at=now,
        subject=("seat", seat.name),
        project_id=seat.project_id,
        before={"state": seat.state},
        after={"state": target, "held_for": seat.held_for, "reason": seat.pause_reason},
    )
    seat.state = target


async def apply(
    session: AsyncSession, project: Project, now: datetime, caller: Caller = HOLDS
) -> list[Seat]:
    """Hold every seat that cannot work and release every held seat that now can. Only
    seats this module holds are released. Returns the seats held now."""
    current = await needs.sync(session, project, now, caller)
    held: list[Seat] = []
    for seat, role in await roster_seats(session, project.id):
        waiting = needs.unmet_for(current, role.slug)
        check = None if waiting else await _seat_check(session, project, seat)
        reasons = [_need_key(need) for need in waiting] + ([SEAT_CHECK] if check else [])
        if reasons:
            if seat.state == SeatState.PAUSED and not seat.held_for:
                continue  # paused for another reason; not ours to change
            seat.held_for, seat.pause_reason = reasons, _reason(waiting, check)
            _set(session, seat, SeatState.PAUSED, now, caller)
            held.append(seat)
        elif seat.held_for:
            seat.held_for, seat.pause_reason = [], None
            _set(session, seat, SeatState.ACTIVE, now, caller)
    await session.flush()
    return held


async def blockers(
    session: AsyncSession, project: Project, now: datetime, caller: Caller, *, keep: bool = True
) -> list[Blocker]:
    """What would hold a seat if the project started now: open needs, and seats whose seat
    check fails. Waived needs are not listed: the chairman already chose to start without
    them. With `keep` off nothing is written, for reading."""
    current = (
        await needs.sync(session, project, now, caller)
        if keep
        else await needs.preview(session, project)
    )
    on_roster = await roster_seats(session, project.id)
    found: list[Blocker] = []
    for need in current:
        if need.state != needs.NeedState.OPEN:
            continue
        names = [seat.display_name for seat, role in on_roster if role.slug in (need.roles or [])]
        found.append(Blocker(text=needs.describe(need).capitalize() + " is missing.", seats=names))
    unmet = {slug for need in current if need.state in needs.UNMET for slug in need.roles or []}
    for seat, role in on_roster:
        if role.slug in unmet:
            continue
        check = await _seat_check(session, project, seat)
        if check:
            found.append(
                Blocker(text=f"{seat.display_name} cannot run: {check}", seats=[seat.display_name])
            )
    return found


async def start_check(
    session: AsyncSession, project: Project, now: datetime, caller: Caller, without_missing: bool
) -> None:
    """PRJ-1, CON-5, LLM-6: start shows what would hold a seat. Without the chairman's word
    to start without it, start is refused with the list. With it, open needs are waived and
    exactly the seats that need them are held."""
    if without_missing:
        needs.waive_open(session, await needs.sync(session, project, now, caller), now, caller)
        await apply(session, project, now, caller)
        return
    found = await blockers(session, project, now, caller)
    if not found:
        return
    listed = " ".join(f"{index}. {item.text}" for index, item in enumerate(found, 1))
    raise Refusal(
        "start_blocked",
        f"Some of the crew could not work yet. {listed}",
        rule=CON_5.id,
        hint="Add what is missing, or start without it: the agents who need it wait until "
        "it is added (`projects start --without-missing`).",
    )


async def lease_guard(session: AsyncSession, project: Project, seat: Seat) -> str | None:
    """CON-5: a run of a seat whose role has an unmet need is never leased. It stays queued,
    and the seat's hold says why."""
    current = list(
        await session.scalars(
            select(ProjectNeed).where(
                ProjectNeed.project_id == project.id, ProjectNeed.state.in_(needs.UNMET)
            )
        )
    )
    if not current:
        return None
    role = await session.get(Role, seat.role_id)
    assert role is not None
    waiting = needs.unmet_for(current, role.slug)
    return _reason(waiting, None) if waiting else None


async def after_roster_change(session: AsyncSession, project: Project, now: datetime) -> None:
    if project.state != "draft":
        await apply(session, project, now)


lifecycle.start_checks.append(start_check)
runs.seat_guards.append(lease_guard)
roster.roster_hooks.append(after_roster_change)
