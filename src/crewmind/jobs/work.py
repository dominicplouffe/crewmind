"""The work jobs: run the checks that are due, and return claims that have no live run
(WRK-4, WRK-7, WRK-8, INV-2, INV-16, BG-3).

A check is read in one transaction, run with no transaction open, and its result written
in another. A crash in between leaves the task in checking, and the next pass runs the
check again: a check changes nothing, so running it twice is safe.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.execute import Clock
from crewmind.domain.execution import roster
from crewmind.domain.work import board, checks, fetch, outside, reviews, tasks
from crewmind.domain.work import operations as work_operations
from crewmind.domain.work.model import Label, TaskState, WatchState
from crewmind.runner.check_sandbox import CHECK_SECONDS_LIMIT
from crewmind.services import Services
from crewmind.storage.models import Evidence, Project, Task, Watch

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=15)  # section 10: periodic jobs run every 15 s


class WorkJobs:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], clock: Clock, services: Services
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._services = services

    async def tick(self) -> None:
        await self.run_checks()
        await self.verify_evidence()
        await self.run_watches()
        await self.keep_work_moving()

    async def verify_evidence(self) -> int:
        """WRK-12: fetch each pending piece of evidence through the guard and verify it. A
        failed check fails it at once; a failed fetch is retried up to 5 times, then fails
        closed. Returns how many were settled."""
        async with self._sessions() as session:
            pending = list(
                await session.scalars(
                    select(Evidence).where(Evidence.state == "pending").order_by(Evidence.id)
                )
            )
            controlled = {
                row.project_id: await outside.controlled_hosts(session, row.project_id)
                for row in pending
            }
        settled = 0
        for row in pending:
            page: bytes | None = None
            failure: str | None = None
            fetch_failed = False
            host = urlsplit(row.url).hostname or ""
            try:
                fetch.check_url(row.url)
                if host in controlled[row.project_id]:
                    failure = f"{host} is a domain this project controls, so it is not outside."
                else:
                    page = await fetch.fetch_public(row.url)
                    if not outside.found_on_page(row.claim, page):
                        failure = "The quoted words are not on the page."
            except fetch.FetchRefused as refused:
                failure = f"The page was not fetched: {refused}."
                fetch_failed = "is not a public address" not in str(refused) and (
                    "only http" not in str(refused)
                )
            async with self._sessions() as session, session.begin():
                current = await session.get(Evidence, row.id)
                if current is None or current.state != "pending":
                    continue
                now = self._clock()
                current.attempts += 1
                if failure is None and page is not None:
                    self._services.blobs.put(page)
                    outside.settle_evidence(
                        session, current, now, tasks.WORK_JOB, snapshot_hash=outside.snapshot(page)
                    )
                elif fetch_failed and current.attempts < outside.FETCH_ATTEMPTS:
                    current.failure = failure
                    continue
                else:
                    outside.settle_evidence(session, current, now, tasks.WORK_JOB, failure=failure)
                settled += 1
        return settled

    async def run_watches(self) -> int:
        """WRK-17: run every watch that is due, at 0 tokens. A watch that starts failing is
        flagged and wakes the seat that launched it; one that recovers is passing again."""
        now = self._clock()
        async with self._sessions() as session:
            rows = list(
                await session.scalars(
                    select(Watch).where(Watch.state.in_(["passing", "failing"])).order_by(Watch.id)
                )
            )
            watches = [watch for watch in rows if outside.due(watch, now)]
        for watch in watches:
            passed, result = await self._watch(watch)
            async with self._sessions() as session, session.begin():
                current = await session.get(Watch, watch.id)
                if current is None or current.state not in ("passing", "failing"):
                    continue
                at = self._clock()
                current.last_run_at, current.last_result = at, result
                if passed and current.state == "failing":
                    outside.move_watch(session, current, WatchState.PASSING, tasks.WORK_JOB, at)
                elif not passed and current.state == "passing":
                    outside.move_watch(session, current, WatchState.FAILING, tasks.WORK_JOB, at)
                    project = await session.get(Project, current.project_id)
                    assert project is not None
                    await outside.watch_failed(session, current, result, at, project)
        return len(watches)

    async def _watch(self, watch: Watch) -> tuple[bool, str]:
        if watch.kind == "url":
            try:
                page = await fetch.fetch_public(watch.check)
            except fetch.FetchRefused as refused:
                return False, f"The page was not fetched: {refused}."
            found = outside.found_on_page(watch.expect or "", page)
            return found, "The page shows what it should." if found else (
                f"The page does not contain: {watch.expect}"
            )
        workspace = self._services.data_dir / "workspaces" / watch.project_id
        result = await self._services.checks.run(workspace, watch.check, {}, CHECK_SECONDS_LIMIT)
        return result.passed, result.output

    async def run_checks(self) -> int:
        """WRK-7, INV-2: run the pinned command of every task in checking. Exit 0 closes the
        task as verified; anything else is a failure (WRK-8). Returns how many were run."""
        async with self._sessions() as session:
            due = list(
                await session.scalars(
                    select(Task).where(Task.state == TaskState.CHECKING).order_by(Task.id)
                )
            )
            timeouts: dict[str, int] = {}
            for task in due:
                project = await session.get(Project, task.project_id)
                assert project is not None
                timeouts[task.project_id] = int(
                    await self._services.settings.get(
                        session, tasks.subject(project), "run.timeout"
                    )
                )
        for task in due:
            workspace = self._services.data_dir / "workspaces" / task.project_id
            try:
                pinned = checks.restored(task.test_files, self._services.blobs)
                result = await self._services.checks.run(
                    workspace, task.success_test, pinned, timeouts[task.project_id]
                )
            except Exception as error:
                logger.exception("the check of task %s could not run", task.id)
                result = checks.CheckResult(False, f"The check could not run: {error}")
            async with self._sessions() as session, session.begin():
                row = await session.get(Task, task.id)
                if row is None or row.state != TaskState.CHECKING:
                    continue
                now = self._clock()
                if result.passed:
                    await tasks.passed(
                        session, row, Label.VERIFIED, result.output, now, tasks.WORK_JOB
                    )
                else:
                    await tasks.failed(
                        session, row, result.output, now, tasks.WORK_JOB, what="the check"
                    )
        return len(due)

    async def keep_work_moving(self) -> None:
        """Per project, in its own transaction (BG-1): expire dead claims, and find another
        reviewer for a review whose reviewer is gone."""
        async with self._sessions() as session:
            project_ids = list(await session.scalars(select(Project.id).order_by(Project.id)))
        for project_id in project_ids:
            try:
                async with self._sessions() as session, session.begin():
                    project = await session.get(Project, project_id)
                    if project is None:
                        continue
                    now = self._clock()
                    await tasks.expire_claims(session, self._services.settings, project, now)
                    await reviews.close_orphans(session, project, now)
                    await work_operations.expire_audits(session, project, now)
                    await board.watch_for_stall(session, self._services.settings, project, now)
                    await board.watch_for_spinning(session, self._services.settings, project, now)
                    independent = await self._services.settings.get(
                        session, tasks.subject(project), "review.independent"
                    )
                    if independent and project.state not in ("deleting", "deleted", "stopped"):
                        await roster.ensure_reviewer(session, project, now)
            except Exception:
                logger.exception("work jobs: project %s failed this tick", project_id)

    async def run(self) -> None:
        """Tick for ever. A failed pass is logged and the next one still runs (NFR-9)."""
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("work jobs: tick failed")
            await asyncio.sleep(TICK.total_seconds())
