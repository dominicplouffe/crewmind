"""Scripted crews for phase 4: a competent crew that finishes a verified job, and a
rule-breaker that must not get anywhere (section 13, NFR-19, P5, P10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from crewmind.storage.models import RunRefusal, Task
from tests.support import App, running_project

SCRIPTS = Path(__file__).parents[2] / "acceptance" / "scripts"


def load(app: App, name: str) -> None:
    """Give the mock provider one of the reference scripts."""
    crew: dict[str, Any] = json.loads((SCRIPTS / f"{name}.json").read_text())
    for key, turns in crew.items():
        if key != "about":
            app.script(key, *turns)


async def settle(app: App, rounds: int = 6) -> None:
    """Let the crew run until nothing is due."""
    for _ in range(rounds):
        if await app.work() == 0:
            return


async def test_scenario_a_competent_crew_finishes_a_verified_job(app: App) -> None:
    """Golden path (WRK-1 to WRK-8, INV-2, P5): the CEO hires a team and creates a task with
    a command test; the lead claims it, does the work and completes it; the platform runs
    the pinned check and closes it as verified. Nobody is refused anything on the way."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    workspace = app.runtime.config.data_dir / "workspaces" / project
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "check.sh").write_text("grep -q 41 report.txt\n")
    load(app, "competent-crew")
    await app.ok("chat.command", owner, project_id=project, text="/do Plan the quarterly report.")
    assert await app.work() >= 1
    app.script("CEO/work", {"text": "Nothing more to plan."})
    await settle(app)

    (task,) = (await app.ok("tasks.list", owner, project_id=project))["items"]
    assert (task["state"], task["label"], task["claimant"]) == (
        "checking",
        "not yet checked",
        "build",
    )
    assert await app.work_jobs.run_checks() == 1
    done = await app.ok("tasks.show", owner, project_id=project, task_id=task["id"])
    assert (done["state"], done["label"], done["failures"]) == ("done", "verified", 0)
    assert done["attempts"][0]["result"] == "passed"
    assert (workspace / "report.txt").read_text() == "Third quarter: 41 orders.\n"
    async with app.runtime.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RunRefusal)) == 0
    assert (await app.ok("budget.show", owner, project_id=project))["spent"] > 0


async def test_scenario_the_rule_breaker_gets_nowhere(app: App) -> None:
    """Section 13 "rule-breaker" (INV-1 to INV-7, INV-23, EXE-10, P10): a scripted agent
    tries to complete a task it does not hold, review it, kill it, overwrite a locked file,
    re-argue a closed decision, create its own task and write a standing order. Each call
    is refused, the refusal cap ends the run and revokes its token, and nothing it wanted
    is reached. With a run token it also cannot do anything only the chairman may."""
    from tests.attack.work_support import OBSERVABLE, Crew
    from tests.support import agent_call, live_run

    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"agent.max_wakes_per_hour": 60})
    crew = Crew(app, owner, project)
    crew.requirement = await crew.add_requirement()
    await crew.ok("CEO", "agent.hire_team", team="build", role="Generalist")
    task = await crew.task()
    await app.ok("decisions.decide", owner, project_id=project, text="Launch: in spring.")
    await app.ok(
        "artifacts.upload", owner, project_id=project, name="plan.md", content_base64="b3Vycw=="
    )
    await app.ok("artifacts.lock", owner, project_id=project, name="plan.md")
    await crew.finish("CEO")

    token = (await live_run(app, project, seat="build")).token
    reserved = {
        "settings.change_project": {"changes": {"budget.tokens": 90_000_000}, "reason": "More."},
        "orders.pin": {"what": "Agents may mark their own work done."},
        "decisions.reopen": {"decision_id": 1},
        "corrections.record": {"words": "Everything was fine."},
        "artifacts.unlock": {"name": "plan.md"},
        "audits.settle": {"audit_id": 1, "verdict": "passed"},
        "memory.forget": {"memory_id": "anything"},
        "projects.stop": {},
        "credentials.list": {},
    }
    for name, values in reserved.items():
        answer = await app.call(name, token, project_id=project, **values)
        assert answer.status_code in (401, 403), name
    await crew.finish("build")

    load(app, "rule-breaker")
    from tests.support import wake

    await wake(app, project, "build")
    await settle(app)

    runs = (await app.ok("runs.list", owner, project_id=project))["items"]
    breaker = next(r for r in runs if r["state"] == "terminated")
    async with app.runtime.sessions() as session:
        refusals = list(
            await session.scalars(
                select(RunRefusal.rule).where(RunRefusal.run_id == breaker["run_id"])
            )
        )
        tasks_now = list(await session.scalars(select(Task)))
    assert len(refusals) == 5
    assert set(refusals) <= {"WRK-6", "WRK-9", "INV-3", "WRK-14", "ART-5", "INV-26", None}
    assert [(t.id, t.state, t.claimant_id) for t in tasks_now] == [(task["id"], "ready", None)]
    after = await agent_call(app, token, "agent.board")
    assert after.status_code == 401

    assert (await app.ok("decisions.list", owner, project_id=project))["items"][0]["state"] == (
        "closed"
    )
    assert (await app.ok("orders.list", owner, project_id=project))["items"] == []
    versions = await app.ok("artifacts.versions", owner, project_id=project, name="plan.md")
    assert len(versions["items"]) == 1
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert all("got away with it" not in m["body"] for m in history)
    assert OBSERVABLE["title"] == task["title"]


