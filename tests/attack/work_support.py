"""Helpers for the work tests: a small crew and its workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from tests.support import Actor, App, agent_call, live_run, running_project

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

    @classmethod
    async def start(
        cls,
        app: App,
        *,
        team: bool = True,
        type: str = "deliver",
        settings: dict[str, Any] | None = None,
    ) -> Crew:
        owner = await app.person("owner@example.com")
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
        crew = cls(app, owner, project)
        crew.workspace.mkdir(parents=True, exist_ok=True)
        if team:
            hired = await crew.call(
                "CEO", "agent.hire_team", team="build", role="Generalist", members=2
            )
            assert hired.status_code == 200, hired.text
        return crew

    async def call(self, seat: str, name: str, /, **values: Any) -> httpx.Response:
        """Call an agent operation as `seat`, in a work run of its own."""
        run = await live_run(self.app, self.project, seat=seat)
        return await agent_call(self.app, run.token, name, **values)

    async def ok(self, seat: str, name: str, /, **values: Any) -> dict[str, Any]:
        answer = await self.call(seat, name, **values)
        assert answer.status_code == 200, answer.text
        return answer.json()

    async def task(self, **fields: Any) -> dict[str, Any]:
        """A top-level task for the team, created by the CEO."""
        return await self.ok(
            "CEO", "agent.create_task", **{**OBSERVABLE, "team": "build", **fields}
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
