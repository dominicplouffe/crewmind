"""Stand-down conditions (PLN-12): a team may carry a condition the platform can check.
When it becomes true and the team holds no work, the platform stands the team down."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.execution import roster
from nightsquad.domain.execution.model import TeamState
from nightsquad.domain.planning.model import OPEN_SCOPE, RequirementState
from nightsquad.domain.planning.readiness import PLANNING_JOB
from nightsquad.domain.work.model import OPEN_STATES
from nightsquad.storage.models import Project, Requirement, Task, Team


async def is_true(session: AsyncSession, project_id: str, condition: str) -> bool:
    wanted = (
        select(func.count()).select_from(Requirement).where(Requirement.project_id == project_id)
    )
    staged = roster.STAGE_CLEARED.match(condition)
    if staged:
        wanted = wanted.where(Requirement.stage <= int(staged.group(1)))
    open_scope = await session.scalar(wanted.where(Requirement.state.in_(OPEN_SCOPE)))
    met = await session.scalar(wanted.where(Requirement.state == RequirementState.MET))
    return not open_scope and bool(met)


async def stand_down_finished_teams(
    session: AsyncSession, project: Project, now: datetime
) -> list[str]:
    """Stand down each active team whose condition is true and which holds no work. The
    condition is spent once it fires, so a recalled team stays recalled."""
    teams = list(
        await session.scalars(
            select(Team).where(
                Team.project_id == project.id,
                Team.state == TeamState.ACTIVE,
                Team.stand_down_when.is_not(None),
            )
        )
    )
    stood_down: list[str] = []
    for team in teams:
        assert team.stand_down_when is not None
        if not await is_true(session, project.id, team.stand_down_when):
            continue
        holds = await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.team_id == team.id, Task.state.in_(OPEN_STATES))
        )
        if holds:
            continue
        try:
            await roster.set_team_state(
                session, project, team.name, TeamState.STOOD_DOWN, caller=PLANNING_JOB, now=now
            )
        except Refusal:
            continue
        team.stand_down_when = None
        stood_down.append(team.name)
    return stood_down