async def test_scenario_a_solo_project_works_from_start_to_finish(app: App) -> None:
    """Section 3 "solo", WRK-2, WRK-4, WRK-6, WRK-9, INV-2, INV-3, P5: one agent plans and
    does the work.

    - With independent read on (the default), the CEO creates a task with a command test,
      claims it, does it and completes it; the platform's check closes it as verified. An
      observable task is read by the reviewer seat the platform staffed.
    - With independent read off, the project is one agent: the reviewer is stood down and
      an observable task closes as self-reported, never as verified or reviewed.
    - Turning independent read on again brings the reviewer back at once."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"agent.max_wakes_per_hour": 60})
    workspace = app.runtime.config.data_dir / "workspaces" / project
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "check.sh").write_text("grep -q 41 report.txt\n")

    def tool(name: str, **arguments: Any) -> dict[str, Any]:
        return {"tools": [{"name": name, "arguments": arguments}]}

    async def active() -> list[str]:
        seats = (await app.ok("roster.show", owner, project_id=project))["seats"]
        return [seat["name"] for seat in seats if seat["state"] == "active"]

    async def run_ceo(*turns: dict[str, Any]) -> None:
        app.script("CEO/work", *turns, {"text": "Done for now."})
        await app.ok("chat.command", owner, project_id=project, text="/do Carry on.")
        await app.work()
        app.script("CEO/work", {"text": "Nothing to do."})
        await settle(app)

    observable = {
        "goal": "Summarise the three interviews in one page.",
        "success_test": "A one-page summary names all three interviewees.",
        "test_kind": "observable",
        "requirement_id": 1,
    }
    await app.ok(
        "requirements.add", owner, project_id=project, text="The interviews are summarised.",
        test_kind="observable", success_test="A reader finds every interview summarised.",
        estimate_runs=20,
    )  # fmt: skip
    assert await active() == ["CEO", "Reviewer"]
    await run_ceo(
        tool(
            "agent_create_task",
            title="Write the report",
            requirement_id=1,
            test_kind="command",
            goal="Write report.txt with the third-quarter orders.",
            success_test="test -f check.sh && sh check.sh",
            test_files=["check.sh"],
        ),
        tool("agent_claim_task", task_id=1),
        tool("write_file", path="report.txt", content="Third quarter: 41 orders.\n"),
        tool("agent_complete_task", task_id=1, evidence="report.txt holds the count: 41."),
    )
    await app.work_jobs.run_checks()

    app.script(
        "Reviewer/work",
        tool("agent_review_task", task_id=2, ok=True, notes="Read it; all three are named."),
        {"text": "Reviewed."},
    )
    await run_ceo(
        tool("agent_create_task", title="Write the summary", **observable),
        tool("agent_claim_task", task_id=2),
        tool("agent_complete_task", task_id=2, evidence="The summary is in summary.md."),
    )

    off = {"review.independent": False}
    await app.ok(
        "settings.change_project", owner, project_id=project, changes=off,
        reason="Running solo and accepting the cost.",
    )  # fmt: skip
    await app.work_jobs.keep_work_moving()
    assert await active() == ["CEO"]
    await run_ceo(
        tool("agent_create_task", title="Write the second summary", **observable),
        tool("agent_claim_task", task_id=3),
        tool("agent_complete_task", task_id=3, evidence="The summary is in summary-2.md."),
    )

    await app.ok(
        "settings.change_project", owner, project_id=project,
        changes={"review.independent": True}, reason="Reviews are worth it again.",
    )  # fmt: skip
    app.script(
        "Reviewer/work",
        tool("agent_review_task", task_id=4, ok=True, notes="Read it; it meets the test."),
        {"text": "Reviewed."},
    )
    await run_ceo(
        tool("agent_create_task", title="Write the third summary", **observable),
        tool("agent_claim_task", task_id=4),
        tool("agent_complete_task", task_id=4, evidence="The summary is in summary-3.md."),
    )

    tasks = (await app.ok("tasks.list", owner, project_id=project))["items"]
    assert [(t["state"], t["label"]) for t in tasks] == [
        ("done", "verified"),
        ("done", "reviewed"),
        ("done", "self-reported"),
        ("done", "reviewed"),
    ]
    assert await active() == ["CEO", "Reviewer"]
    async with app.runtime.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RunRefusal)) == 0
