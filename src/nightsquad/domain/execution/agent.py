"""An agent's identity during a run: resolving a run token to a caller (P3, INV-4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightsquad.catalog.caller import Caller, CallerKind
from nightsquad.catalog.execute import unauthenticated
from nightsquad.domain.execution import runs
from nightsquad.storage.models import Project, Role, Run, Seat


class RunAuthenticator:
    """Turns a run token into an agent caller. The token works only for its own run, agent
    and project, and only while the run is live and not revoked (INV-4)."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def authenticate(self, token: str | None) -> Caller:
        async with self._sessions() as session:
            run = await runs.run_for_token(session, token)
            if run is None:
                raise unauthenticated()
            seat = await session.get(Seat, run.seat_id)
            assert seat is not None
            return Caller(
                CallerKind.AGENT,
                seat.id,
                via=f"run:{run.id}",
                run_id=run.id,
                project_id=run.project_id,
                seat_kind=seat.kind,
            )


@dataclass(frozen=True)
class AgentView:
    project: Project
    seat: Seat
    role: Role
    run: Run


async def agent_of(context: Any) -> AgentView:
    """The project, seat, role and run behind an agent call."""
    caller: Caller = context.caller
    session: AsyncSession = context.session
    assert caller.project_id is not None
    assert caller.run_id is not None
    project = await session.get(Project, caller.project_id)
    seat = await session.get(Seat, caller.actor_id)
    run = await session.get(Run, caller.run_id)
    assert project is not None
    assert seat is not None
    assert run is not None
    role = await session.get(Role, seat.role_id)
    assert role is not None
    return AgentView(project, seat, role, run)
