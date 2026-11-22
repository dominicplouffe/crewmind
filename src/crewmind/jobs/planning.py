"""The planning jobs: requirement acceptance and team stand-down conditions (PLN-10,
PLN-12, BG-3).

A command test is read in one transaction, run with no transaction open, and its result
written in another. A test changes nothing, so running it twice after a crash is safe.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.execute import Clock
from crewmind.domain.planning import acceptance, standdown
from crewmind.domain.planning.model import RequirementState, RequirementTest
from crewmind.domain.planning.readiness import PLANNING_JOB
from crewmind.domain.projects.model import ProjectState
from crewmind.domain.work import checks
from crewmind.runner.check_sandbox import CHECK_SECONDS_LIMIT
from crewmind.services import Services
from crewmind.storage.models import Project, Requirement

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=15)  # section 10: periodic jobs run every 15 s


class PlanningJobs:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], clock: Clock, services: Services
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._services = services

    async def tick(self) -> None:
        await self.per_project()
        await self.run_requirement_tests()

    async def per_project(self) -> None:
        """Per running project, in its own transaction (BG-1). A held, paused, stopped,
        ready or completed project changes no state (INV-20)."""
        async with self._sessions() as session:
            project_ids = list(
                await session.scalars(
                    select(Project.id)
                    .where(Project.state == ProjectState.RUNNING)
                    .order_by(Project.id)
                )
            )
        for project_id in project_ids:
            try:
                async with self._sessions() as session, session.begin():
                    project = await session.get(Project, project_id)
                    if project is None or project.state != ProjectState.RUNNING:
                        continue
                    now = self._clock()
                    settings = self._services.settings
                    await acceptance.start_checking(session, settings, project, now)
                    await standdown.stand_down_finished_teams(session, project, now)
            except Exception:
                logger.exception("planning jobs: project %s failed this tick", project_id)

    async def run_requirement_tests(self) -> int:
        """PLN-10: run the command test of every requirement in checking. Exit 0 means
        met; anything else sends it back to in progress. Returns how many were run."""
        async with self._sessions() as session:
            due = list(
                await session.scalars(
                    select(Requirement)
                    .where(
                        Requirement.state == RequirementState.CHECKING,
                        Requirement.test_kind == RequirementTest.COMMAND,
                    )
                    .order_by(Requirement.id)
                )
            )
        for requirement in due:
            workspace = self._services.data_dir / "workspaces" / requirement.project_id
            try:
                pinned = checks.restored(requirement.test_files, self._services.blobs)
                result = await self._services.checks.run(
                    workspace, requirement.success_test, pinned, CHECK_SECONDS_LIMIT
                )
            except Exception as error:
                logger.exception("the test of requirement %s could not run", requirement.id)
                result = checks.CheckResult(False, f"The test could not run: {error}")
            async with self._sessions() as session, session.begin():
                row = await session.get(Requirement, requirement.id)
                if row is None or row.state != RequirementState.CHECKING:
                    continue
                project = await session.get(Project, row.project_id)
                assert project is not None
                await acceptance.settle(
                    session,
                    project,
                    row,
                    result.passed,
                    result.output,
                    self._clock(),
                    by=PLANNING_JOB,
                )
        return len(due)

    async def run(self) -> None:
        """Tick for ever. A failed pass is logged and the next one still runs (NFR-9)."""
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("planning jobs: tick failed")
            await asyncio.sleep(TICK.total_seconds())
