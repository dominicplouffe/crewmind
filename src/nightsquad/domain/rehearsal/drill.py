"""The fire drill: a project spec run through the real rules, dispatcher and scheduler,
with a squad in code, on a database of its own (RHS-1, RHS-2).

It runs as its own process: `python -m nightsquad.domain.rehearsal.drill` reads a spec
as JSON on standard input and prints what happened as JSON. The process is given no
database address, no key and no credential, and it opens no socket."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import event, select

from nightsquad.catalog import catalog
from nightsquad.catalog.caller import Caller, CallerKind, InstanceRole
from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.connections import needs
from nightsquad.domain.decisions import agenda
from nightsquad.domain.install.config import Config
from nightsquad.domain.library.spec import ProjectSpec
from nightsquad.domain.planning.model import BetState, RequirementState
from nightsquad.domain.rehearsal.squad import DrillSquad, Roster
from nightsquad.jobs.dispatcher import Dispatcher
from nightsquad.jobs.planning import PlanningJobs
from nightsquad.jobs.scheduler import Scheduler
from nightsquad.jobs.work import WorkJobs
from nightsquad.runner.sandbox import InProcessSandbox
from nightsquad.runner.supervisor import Runner
from nightsquad.runtime import Runtime, build_runtime
from nightsquad.storage.models import (
    Bet,
    DecisionItem,
    Event,
    Person,
    Project,
    Requirement,
    Role,
    Run,
    RunRefusal,
    Seat,
)
from nightsquad.storage.models.base import Base
from nightsquad.surfaces.agent_api.app import add_agent_api
from nightsquad.surfaces.api.app import build_api

DATABASE_FILE = "rehearsal.sqlite"
"""RHS-1: a drill runs only on this file, inside a folder made for the drill and deleted
after it."""
START = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)
"""The drill's own calendar: a Monday morning. No real time is read."""
ROUNDS_MOST = 60
"""A drill ends after this many rounds of work, whatever the state: it is a rehearsal."""
TICK = timedelta(milliseconds=1)
"""The drill's clock moves this much each time it is read, so that, as on a real clock,
no two things happen at the same instant. It is not how long anything really takes."""
IDLE_STEP = timedelta(minutes=15)
IDLE_ROUNDS_MOST = 4
"""After this many jumps of the clock in a row with no run started, the drill has stalled."""
ENDED = frozenset({"ready", "completed", "stopped"})
REPORTED_SETTINGS = (
    "run.concurrency",
    "heartbeat.every",
    "review.independent",
    "authority.preset",
    "budget.tokens",
    "bet.window",
    "audit.sample_rate",
)
RUNNER_SLOTS = 1
"""The drill runs one agent at a time, in the order runs were queued, so the same spec
always gives the same report. The rules on parallel work are still checked at leasing."""


class DrillClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        self.now += TICK
        return self.now


