"""The scheduler: periodic platform jobs (section 10, BG-1, BG-3, BG-4).

Each project is processed in its own transaction, so one broken project cannot stall the
others (BG-1). Every job is safe to run twice (BG-3). Every change a job makes names the
job as its actor (BG-4).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.caller import platform_job
from crewmind.catalog.execute import Clock
from crewmind.domain.accounts.credentials import session_is_live
from crewmind.domain.accounts.model import (
    LINK_MACHINE,
    SESSION_MACHINE,
    TOKEN_MACHINE,
    LinkState,
    SessionState,
    TokenState,
)
from crewmind.domain.accounts.people import LINK_EXPIRED
from crewmind.domain.accounts.token_operations import TOKEN_EXPIRED
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import corrections, sessions, speaking
from crewmind.domain.execution import runs
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.model import Hold, ProjectState
from crewmind.domain.settings.registry import load_registry
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import BrowserSession, Link, Project, Token

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=15)  # section 10: the scheduler runs every 15 s per project

SESSION_EXPIRED = event_type("session.expired", "A session ended by age or idleness (ACC-2).")

ProjectJob = Callable[[AsyncSession, Project, datetime], Awaitable[None]]
InstallJob = Callable[[AsyncSession, datetime], Awaitable[None]]

RESUME_TIMES = platform_job("scheduler: resume times")
PURGE = platform_job("scheduler: purge deleted projects")
EXPIRY = platform_job("scheduler: expire credentials")


async def lift_due_holds(session: AsyncSession, project: Project, now: datetime) -> None:
    """Section 7.1: the chairman's hold lifts when its lift time arrives."""
    due = [
        row
        for row in await lifecycle.active_holds(session, project.id)
        if row.reason == Hold.CHAIRMAN and row.lift_at is not None and row.lift_at <= now
    ]
    if due:
        await lifecycle.lift_holds(
            session,
            project,
            frozenset({Hold.CHAIRMAN}),
            caller=RESUME_TIMES,
            now=now,
            cause="the resume time arrived",
        )


async def purge_deleted(session: AsyncSession, project: Project, now: datetime) -> None:
    """PRJ-10: a deleting project is purged once `delete.grace` has passed."""
    if (
        project.state == ProjectState.DELETING
        and project.delete_at is not None
        and project.delete_at <= now
    ):
        await lifecycle.purge(session, project, caller=PURGE, now=now)


async def expire_credentials(session: AsyncSession, now: datetime) -> None:
    """Sections 7.9 and 7.10: links, tokens and sessions past their time change state."""
    links = await session.scalars(
        select(Link).where(Link.state == LinkState.UNUSED, Link.expires_at <= now)
    )
    for link in links:
        LINK_MACHINE.check(link.state, LinkState.EXPIRED)
        link.state = LinkState.EXPIRED
        _expired(session, LINK_EXPIRED, "link", link.id, LinkState.UNUSED, LinkState.EXPIRED, now)
    tokens = await session.scalars(
        select(Token).where(Token.state == TokenState.ACTIVE, Token.expires_at <= now)
    )
    for token in tokens:
        TOKEN_MACHINE.check(token.state, TokenState.EXPIRED)
        token.state = TokenState.EXPIRED
        _expired(
            session, TOKEN_EXPIRED, "token", token.id, TokenState.ACTIVE, TokenState.EXPIRED, now
        )
    sessions = await session.scalars(
        select(BrowserSession).where(BrowserSession.state == SessionState.ACTIVE)
    )
    for row in sessions:
        if not session_is_live(row, now):
            SESSION_MACHINE.check(row.state, SessionState.ENDED)
            row.state = SessionState.ENDED
            row.ended_at = now
            _expired(
                session,
                SESSION_EXPIRED,
                "session",
                row.id,
                SessionState.ACTIVE,
                SessionState.ENDED,
                now,
            )


def _expired(
    session: AsyncSession, type: str, kind: str, id: str, before: str, after: str, now: datetime
) -> None:
    append_event(
        session,
        type=type,
        caller=EXPIRY,
        at=now,
        subject=(kind, id),
        before={"state": before},
        after={"state": after},
    )


class Scheduler:
    """Runs the project jobs, in order, for every project, then the install jobs."""

    project_jobs: tuple[ProjectJob, ...] = (
        lift_due_holds,
        purge_deleted,
        corrections.expire,
        speaking.deliver_due,
    )
    install_jobs: tuple[InstallJob, ...] = (expire_credentials,)

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        clock: Clock,
        settings: SettingsService | None = None,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._settings = settings or SettingsService(load_registry())

    async def tick(self) -> list[str]:
        """One pass. Returns the ids of projects whose jobs failed; the rest are done."""
        now = self._clock()
        failed: list[str] = []
        async with self._sessions() as session:
            project_ids = list(await session.scalars(select(Project.id).order_by(Project.id)))
        for project_id in project_ids:
            try:
                async with self._sessions() as session, session.begin():
                    project = await session.get(Project, project_id)
                    if project is None:
                        continue
                    for job in self.project_jobs:
                        await job(session, project, now)
                        if project.state == ProjectState.DELETED:
                            break
                    else:
                        await budget.follow_wall(session, self._settings, project, now)
            except Exception:
                logger.exception("scheduler: project %s failed this tick", project_id)
                failed.append(project_id)
        try:
            async with self._sessions() as session, session.begin():
                await runs.reap(session, self._settings, now)
                await sessions.close_idle(session, self._settings, now)
        except Exception:
            logger.exception("scheduler: reaping failed this tick")
        for job in self.install_jobs:
            try:
                async with self._sessions() as session, session.begin():
                    await job(session, now)
            except Exception:
                logger.exception("scheduler: %s failed this tick", job.__name__)
        return failed

    async def run(self) -> None:
        """Tick for ever. A failed pass is logged and the next one still runs (NFR-9)."""
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("scheduler: tick failed")
            await asyncio.sleep(TICK.total_seconds())
