"""The roster: roles, teams and seats (EXE-1, section 7.12)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller, platform_job
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.execution import names as agent_names
from nightsquad.domain.execution.model import (
    EXE_1,
    EXE_18,
    SEAT_MACHINE,
    TEAM_MACHINE,
    SeatKind,
    SeatState,
    TeamState,
)
from nightsquad.domain.library import service as library
from nightsquad.domain.projects import lifecycle
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import Project, Role, Seat, Team

TEAM_HIRED = event_type("team.hired", "A team was hired (EXE-1).")
TEAM_STOOD_DOWN = event_type("team.stood_down", "A team was stood down (7.12).")
TEAM_RECALLED = event_type("team.recalled", "A team was recalled (7.12).")
SEAT_CREATED = event_type("seat.created", "A seat was created (7.12).")
SEAT_STATE_CHANGED = event_type("seat.state_changed", "A seat changed state (7.12).")
SEAT_RENAMED = event_type("seat.renamed", "The chairman changed an agent's name (EXE-18).")

CEO_ROLE = "ceo"
TEAM_MEMBERS_MAX = 12


async def ensure_starter_roles(session: AsyncSession, now: datetime) -> None:
    """Load the library shipped with Nightsquad, once (LIB-3)."""
    await library.load_starter(session, now)


async def newest_role(session: AsyncSession, name: str) -> Role:
    return await library.role_named(session, name)


async def ceo_of(session: AsyncSession, project_id: str) -> Seat:
    seat = await session.scalar(
        select(Seat).where(Seat.project_id == project_id, Seat.kind == SeatKind.CEO)
    )
    assert seat is not None, "every project has a CEO seat (EXE-1)"
    return seat


async def names_in_use(session: AsyncSession, project_id: str) -> set[str]:
    """Every seat name and display name in the project, active or not (EXE-18)."""
    rows = await session.execute(
        select(Seat.name, Seat.display_name).where(Seat.project_id == project_id)
    )
    return {name for row in rows.all() for name in row}


async def _new_seat(
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
    given_name: bool = False,
) -> Seat:
    """EXE-18: a seat hired with a name shows that name; any other draws one from the pool."""
    SEAT_MACHINE.check("(new)", SeatState.ACTIVE)
    display_name = (
        name
        if given_name
        else agent_names.draw(project_id, await names_in_use(session, project_id))
    )
    seat = Seat(
        project_id=project_id,
        team_id=team_id,
        role_id=role.id,
        name=name,
        display_name=display_name,
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
        after={
            "state": SeatState.ACTIVE,
            "kind": kind,
            "role": role.name,
            "lead": is_lead,
            "display_name": display_name,
        },
    )
    return seat


async def rename_seat(
    session: AsyncSession,
    project_id: str,
    seat_name: str,
    display_name: str,
    caller: Caller,
    now: datetime,
) -> Seat:
    """EXE-18: the chairman changes the name an agent is shown by. The seat's identity stays;
    the new name is never empty and no other seat in the project has it."""
    seat = await session.scalar(
        select(Seat).where(Seat.project_id == project_id, Seat.name == seat_name)
    )
    if seat is None:
        raise Refusal(
            "seat_not_found", f"There is no agent named {seat_name}.", kind=RefusalKind.NOT_FOUND
        )
    wanted = agent_names.tidy(display_name)
    if not wanted:
        raise Refusal("name_is_empty", "An agent's name cannot be empty.", rule=EXE_18.id)
    if len(wanted) > agent_names.DISPLAY_NAME_MAX:
        raise Refusal(
            "name_too_long",
            f"An agent's name has at most {agent_names.DISPLAY_NAME_MAX} characters.",
            rule=EXE_18.id,
        )
    others = await session.execute(
        select(Seat.name, Seat.display_name).where(
            Seat.project_id == project_id, Seat.id != seat.id
        )
    )
    if wanted.casefold() in {name.casefold() for row in others.all() for name in row}:
        raise Refusal(
            "name_taken",
            f"Another agent in this project is already called {wanted}.",
            rule=EXE_18.id,
            hint="Every agent in a project has its own name. Choose another.",
        )
    before = seat.display_name
    if wanted == before:
        return seat
    seat.display_name = wanted
    append_event(
        session,
        type=SEAT_RENAMED,
        caller=caller,
        at=now,
        subject=("seat", seat.name),
        project_id=project_id,
        before={"display_name": before},
        after={"display_name": wanted},
    )
    return seat


async def create_ceo(
    session: AsyncSession, project: Project, now: datetime, caller: Caller
) -> None:
    """Every project gets its CEO seat and its channels when it is created (EXE-1, MSG-1)."""
    await ensure_starter_roles(session, now)
    role = await newest_role(session, CEO_ROLE)
    await _new_seat(session, project.id, role, "CEO", SeatKind.CEO, now, caller)
    for name, kind in (
        (conversation.PROJECT_CHAT, conversation.ChannelKind.PROJECT),
        (conversation.LEADERSHIP, conversation.ChannelKind.LEADERSHIP),
    ):
        await conversation.ensure_channel(session, project.id, name, kind, now)


async def set_ceo_role(session: AsyncSession, project: Project, role_name: str) -> None:
    """LIB-4: a spec may name the role its CEO takes. Only a role that can be the CEO."""
    role = await newest_role(session, role_name)
    if role.seat_kind != SeatKind.CEO:
        raise Refusal(
            "not_a_ceo_role", f"{role.name} is not a role that can be the CEO.", rule=EXE_1.id
        )
    (await ceo_of(session, project.id)).role_id = role.id


REVIEWER_ROLE = "reviewer"
REVIEWER_SEAT = "Reviewer"
STAFFING = platform_job("work: reviewer staffing")

RosterHook = Callable[[AsyncSession, Project, datetime], Awaitable[None]]
roster_hooks: list[RosterHook] = []
"""Steps run after the roster changes: a team hired, stood down or recalled. The
connections domain holds the new seats that cannot work yet (CON-5)."""


def _set_seat_state(session: AsyncSession, seat: Seat, target: SeatState, now: datetime) -> None:
    SEAT_MACHINE.check(seat.state, target)
    append_event(
        session,
        type=SEAT_STATE_CHANGED,
        caller=STAFFING,
        at=now,
        subject=("seat", seat.name),
        project_id=seat.project_id,
        before={"state": seat.state},
        after={"state": target},
    )
    seat.state = target


async def _platform_reviewers(session: AsyncSession, project_id: str) -> list[Seat]:
    """Reviewer seats the platform staffed: they belong to no team."""
    rows = await session.scalars(
        select(Seat)
        .where(
            Seat.project_id == project_id,
            Seat.kind == SeatKind.REVIEWER,
            Seat.team_id.is_(None),
        )
        .order_by(Seat.created_at, Seat.name)
    )
    return list(rows)


async def ensure_reviewer(session: AsyncSession, project: Project, now: datetime) -> bool:
    """WRK-9: a project with independent read on must staff a reviewer seat. When it has
    none, the platform brings back the one it stood down, or staffs a new one. Returns
    whether a seat was added or brought back."""
    have = await session.scalar(
        select(Seat.id)
        .where(
            Seat.project_id == project.id,
            Seat.kind == SeatKind.REVIEWER,
            Seat.state == SeatState.ACTIVE,
        )
        .limit(1)
    )
    if have is not None:
        return False
    for seat in await _platform_reviewers(session, project.id):
        if seat.state == SeatState.STOOD_DOWN:
            _set_seat_state(session, seat, SeatState.ACTIVE, now)
            return True
    taken = set(await session.scalars(select(Seat.name).where(Seat.project_id == project.id)))
    name, number = REVIEWER_SEAT, 1
    while name in taken:
        number += 1
        name = f"{REVIEWER_SEAT}-{number}"
    role = await newest_role(session, REVIEWER_ROLE)
    await _new_seat(session, project.id, role, name, SeatKind.REVIEWER, now, STAFFING)
    await session.flush()
    return True


async def stand_down_reviewer(session: AsyncSession, project: Project, now: datetime) -> None:
    """Section 3, WRK-9: a solo project that has turned independent read off is one agent.
    The reviewer seat the platform staffed is stood down; it comes back, with its history,
    when independent read is turned on again."""
    for seat in await _platform_reviewers(session, project.id):
        if seat.state == SeatState.ACTIVE:
            _set_seat_state(session, seat, SeatState.STOOD_DOWN, now)


async def create_first_seats(
    session: AsyncSession, project: Project, now: datetime, caller: Caller
) -> None:
    """A project starts with its CEO and, because independent read is on by default, a
    reviewer seat (EXE-1, WRK-9)."""
    await create_ceo(session, project, now, caller)
    await ensure_reviewer(session, project, now)


lifecycle.created_hooks.append(create_first_seats)


REQUIREMENTS_MET = "requirements met"
STAGE_CLEARED = re.compile(r"^stage ([1-9][0-9]?) cleared$")


def check_stand_down(condition: str | None) -> str | None:
    """PLN-12: a stand-down condition is one the platform can check, or nothing."""
    if condition is None:
        return None
    text = " ".join(condition.lower().split())
    if text == REQUIREMENTS_MET or STAGE_CLEARED.match(text):
        return text
    raise Refusal(
        "unknown_stand_down_condition",
        f'A stand-down condition is "{REQUIREMENTS_MET}" or "stage N cleared".',
        rule=EXE_1.id,
    )


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
    stand_down_when: str | None = None,
    names: list[str] | None = None,
    role_version: int | None = None,
) -> Team:
    """EXE-1: a team is seats created from one pinned role version, within `teams.max`.
    Its first member leads it. A CEO hire takes the same path as a chairman's."""
    role = await newest_role(session, role_name)
    if role_version is not None and role_version != role.version:
        role = await library.role_version(session, role.slug, role_version)
    if role.seat_kind == SeatKind.CEO:
        raise Refusal(
            "second_ceo",
            "A project has exactly one CEO; a team cannot be hired from a CEO role.",
            rule=EXE_1.id,
            hint="Choose another role.",
        )
    if names is not None:
        members = len(names)
        taken_seats = {name.casefold() for name in await names_in_use(session, project.id)}
        folded = [member.casefold() for member in names]
        clash = sorted(member for member in names if member.casefold() in taken_seats) or sorted(
            {member for member, key in zip(names, folded, strict=True) if folded.count(key) > 1}
        )
        if clash:
            raise Refusal(
                "seat_name_taken",
                f"An agent called {clash[0]} already exists or is named twice.",
                rule=EXE_1.id,
                hint="Every agent in a project has its own name.",
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
        project_id=project.id,
        name=name,
        role_id=role.id,
        state=TeamState.ACTIVE,
        stand_down_when=check_stand_down(stand_down_when),
        created_at=now,
    )
    session.add(team)
    await session.flush()
    for index in range(members):
        if names is not None:
            seat_name = names[index]
        else:
            seat_name = name if members == 1 else f"{name}-{index + 1}"
        await _new_seat(
            session,
            project.id,
            role,
            seat_name,
            role.seat_kind,
            now,
            caller,
            team_id=team.id,
            is_lead=index == 0,
            given_name=names is not None,
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
    for hook in roster_hooks:
        await hook(session, project, now)
    return team


TEAM_REPINNED = event_type("team.repinned", "A team moved to a newer version of its role.")


async def repin_team(
    session: AsyncSession, project: Project, name: str, caller: Caller, now: datetime
) -> Team:
    """LIB-1: move a team, and its seats, to the newest version of the role it was hired
    from."""
    team = await team_named(session, project.id, name)
    pinned = await session.get(Role, team.role_id)
    assert pinned is not None
    current = await library.role_named(session, pinned.slug)
    if current.id == pinned.id:
        raise Refusal(
            "already_current",
            f"Team {name} is already on version {pinned.version} of {pinned.name}, the newest.",
            rule=library.LIB_1.id,
        )
    team.role_id = current.id
    for seat in await session.scalars(select(Seat).where(Seat.team_id == team.id)):
        seat.role_id = current.id
    append_event(
        session,
        type=TEAM_REPINNED,
        caller=caller,
        at=now,
        subject=("team", name),
        project_id=project.id,
        before={"version": pinned.version},
        after={"version": current.version, "role": current.slug},
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
    from nightsquad.domain.execution import runs

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
    for hook in roster_hooks:
        await hook(session, project, now)
    return team
