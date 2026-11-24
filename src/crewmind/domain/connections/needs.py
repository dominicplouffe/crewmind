"""What a project's roles need from outside, and whether they have it (CON-5, 7.18).

A role declares the connections it needs by name. A spec may add needs. The platform keeps
one row per need and project: open until the chairman marks it done or a connection of its
name meets it, waived when the chairman starts without it, dropped when no role on the
roster needs it any more. A need's name says what it is for, not what fills it: the
chairman may fill it under any names, and the agents work out which is which.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW, StateMachine
from crewmind.domain.execution.model import SeatState
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Project, ProjectNeed, Role, Seat

CON_5 = rules.register(
    Rule("CON-5", "No seat runs while a need of its role is open; start shows what is missing.")
)

NEED_CHANGED = event_type("need.state_changed", "A project's need changed state (7.18).")


class NeedState(StrEnum):
    OPEN = "open"
    MET = "met"
    """Met by an attached connection of its name, with no word from the chairman."""
    DONE = "done"
    """Marked done by the chairman: what it asks for is added, under any names."""
    WAIVED = "waived"
    DROPPED = "dropped"


class NeedKind(StrEnum):
    SECRET = "secret"
    VARIABLE = "variable"
    MCP_SERVER = "mcp_server"


N = NeedState
NEED_MACHINE = StateMachine(
    "need",
    "7.18",
    [
        (NEW, N.OPEN),
        (N.OPEN, N.MET),
        (N.OPEN, N.WAIVED),
        (N.WAIVED, N.MET),
        (N.MET, N.OPEN),
        (N.OPEN, N.DONE),
        (N.WAIVED, N.DONE),
        (N.DONE, N.OPEN),
        (N.OPEN, N.DROPPED),
        (N.WAIVED, N.DROPPED),
        (N.DROPPED, N.OPEN),
        (N.MET, N.DROPPED),
        (N.DONE, N.DROPPED),
    ],
)
UNMET = (N.OPEN, N.WAIVED)
"""Needs that hold the seats of the roles that have them."""

assume_met: ContextVar[bool] = ContextVar("assume_met", default=False)
"""Set by the rehearsal (RHS-1): a fire drill treats every need as provided, and lists
the needs as setup still to do instead of holding the scripted crew."""

Meets = Callable[[AsyncSession, Project, ProjectNeed], Awaitable[bool]]
meets: list[Meets] = []
"""Ways a need can be met. The connections of this phase add theirs; with none, a need is
open until the roles that have it leave the roster."""


async def roles_on_roster(session: AsyncSession, project_id: str) -> list[Role]:
    # Distinct ids first: Postgres cannot compare the role's JSON columns for DISTINCT.
    on_roster = (
        select(Seat.role_id)
        .where(Seat.project_id == project_id, Seat.state != SeatState.STOOD_DOWN)
        .distinct()
    )
    rows = await session.scalars(select(Role).where(Role.id.in_(on_roster)).order_by(Role.slug))
    return list(rows)


async def declared(session: AsyncSession, project: Project) -> dict[tuple[str, str], set[str]]:
    """Every need of the project, with the roles that have it: what each role on the roster
    declares, and what the spec it came from asked for (LIB-4). Names match whatever their
    case (CON-1); the first spelling seen is kept."""
    found: dict[tuple[str, str], set[str]] = {}
    spelled: dict[tuple[str, str], tuple[str, str]] = {}

    def add(kind: str, name: str, roles: set[str]) -> None:
        key = spelled.setdefault((kind, name.lower()), (kind, name))
        found.setdefault(key, set()).update(roles)

    roster = await roles_on_roster(session, project.id)
    on_roster = {role.slug for role in roster}
    for role in roster:
        for name in role.credential_names or []:
            add(NeedKind.SECRET, str(name), {role.slug})
    extras: dict[str, Any] = project.extras or {}
    for asked in extras.get("requested", []):
        # CON-14: what an agent asked for and the chairman approved.
        roles = {str(slug) for slug in asked.get("roles", [])} & on_roster
        if roles:
            add(str(asked["kind"]), str(asked["name"]), roles)
    for grant in extras.get("credentials", []):
        roles = {str(slug) for slug in grant.get("roles", [])} & on_roster
        if roles:
            add(str(grant.get("kind", NeedKind.SECRET)), str(grant["name"]), roles)
    return found


def _move(
    session: AsyncSession, need: ProjectNeed, target: NeedState, now: datetime, caller: Caller
) -> None:
    if need.state == target:
        return
    NEED_MACHINE.check(need.state, target)
    append_event(
        session,
        type=NEED_CHANGED,
        caller=caller,
        at=now,
        subject=("need", f"{need.kind}:{need.name}"),
        project_id=need.project_id,
        before={"state": need.state},
        after={"state": target, "roles": need.roles},
    )
    need.state, need.changed_at = target, now


async def _is_met(session: AsyncSession, project: Project, need: ProjectNeed) -> bool:
    if assume_met.get():
        return True
    for way in meets:
        if await way(session, project, need):
            return True
    return False


async def sync(
    session: AsyncSession, project: Project, now: datetime, caller: Caller
) -> list[ProjectNeed]:
    """Bring the project's needs in line with its roster and its connections. Safe to call
    at any time; it changes only what is out of date. Returns every need, dropped ones
    included."""
    wanted = await declared(session, project)
    rows = {
        (row.kind, row.name): row
        for row in await session.scalars(
            select(ProjectNeed).where(ProjectNeed.project_id == project.id)
        )
    }
    for key, roles in wanted.items():
        row = rows.get(key)
        if row is None:
            NEED_MACHINE.check(NEW, N.OPEN)
            row = ProjectNeed(
                project_id=project.id,
                kind=key[0],
                name=key[1],
                roles=sorted(roles),
                source="role",
                state=N.OPEN,
                created_at=now,
                changed_at=now,
            )
            session.add(row)
            rows[key] = row
            append_event(
                session,
                type=NEED_CHANGED,
                caller=caller,
                at=now,
                subject=("need", f"{row.kind}:{row.name}"),
                project_id=project.id,
                after={"state": N.OPEN, "roles": row.roles},
            )
        elif row.state == N.DROPPED:
            _move(session, row, N.OPEN, now, caller)
        row.roles = sorted(roles)
    for key, row in rows.items():
        if key not in wanted and row.state != N.DROPPED:
            _move(session, row, N.DROPPED, now, caller)
            continue
        if row.state in (N.DROPPED, N.DONE):
            continue  # the chairman's word is final; nothing second-guesses it (CON-5)
        met = await _is_met(session, project, row)
        if met and row.state in UNMET:
            _move(session, row, N.MET, now, caller)
        elif not met and row.state == N.MET:
            _move(session, row, N.OPEN, now, caller)
    await session.flush()
    return list(rows.values())


async def preview(session: AsyncSession, project: Project) -> list[ProjectNeed]:
    """The needs as `sync` would leave them, without changing anything: for reading."""
    stored = {
        (row.kind, row.name): row
        for row in await session.scalars(
            select(ProjectNeed).where(ProjectNeed.project_id == project.id)
        )
    }
    found: list[ProjectNeed] = []
    for (kind, name), roles in (await declared(session, project)).items():
        row = stored.get((kind, name))
        state = row.state if row is not None and row.state in (N.WAIVED, N.DONE) else N.OPEN
        need = ProjectNeed(
            project_id=project.id, kind=kind, name=name, roles=sorted(roles), source="role",
            state=state,
        )  # fmt: skip
        if state != N.DONE and await _is_met(session, project, need):
            need.state = N.MET
        found.append(need)
    return found


def unmet_for(needs: list[ProjectNeed], role_slug: str) -> list[ProjectNeed]:
    """The needs of one role that hold its seats."""
    return [need for need in needs if need.state in UNMET and role_slug in (need.roles or [])]


def waive_open(
    session: AsyncSession, needs: list[ProjectNeed], now: datetime, caller: Caller
) -> list[ProjectNeed]:
    """Start without what is missing: every open need is waived for now (CON-5)."""
    waived = [need for need in needs if need.state == N.OPEN]
    for need in waived:
        _move(session, need, N.WAIVED, now, caller)
    return waived


def mark_done(session: AsyncSession, need: ProjectNeed, now: datetime, caller: Caller) -> None:
    """CON-5: the chairman says what the need asks for is added. Their word is final."""
    _move(session, need, N.DONE, now, caller)


def reopen(session: AsyncSession, need: ProjectNeed, now: datetime, caller: Caller) -> None:
    """CON-5: the chairman takes back a done mark; the need is open again."""
    _move(session, need, N.OPEN, now, caller)


KIND_WORDS = {
    NeedKind.SECRET: "secret",
    NeedKind.VARIABLE: "variable",
    NeedKind.MCP_SERVER: "MCP server",
}


def describe(need: ProjectNeed) -> str:
    """One need in plain words: "the secret wordpress, for blog-writer"."""
    roles = ", ".join(need.roles or [])
    return f"the {KIND_WORDS.get(NeedKind(need.kind), need.kind)} {need.name}, for {roles}"
