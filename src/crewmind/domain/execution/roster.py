"""The roster: roles, teams and seats (EXE-1, section 7.12)."""

from __future__ import annotations

import tomllib
from datetime import datetime
from importlib import resources

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution.model import (
    EXE_1,
    SEAT_MACHINE,
    TEAM_MACHINE,
    SeatKind,
    SeatState,
    TeamState,
)
from crewmind.domain.projects import lifecycle
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import SettingsService, Subject
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Project, Role, Seat, Team

TEAM_HIRED = event_type("team.hired", "A team was hired (EXE-1).")
TEAM_STOOD_DOWN = event_type("team.stood_down", "A team was stood down (7.12).")
TEAM_RECALLED = event_type("team.recalled", "A team was recalled (7.12).")
SEAT_CREATED = event_type("seat.created", "A seat was created (7.12).")
SEAT_STATE_CHANGED = event_type("seat.state_changed", "A seat changed state (7.12).")

CEO_ROLE = "CEO"
TEAM_MEMBERS_MAX = 12


async def ensure_starter_roles(session: AsyncSession, now: datetime) -> None:
    """Load the packaged starter roles once."""
    if await session.scalar(select(func.count()).select_from(Role)):
        return
    text = resources.files(__package__).joinpath("starter_roles.toml").read_text(encoding="utf-8")
    for entry in tomllib.loads(text)["roles"]:
        session.add(
            Role(
                version=1,
                credential_names=[],
                min_class=None,
                created_at=now,
                **entry,
            )
        )
    await session.flush()


async def newest_role(session: AsyncSession, name: str) -> Role:
    role = await session.scalar(
        select(Role).where(Role.name == name).order_by(Role.version.desc()).limit(1)
    )
    if role is None:
        raise Refusal(
            "role_not_found",
            f"There is no role named {name}.",
            kind=RefusalKind.NOT_FOUND,
            hint="List the roles with `crewmind roles list`.",
        )
    return role


async def ceo_of(session: AsyncSession, project_id: str) -> Seat:
    seat = await session.scalar(
        select(Seat).where(Seat.project_id == project_id, Seat.kind == SeatKind.CEO)
    )
    assert seat is not None, "every project has a CEO seat (EXE-1)"
    return seat


def _new_seat(
    session: AsyncSession,
    project_id: str,
    role: Role,
    name: str,
    kind: str,
    now: datetime,
    caller: Caller,
    *,
    team_id: str | None = None,
    is_lead: bool = False,
) -> Seat:
    SEAT_MACHINE.check("(new)", SeatState.ACTIVE)
    seat = Seat(
        project_id=project_id,
        team_id=team_id,
        role_id=role.id,
        name=name,
        kind=kind,
        is_lead=is_lead,
        state=SeatState.ACTIVE,
        pause_reason=None,
        created_at=now,
    )
    session.add(seat)
    append_event(
        session,
        type=SEAT_CREATED,
        caller=caller,
        at=now,
        subject=("seat", name),
        project_id=project_id,
        after={"state": SeatState.ACTIVE, "kind": kind, "role": role.name, "lead": is_lead},
    )
    return seat


async def create_ceo(
    session: AsyncSession, project: Project, now: datetime, caller: Caller
) -> None:
    """Every project gets its CEO seat and its channels when it is created (EXE-1, MSG-1)."""
    await ensure_starter_roles(session, now)
    role = await newest_role(session, CEO_ROLE)
    _new_seat(session, project.id, role, "CEO", SeatKind.CEO, now, caller)
    for name, kind in (
        (conversation.PROJECT_CHAT, conversation.ChannelKind.PROJECT),
        (conversation.LEADERSHIP, conversation.ChannelKind.LEADERSHIP),
    ):
        await conversation.ensure_channel(session, project.id, name, kind, now)


lifecycle.created_hooks.append(create_ceo)