class Drill:
    def __init__(self, spec: ProjectSpec, data_dir: Path) -> None:
        self.spec = spec
        self.clock = DrillClock()
        database = f"sqlite+aiosqlite:///{data_dir / DATABASE_FILE}"
        if (data_dir / DATABASE_FILE).exists():
            raise RuntimeError("a rehearsal runs only on a database it has just made (RHS-1)")
        config = Config(
            database_url=database,
            data_dir=data_dir,
            master_key_file=data_dir / "no-key",
            host="127.0.0.1",
            port=1,
            public_url=None,
            sandbox_mode="unisolated",
            memory_engine="in-process",
        )
        self.squad = DrillSquad(Roster("deliver", [], {}, set(), True))
        self.runtime: Runtime = build_runtime(
            config, self.clock, mock_default=True, mock=self.squad
        )
        event.listen(self.runtime.engine.sync_engine, "connect", _no_sync)
        self.waits: list[dict[str, Any]] = []
        self.jumps: list[dict[str, Any]] = []
        self.refusal: dict[str, Any] | None = None
        self.missing: list[str] = []
        self.project_id = ""
        self.rounds = 0
        self.compressed = timedelta(0)
        self.stalled = False
        self.reached = False
        self.run_time = timedelta(0)

    async def _needs(self) -> list[str]:
        """What the squad will need from outside, assumed in place for the drill (CON-5)."""
        async with self.runtime.sessions() as session:
            project = await session.get(Project, self.project_id)
            assert project is not None
            wanted = await needs.declared(session, project)
        return [
            f"The squad will need the {needs.KIND_WORDS[needs.NeedKind(kind)]} {name}, for "
            f"{', '.join(sorted(roles))}. The rehearsal assumed it was in place."
            for (kind, name), roles in sorted(wanted.items())
        ]

    async def _as_chairman(self, operation_name: str, /, **values: Any) -> Any:
        operation = catalog.get(operation_name)
        return await self.runtime.executor.execute(
            operation, self.chairman, operation.input(**values)
        )

    async def run(self) -> None:
        runtime = self.runtime
        async with runtime.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with runtime.sessions() as session, session.begin():
            person = Person(
                email="chairman@rehearsal.invalid",
                name="The chairman",
                role=InstanceRole.ADMIN,
                state="active",
                password_hash=None,
                created_at=self.clock(),
            )
            session.add(person)
            await session.flush()
            self.chairman = Caller(CallerKind.PERSON, person.id, role=InstanceRole.ADMIN)
        needs.assume_met.set(True)
        try:
            created = await self._as_chairman("projects.import_spec", **self.spec.model_dump())
            self.project_id, self.missing = created.project_id, list(created.missing)
            self.missing += await self._needs()
            await self._set_roster()
            await self._as_chairman("projects.start", project_id=self.project_id)
        except Refusal as refusal:
            self.refusal = refusal.envelope.model_dump(mode="json")
            return
        await self._work()

    async def _set_roster(self) -> None:
        async with self.runtime.sessions() as session:
            rows = (
                await session.execute(
                    select(Seat, Role)
                    .join(Role, Role.id == Seat.role_id)
                    .where(Seat.project_id == self.project_id)
                )
            ).all()
            project = await session.get(Project, self.project_id)
            assert project is not None
            authority = await self.runtime.settings.get(
                session,
                await _subject(session, project),
                "authority.accept_scope",
            )
        teams = {team.name: team for team in self.spec.teams}
        seat_team = {member: team.name for team in self.spec.teams for member in team.members}
        kinds = {seat.name: seat.kind for seat, _ in rows}
        workers = [
            name
            for name, team in teams.items()
            if any(kinds.get(member) in ("worker", "lead") for member in team.members)
        ]
        self.squad.roster = Roster(
            type=self.spec.type,
            worker_teams=workers,
            seat_team=seat_team,
            reviewers={seat.name for seat, _ in rows if seat.kind == "reviewer"},
            ceo_accepts=authority == "ceo",
        )

    async def _work(self) -> None:
        runtime = self.runtime
        api = build_api(catalog, runtime.executor, runtime.authenticator, base_url="http://drill")
        add_agent_api(
            api, catalog, runtime.executor, runtime.run_authenticator, runtime.gateway,
            runtime.settings, runtime.masker,
        )  # fmt: skip
        runner = Runner(
            runtime.sessions,
            runtime.settings,
            self.clock,
            InProcessSandbox(httpx.ASGITransport(app=api)),
            api_url="http://drill",
            workspaces=runtime.config.data_dir / "workspaces",
            blobs=runtime.services.blobs,
            workers=RUNNER_SLOTS,
            heartbeat_seconds=0.05,
            masks=runtime.masker,
        )
        dispatcher = Dispatcher(runtime.sessions, runtime.settings, self.clock)
        jobs = (
            Scheduler(runtime.sessions, self.clock, runtime.settings),
            WorkJobs(runtime.sessions, self.clock, runtime.services),
            PlanningJobs(runtime.sessions, self.clock, runtime.services),
        )
        idle = 0
        for self.rounds in range(1, ROUNDS_MOST + 1):
            await dispatcher.tick()
            started = await runner.step()
            await runner.idle()
            for job in jobs:
                await job.tick()
            answered = await self._answer_the_chairmans_items()
            if await self._reached_its_first_close():
                self.reached = True
                return
            if await self._state() in ENDED:
                return
            if started or answered:
                idle = 0
                continue
            idle += 1
            if idle > IDLE_ROUNDS_MOST:
                self.stalled = True
                return
            await self._let_time_pass()

    async def _state(self) -> str:
        async with self.runtime.sessions() as session:
            project = await session.get(Project, self.project_id)
            assert project is not None
            return project.state

    async def _reached_its_first_close(self) -> bool:
        """Where the walk ends: a Deliver project is ready, an Explore bet has its
        finding, an Operate requirement is met in its cycle."""
        async with self.runtime.sessions() as session:
            if self.spec.type == "explore":
                ended = await session.scalar(
                    select(Bet.id).where(
                        Bet.project_id == self.project_id, Bet.state != BetState.ACTIVE
                    )
                )
                return ended is not None
            if self.spec.type == "operate":
                met = await session.scalar(
                    select(Requirement.id).where(
                        Requirement.project_id == self.project_id,
                        Requirement.state == RequirementState.MET,
                    )
                )
                return met is not None
        return await self._state() in ENDED

    async def _answer_the_chairmans_items(self) -> int:
        """Each time the drill waits for the chairman it is counted, and answered with
        the first action the item offers, so the walk goes on (RHS-3)."""
        async with self.runtime.sessions() as session:
            items = list(
                await session.scalars(
                    select(DecisionItem).where(
                        DecisionItem.project_id == self.project_id, DecisionItem.state == "open"
                    )
                )
            )
        answered = 0
        for item in items:
            shown = await self._as_chairman(
                "items.show", project_id=self.project_id, item_id=item.id
            )
            if not shown.actions or not shown.waits_on_you:
                continue
            self.waits.append({"kind": item.kind, "title": shown.title, "at": _at(self.clock())})
            try:
                await self._as_chairman(
                    "items.decide",
                    project_id=self.project_id,
                    item_id=item.id,
                    action=shown.actions[0],
                    note="Answered by the rehearsal.",
                )
                answered += 1
            except Refusal:
                continue
        return answered

    async def _let_time_pass(self) -> None:
        """RHS-2: nothing is due, so the clock moves to the next thing the clock brings."""
        async with self.runtime.sessions() as session:
            project = await session.get(Project, self.project_id)
            assert project is not None
            due = await agenda.next_time_wake(session, self.runtime.settings, project, self.clock())
        step = max(due - self.clock(), IDLE_STEP) if due else IDLE_STEP
        if due:
            self.jumps.append({"seconds": int(step.total_seconds()), "at": _at(self.clock())})
        self.clock.now += step
        self.compressed += step

    async def result(self) -> dict[str, Any]:
        """What happened, as plain data. The server turns it into the report (RHS-3)."""
        found: dict[str, Any] = {
            "refusal": self.refusal,
            "reached": self.reached,
            "stalled": self.stalled,
            "missing": self.missing,
            "waits": self.waits,
            "jumps": self.jumps,
            "rounds": self.rounds,
            "started_at": _at(START),
            "ended_at": _at(self.clock()),
            "idle_seconds": int(self.compressed.total_seconds()),
            "model_calls": self.squad.calls,
            "state": None,
            "events": [],
            "seats": [],
            "refusals": [],
            "settings": {},
            "chain_runs": None,
        }
        if not self.project_id:
            return found
        async with self.runtime.sessions() as session:
            project = await session.get(Project, self.project_id)
            assert project is not None
            found["state"] = project.state
            rows = await session.scalars(
                select(Event).where(Event.project_id == self.project_id).order_by(Event.id)
            )
            found["events"] = [
                {
                    "type": row.type,
                    "at": _at(row.at),
                    "subject": row.subject_id,
                    "after": row.after,
                    "detail": row.detail,
                }
                for row in rows
            ]
            seats = (
                await session.execute(
                    select(Seat, Role)
                    .join(Role, Role.id == Seat.role_id)
                    .where(Seat.project_id == self.project_id)
                    .order_by(Seat.created_at, Seat.name)
                )
            ).all()
            runs = list(await session.scalars(select(Run).where(Run.project_id == project.id)))
            found["seats"] = [
                {
                    "name": seat.name,
                    "kind": seat.kind,
                    "role": role.slug,
                    "team": self.squad.roster.seat_team.get(seat.name),
                    "runs": len([run for run in runs if run.seat_id == seat.id]),
                }
                for seat, role in seats
            ]
            refused = await session.scalars(
                select(RunRefusal)
                .join(Run, Run.id == RunRefusal.run_id)
                .where(Run.project_id == project.id)
                .order_by(RunRefusal.id)
            )
            found["refusals"] = [
                {
                    "rule": row.rule,
                    "code": row.code,
                    "operation": row.operation,
                    "message": row.message,
                }
                for row in refused
            ]
            values = await self.runtime.settings.effective(
                session, await _subject(session, project)
            )
            found["settings"] = {name: values[name] for name in REPORTED_SETTINGS if name in values}
        try:
            plan = await self._as_chairman("plan.show", project_id=self.project_id)
            found["chain_runs"] = plan.longest_chain.runs
        except Refusal:
            pass
        return found


def _no_sync(connection: Any, _: Any) -> None:
    """The drill's database is thrown away with the drill, so it need not survive a
    power cut: writes are not flushed to disk one by one."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA synchronous=OFF")
    cursor.close()


async def _subject(session: Any, project: Project) -> Any:
    from nightsquad.domain.settings.service import project_subject

    return await project_subject(session, project)


def _at(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


async def rehearse(document: dict[str, Any]) -> dict[str, Any]:
    spec = ProjectSpec.model_validate(document)
    with tempfile.TemporaryDirectory(prefix="nightsquad-rehearsal-") as folder:
        drill = Drill(spec, Path(folder))
        try:
            await drill.run()
            return await drill.result()
        finally:
            await drill.runtime.close()


if __name__ == "__main__":
    json.dump(asyncio.run(rehearse(json.load(sys.stdin))), sys.stdout)
