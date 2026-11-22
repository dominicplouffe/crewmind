"""Helpers for the work tests: a small crew and its workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from tests.support import Actor, App, agent_call, live_run, quiet_start, running_project

OBSERVABLE = {
    "title": "Write the summary",
    "goal": "Summarise the three interviews in one page.",
    "success_test": "A one-page summary exists and names all three interviewees.",
    "test_kind": "observable",
}


class Crew:
    """A running project with a CEO, a reviewer and one team: a lead and a member."""

    def __init__(self, app: App, owner: Actor, project: str) -> None:
        self.app, self.owner, self.project = app, owner, project
        self.workspace: Path = app.runtime.config.data_dir / "workspaces" / project
        self.requirement: int = 0
        self.bet: int = 0
        self.run_hours: int = 0
        """When set, every finished run is made this long, so projections are exact."""

    @classmethod
    async def start(
        cls,
        app: App,
        *,
        team: bool = True,
        type: str = "deliver",
        settings: dict[str, Any] | None = None,
        owner: Actor | None = None,
    ) -> Crew:
        owner = owner or await app.person("owner@example.com")
        # These tests wake the same agent many times in one clock hour.
        settings = {"agent.max_wakes_per_hour": 60, **(settings or {})}
        if type == "deliver":
            project = await running_project(app, owner, **settings)
        else:
            project = await app.project(owner, type=type)
            if settings:
                await app.ok(
                    "settings.change_project", owner, project_id=project, changes=settings,
                    reason="Set up for the test.",
                )  # fmt: skip
            await app.ok("projects.start", owner, project_id=project)
            await quiet_start(app, project)
        crew = cls(app, owner, project)
        crew.workspace.mkdir(parents=True, exist_ok=True)
        if type != "explore":
            crew.requirement = await crew.add_requirement()
        else:
            crew.bet = await crew.open_bet()
        if team:
            hired = await crew.call(
                "CEO", "agent.hire_team", team="build", role="Generalist", members=2
            )
            assert hired.status_code == 200, hired.text
        return crew

    async def call(self, seat: str, name: str, /, **values: Any) -> httpx.Response:
        """Call an agent operation as `seat`, in a work run of its own. A new top-level
        task serves the crew's requirement unless the test names another."""
        if name == "agent.create_task":
            values = {**self.scope(), **values}
        run = await live_run(self.app, self.project, seat=seat)
        await self._stretch_runs()
        return await agent_call(self.app, run.token, name, **values)

    async def _stretch_runs(self) -> None:
        if not self.run_hours:
            return
        from datetime import timedelta

        from sqlalchemy import select

        from crewmind.storage.models import Run

        async with self.app.runtime.sessions() as session, session.begin():
            rows = await session.scalars(
                select(Run).where(Run.project_id == self.project, Run.ended_at.is_not(None))
            )
            for row in rows:
                assert row.ended_at is not None
                row.started_at = row.ended_at - timedelta(hours=self.run_hours)

    async def ok(self, seat: str, name: str, /, **values: Any) -> dict[str, Any]:
        answer = await self.call(seat, name, **values)
        assert answer.status_code == 200, answer.text
        return answer.json()

    async def add_requirement(self, **fields: Any) -> int:
        """Scope the chairman adds: accepted at once and estimated, so work can serve it."""
        plan = await self.app.ok(
            "requirements.add",
            self.owner,
            project_id=self.project,
            **{
                "text": "The interviews are summarised for the team.",
                "test_kind": "observable",
                "success_test": "A reader finds every interview summarised.",
                "estimate_runs": 40,
                **fields,
            },
        )
        return plan["requirements"][-1]["id"]

    async def open_bet(self, **fields: Any) -> int:
        """A bet the CEO opens, so Explore work has something to serve."""
        plan = await self.ok(
            "CEO",
            "agent.open_bet",
            **{
                "statement": "Small firms will pay for the interview summaries.",
                "kill_condition": "Fewer than three of ten firms say they would pay.",
                **fields,
            },
        )
        return plan["bets"][-1]["id"]

    def scope(self) -> dict[str, Any]:
        """What a new top-level task names as the scope it serves."""
        if self.bet:
            return {"bet_id": self.bet}
        return {} if not self.requirement else {"requirement_id": self.requirement}

    async def task(self, **fields: Any) -> dict[str, Any]:
        """A top-level task for the team, created by the CEO."""
        return await self.ok(
            "CEO",
            "agent.create_task",
            **{**OBSERVABLE, "team": "build", **self.scope(), **fields},
        )

    async def finish(self, seat: str) -> None:
        """End the run this agent was last given, as its sandbox would."""
        from crewmind.domain.execution import runs

        handed: dict[tuple[str, str], Any] = self.app.__dict__.get("_handed_runs", {})
        run = handed.pop((self.project, seat), None)
        if run is not None:
            async with self.app.runtime.sessions() as session, session.begin():
                await runs.finish(
                    session, run.run_id, run.runner_id, self.app.runtime.clock(), failed=False
                )

    async def finish_all(self) -> None:
        """End every run this project's agents were given or are waiting to be given."""
        from crewmind.domain.execution import runs

        handed: dict[tuple[str, str], Any] = self.app.__dict__.get("_handed_runs", {})
        stash: dict[tuple[str, str], list[Any]] = self.app.__dict__.get("_live_runs", {})
        waiting = [handed.pop(key) for key in list(handed) if key[0] == self.project]
        for key in [key for key in stash if key[0] == self.project]:
            waiting += stash.pop(key)
        for run in waiting:
            async with self.app.runtime.sessions() as session, session.begin():
                await runs.finish(
                    session, run.run_id, run.runner_id, self.app.runtime.clock(), failed=False
                )
        await self._stretch_runs()

    async def fail(self, seat: str) -> None:
        """End the run this agent was last given as failed, so it is retried (EXE-8)."""
        from crewmind.domain.execution import runs

        handed: dict[tuple[str, str], Any] = self.app.__dict__.get("_handed_runs", {})
        run = handed.pop((self.project, seat))
        async with self.app.runtime.sessions() as session, session.begin():
            await runs.finish(
                session, run.run_id, run.runner_id, self.app.runtime.clock(), failed=True
            )

    def write(self, name: str, content: str) -> None:
        file = self.workspace / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    async def show(self, task_id: int) -> dict[str, Any]:
        return await self.app.ok("tasks.show", self.owner, project_id=self.project, task_id=task_id)
