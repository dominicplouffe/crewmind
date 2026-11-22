"""Speed as a requirement (SPD-1 to SPD-4, SPD-6, SPD-8, SPD-9)."""

from __future__ import annotations

from typing import Any

from tests.attack.delivery_support import SOLO, command_requirement, set_states, spend, view
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App, agent_call, live_run

TASK = {
    "title": "Write the first page",
    "goal": "Write the first page of the site.",
    "success_test": "The page exists and can be opened.",
    "test_kind": "observable",
}


async def flags(crew: Crew) -> list[str]:
    return (await view(crew))["speed"]["flags"]


async def lines(crew: Crew, words: str) -> list[dict[str, Any]]:
    history = (await crew.app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    return [line for line in history if words in line["body"]]


async def test_SPD_3_the_ceo_plans_at_once_and_a_slow_start_is_said_out_loud(
    app: App, clock: FakeClock
) -> None:
    """SPD-3, SPD-1: starting a project queues the CEO's first planning run at once, with
    no directive. A Deliver project with no task claimed within `start.first_task_within`
    gets a slow-start flag that names the cause, once; the cause is kept current, and
    the flag clears when a task is claimed."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    await app.ok("projects.start", owner, project_id=project)
    app.script("CEO/work", {"text": "Thinking about the plan."})
    assert await app.work() == 1
    crew = Crew(app, owner, project)
    run = await live_run(app, project)
    pack = (await agent_call(app, run.token, "agent.context")).json()["context_pack"]
    assert "There is no scope yet." in pack

    clock.advance(minutes=9)
    await app.planning.tick()
    assert await flags(crew) == []
    clock.advance(minutes=2)
    await app.planning.tick()
    await app.planning.tick()
    said = "Slow start: no task was claimed in the first 10 minutes because"
    assert await flags(crew) == [f"{said} no requirement has been proposed."]
    assert len(await lines(crew, "Slow start")) == 1

    crew.requirement = await crew.add_requirement()
    await app.planning.tick()
    assert await flags(crew) == [
        f"{said} scope is accepted and estimated but no task has been created."
    ]
    task = await crew.ok("CEO", "agent.create_task", **TASK)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    await app.planning.tick()
    assert await flags(crew) == []


async def test_SPD_4_SPD_6_no_visible_output_is_flagged_until_something_is_published(
    app: App, clock: FakeClock
) -> None:
    """SPD-4, SPD-6: a Deliver project that has run for `output.first_within` with no
    deliverable published gets a no-visible-output flag. Publishing puts the deliverable
    in the chat at once and clears the flag."""
    crew = await Crew.start(app, team=False, settings=SOLO)
    task = await crew.ok("CEO", "agent.create_task", **TASK)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    clock.advance(hours=7)
    await crew.finish_all()
    await app.planning.tick()
    assert await flags(crew) == [
        "No visible output: the project has run for 6 hours and nothing has been published "
        "for the chairman to open."
    ]
    await crew.ok(
        "CEO", "agent.publish_artifact", name="first-page.md", content="# The first page",
        purpose="The first page of the site",
    )  # fmt: skip
    assert len(await lines(crew, "first-page.md")) >= 1
    await app.planning.tick()
    assert await flags(crew) == []


async def test_SPD_9_a_seat_that_closes_nothing_is_said_out_loud(
    app: App, clock: FakeClock
) -> None:
    """SPD-9: a team seat that has closed nothing in `seat.idle_after` raises a seat-idle
    flag naming it. A seat that closed a task is left out, and the CEO and the reviewer
    seat the platform staffed are never listed."""
    crew = await Crew.start(app)

    async def idle(crew: Crew) -> list[str]:
        return [flag for flag in await flags(crew) if flag.startswith("Seat idle")]

    async def build_1_closes_a_task() -> None:
        task = await crew.task()
        await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
        await crew.ok(
            "build-1", "agent.complete_task", task_id=task["id"], evidence="See the page."
        )
        await crew.ok(
            "Reviewer", "agent.review_task", task_id=task["id"], ok=True, notes="Read it all."
        )
        await crew.finish_all()

    clock.advance(days=2)
    await build_1_closes_a_task()
    await app.planning.tick()
    assert await idle(crew) == []
    clock.advance(days=1, hours=12)
    await app.planning.tick()
    crew.owner = await app.login(crew.owner.email)
    assert await idle(crew) == ["Seat idle: build-2 closed nothing in 3 days."]
    clock.advance(days=2)
    await app.planning.tick()
    crew.owner = await app.login(crew.owner.email)
    assert await idle(crew) == ["Seat idle: build-1, build-2 closed nothing in 3 days."]
    assert len(await lines(crew, "Seat idle")) == 2


async def test_SPD_2_the_plan_shows_the_longest_dependency_chain(app: App) -> None:
    """SPD-2, PLN-2: the plan view shows the longest dependency chain of open scope, in
    adjusted runs and in the order it must be done."""
    crew = await Crew.start(app, team=False)
    await set_states(app, {crew.requirement: "cut"})
    first = await command_requirement(crew, "home", runs=2)
    second = await command_requirement(crew, "pricing", runs=3, depends_on=[first])
    third = await command_requirement(crew, "signup", runs=4, depends_on=[second])
    await command_requirement(crew, "about", runs=5)
    chain = (await view(crew))["longest_chain"]
    assert chain == {"runs": 9, "requirements": [first, second, third]}
    await set_states(app, {third: "met"})
    chain = (await view(crew))["longest_chain"]
    assert chain == {"runs": 5, "requirements": [first, second]}


async def test_SPD_8_every_stretch_of_time_is_attributed(app: App, clock: FakeClock) -> None:
    """SPD-8: the plan shows where the time went: working, waiting on the chairman,
    waiting on a limit or the budget, waiting on a provider, and reviewing. Time held by
    the chairman is counted apart from time the budget wall took, and the time to the
    first task is measured from the start."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"budget.tokens": 1_000_000})

    async def tick_after(**delta: float) -> dict[str, int]:
        clock.advance(**delta)
        await crew.finish_all()
        await app.planning.tick()
        return (await view(crew))["speed"]["where"]

    task = await crew.ok("CEO", "agent.create_task", **TASK)
    clock.advance(minutes=30)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    where = await tick_after(minutes=30)
    assert where["working"] == 3600
    await app.ok("projects.hold", crew.owner, project_id=crew.project)
    where = await tick_after(hours=2)
    assert (where["working"], where["waiting on the chairman"]) == (3600, 7200)
    await app.ok("projects.resume", crew.owner, project_id=crew.project)
    await spend(app, crew.project, 1_000_000)
    await app.scheduler.tick()
    where = await tick_after(hours=3)
    assert where["waiting on a limit or the budget"] == 10_800
    assert where["waiting on a provider"] == where["reviewing"] == 0
    speed = (await view(crew))["speed"]
    assert speed["to_first_task_seconds"] == 1800
    assert speed["to_first_deliverable_seconds"] is None
    assert sum(where.values()) == 6 * 3600
