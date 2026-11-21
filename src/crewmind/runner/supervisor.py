"""The runner: leases runs, starts sandboxes, sends heartbeats (section 10, EXE-5, EXE-7).

Without a runner nothing executes; the server never runs an agent itself. Scaling means
adding runners against the same database.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.execute import Clock
from crewmind.domain.artifacts import service as artifacts
from crewmind.domain.execution import runs
from crewmind.domain.execution.model import HEARTBEAT_EVERY
from crewmind.domain.execution.runs import Lease
from crewmind.domain.settings.service import SettingsService
from crewmind.runner.sandbox import Sandbox, SandboxSpec
from crewmind.storage.models import Artifact, Project, Seat

logger = logging.getLogger(__name__)

POLL_SECONDS = 5  # section 10: the runner supervisor runs every 5 s


class Runner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: SettingsService,
        clock: Clock,
        sandbox: Sandbox,
        *,
        api_url: str,
        workspaces: Path,
        blobs: artifacts.BlobStore,
        workers: int,
        heartbeat_seconds: float = HEARTBEAT_EVERY.total_seconds(),
    ) -> None:
        self.id = f"runner-{uuid.uuid4().hex[:8]}"
        self._sessions = sessions
        self._settings = settings
        self._clock = clock
        self._sandbox = sandbox
        self._api_url = api_url
        self._workspaces = workspaces
        self._blobs = blobs
        self._workers = workers
        self._heartbeat_seconds = heartbeat_seconds
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def busy(self) -> int:
        return len(self._tasks)

    async def step(self) -> int:
        """Lease as many runs as there are free workers and start them (EXE-5). Returns how
        many were started."""
        free = self._workers - self.busy
        async with self._sessions() as session, session.begin():
            leases = await runs.lease(session, self._settings, self.id, free, self._clock())
        for lease in leases:
            task = asyncio.create_task(self._execute(lease))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return len(leases)

    async def idle(self) -> None:
        """Wait until every run this runner started has ended."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _execute(self, lease: Lease) -> None:
        spec = SandboxSpec(
            run_id=lease.run_id,
            project_id=lease.project_id,
            token=lease.token,
            api_url=self._api_url,
            workspace=self._workspaces / lease.project_id,
        )
        spec.workspace.mkdir(parents=True, exist_ok=True)
        await self._before(lease, spec.workspace)
        try:
            handle = await self._sandbox.start(spec)
        except Exception as error:
            logger.exception("runner: sandbox for run %s did not start", lease.run_id)
            await self._started(lease)
            await self._finish(lease, failed=True, detail=f"the sandbox did not start: {error}")
            return
        if not await self._started(lease):
            await handle.kill()
            return
        waiter = asyncio.create_task(handle.wait())
        try:
            while True:
                done, _ = await asyncio.wait({waiter}, timeout=self._heartbeat_seconds)
                if done:
                    break
                async with self._sessions() as session, session.begin():
                    alive = await runs.heartbeat(session, lease.run_id, self.id, self._clock())
                if not alive:
                    await handle.kill()
                    return
            code = waiter.result()
        except asyncio.CancelledError:
            waiter.cancel()
            with contextlib.suppress(Exception):
                await handle.kill()
            raise
        await self._after(lease, spec.workspace)
        await self._finish(lease, failed=code != 0, detail=None if code == 0 else f"exit {code}")

    async def _before(self, lease: Lease, workspace: Path) -> None:
        """Make the chairman's locked files read-only where the sandbox sees them (ART-5)."""
        async with self._sessions() as session:
            locked = await session.scalars(
                select(Artifact.name).where(
                    Artifact.project_id == lease.project_id, Artifact.locked.is_(True)
                )
            )
            artifacts.lock_in_workspace(workspace, list(locked))

    async def _after(self, lease: Lease, workspace: Path) -> None:
        """Snapshot the workspace: every changed file becomes a working artifact (ART-2)."""
        try:
            async with self._sessions() as session, session.begin():
                project = await session.get(Project, lease.project_id)
                seat = await session.get(Seat, lease.seat_id)
                assert project is not None
                assert seat is not None
                await artifacts.snapshot_workspace(
                    session,
                    self._settings,
                    self._blobs,
                    project,
                    workspace,
                    artifacts.Author("agent", seat.id, seat.name, lease.run_id),
                    self._clock(),
                )
        except Exception:
            logger.exception("runner: workspace snapshot for run %s failed", lease.run_id)

    async def _started(self, lease: Lease) -> bool:
        async with self._sessions() as session, session.begin():
            return await runs.started(session, lease.run_id, self.id, self._clock())

    async def _finish(self, lease: Lease, *, failed: bool, detail: str | None) -> None:
        async with self._sessions() as session, session.begin():
            await runs.finish(
                session, lease.run_id, self.id, self._clock(), failed=failed, detail=detail
            )

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except Exception:
                logger.exception("runner: step failed")
            await asyncio.sleep(POLL_SECONDS)

    async def crash(self) -> None:
        """Stop without finishing anything, as a killed runner would. For chaos tests."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
        self._tasks.clear()