async def hire_team(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    *,
    name: str,
    role_name: str,
    members: int,
    caller: Caller,
    now: datetime,
) -> Team:
    """EXE-1: a team is seats created from one pinned role version, within `teams.max`.
    Its first member leads it. A CEO hire takes the same path as a chairman's."""
    role = await newest_role(session, role_name)
    if role.seat_kind == SeatKind.CEO:
        raise Refusal(
            "second_ceo",
            "A project has exactly one CEO; a team cannot be hired from a CEO role.",
            rule=EXE_1.id,
            hint="Choose another role.",
        )
    if not 1 <= members <= TEAM_MEMBERS_MAX:
        raise Refusal(
            "team_size",
            f"A team has 1 to {TEAM_MEMBERS_MAX} members; {members} were asked for.",
            rule=EXE_1.id,
        )
    limit = await settings.get(
        session, Subject(Scope.PROJECT, project.id, project.type), "teams.max"
    )
    teams = await session.scalar(
        select(func.count())
        .select_from(Team)
        .where(Team.project_id == project.id, Team.state == TeamState.ACTIVE)
    )
    if (teams or 0) >= limit:
        raise Refusal(
            "too_many_teams",
            f"The project has {teams} active teams and `teams.max` is {limit}.",
            rule=EXE_1.id,
            hint="Stand a team down first, or ask the chairman to raise teams.max.",
        )
    taken = await session.scalar(
        select(func.count())
        .select_from(Team)
        .where(Team.project_id == project.id, Team.name == name)
    )
    if taken:
        raise Refusal("team_exists", f"There is already a team named {name}.", rule=EXE_1.id)
    TEAM_MACHINE.check("(new)", TeamState.ACTIVE)
    team = Team(
        project_id=project.id, name=name, role_id=role.id, state=TeamState.ACTIVE, created_at=now
    )
    session.add(team)
    await session.flush()
    for index in range(members):
        seat_name = name if members == 1 else f"{name}-{index + 1}"
        _new_seat(
            session,
            project.id,
            role,
            seat_name,
            role.seat_kind,
            now,
            caller,
            team_id=team.id,
            is_lead=index == 0,
        )
    await conversation.ensure_channel(
        session, project.id, f"team {name}", conversation.ChannelKind.TEAM, now, team.id
    )
    append_event(
        session,
        type=TEAM_HIRED,
        caller=caller,
        at=now,
        subject=("team", name),
        project_id=project.id,
        after={"state": TeamState.ACTIVE, "role": role.name, "version": role.version},
        detail={"members": members},
    )
    await conversation.platform_line(
        session,
        project.id,
        f"Team {name} hired: {members} x {role.name}.",
        now,
        detail={"kind": "team hired", "team": name},
    )
    return team


async def team_named(session: AsyncSession, project_id: str, name: str) -> Team:
    team = await session.scalar(
        select(Team).where(Team.project_id == project_id, Team.name == name)
    )
    if team is None:
        raise Refusal(
            "team_not_found", f"There is no team named {name}.", kind=RefusalKind.NOT_FOUND
        )
    return team


async def set_team_state(
    session: AsyncSession,
    project: Project,
    name: str,
    target: TeamState,
    *,
    caller: Caller,
    now: datetime,
) -> Team:
    """Section 7.12: stand a team down, or recall it with its history intact. Its seats follow."""
    from crewmind.domain.execution import runs

    team = await team_named(session, project.id, name)
    TEAM_MACHINE.check(team.state, target)
    seats = list(await session.scalars(select(Seat).where(Seat.team_id == team.id)))
    if target is TeamState.STOOD_DOWN:
        busy = [seat.name for seat in seats if await runs.has_open_run(session, seat.id)]
        if busy:
            raise Refusal(
                "team_holds_work",
                f"Team {name} still holds work: {', '.join(busy)} has a run in progress.",
                rule=EXE_1.id,
                hint="Wait for the run to end, then stand the team down.",
            )
    before = team.state
    team.state = target
    seat_target = SeatState.STOOD_DOWN if target is TeamState.STOOD_DOWN else SeatState.ACTIVE
    for seat in seats:
        SEAT_MACHINE.check(seat.state, seat_target)
        append_event(
            session,
            type=SEAT_STATE_CHANGED,
            caller=caller,
            at=now,
            subject=("seat", seat.name),
            project_id=project.id,
            before={"state": seat.state},
            after={"state": seat_target},
        )
        seat.state = seat_target
    append_event(
        session,
        type=TEAM_STOOD_DOWN if target is TeamState.STOOD_DOWN else TEAM_RECALLED,
        caller=caller,
        at=now,
        subject=("team", name),
        project_id=project.id,
        before={"state": before},
        after={"state": target},
    )
    return team
