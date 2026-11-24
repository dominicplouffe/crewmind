"""Requirements end to end: a command requirement, wrap-up mode, readiness over any
sequence of scope changes, and team stand-down (PLN-2, PLN-10, PLN-12, GOV-3, INV-18)."""

from __future__ import annotations

import random
from typing import Any

import pytest
from sqlalchemy import select, update

from nightsquad.storage.models import Requirement, RequirementDependency, Task
from tests.attack.harness import assert_refused
from tests.attack.test_planning import SCOPE, TASK, plan, propose
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App

SOLO: dict[str, Any] = {"review.independent": False}


def assert_acyclic(needs: dict[int, set[int]]) -> None:
    def walk(node: int, path: tuple[int, ...]) -> None:
        assert node not in path, f"loop through {node}"
        for needed in needs.get(node, ()):
            walk(needed, (*path, node))

    for node in needs:
        walk(node, ())


async def solo_task(crew: Crew, requirement: int) -> None:
    """In a solo project with independent read off, the CEO does a task itself."""
    task = await crew.ok("CEO", "agent.create_task", requirement_id=requirement, **TASK)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    await crew.ok("CEO", "agent.complete_task", task_id=task["id"], evidence="The page is up.")


async def test_PLN_10_a_command_requirement_is_met_when_the_platform_runs_its_test(
    app: App, clock: FakeClock
) -> None:
    """PLN-10: the platform runs a command requirement's test once its work is done. A
    failure sends it back to in progress and it is not run again until a task under it is
    done or a file changes. The third failure is escalated to the CEO once. A pass writes
    met with the actual runs."""
    crew = await Crew.start(app, team=False, settings=SOLO)
    wanted = await crew.add_requirement(
        text="The pricing page is published.", test_kind="command",
        success_test="test -f pricing.html", estimate_runs=2,
    )  # fmt: skip

    for failures in (1, 2, 3):
        clock.advance(minutes=1)
        await solo_task(crew, wanted)
        clock.advance(minutes=1)
        await app.planning.tick()
        shown = (await plan(crew))[wanted]
        assert (shown["state"], shown["failures"]) == ("in progress", failures)
        assert await app.planning.run_requirement_tests() == 0
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    escalations = [m for m in lines if "has failed its test 3 times" in m["body"]]
    assert len(escalations) == 1

    crew.write("pricing.html", "<h1>Pricing</h1>")
    clock.advance(minutes=1)
    await app.ok(
        "artifacts.upload", crew.owner, project_id=crew.project, name="pricing.html",
        content_base64="PGgxPlByaWNpbmc8L2gxPg==",
    )  # fmt: skip
    clock.advance(minutes=1)
    await app.planning.tick()
    shown = (await plan(crew))[wanted]
    assert (shown["state"], shown["ruling"], shown["failures"]) == ("met", "passed", 3)
    assert shown["actual_runs"] >= 3
    lines = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    assert len([m for m in lines if "has failed its test" in m["body"]]) == 1
    assert any(f"Requirement {wanted} is met" in m["body"] for m in lines)


@pytest.mark.attack("GOV-3")
async def test_GOV_3_in_wrap_up_mode_no_new_scope_is_taken_on(app: App) -> None:
    """GOV-3, R-24: at `budget.wrapup_at`, a new requirement is refused, and a new task is
    refused unless it serves a requirement already in progress."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"budget.tokens": 1_000_000})
    idle = await crew.add_requirement(text="A second page nobody has started.")
    task = await crew.ok("CEO", "agent.create_task", **TASK)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    app.script("CEO/work", {"text": "Working.", "usage": {"input": 910_000, "output": 0}})
    await crew.finish("CEO")
    await app.ok("chat.command", crew.owner, project_id=crew.project, text="/do Carry on.")
    await app.work()

    refused = await crew.call("CEO", "agent.propose_requirement", **SCOPE)
    envelope = assert_refused(refused, rule="GOV-3", code="wrap_up_mode")
    assert "910,000 of 1,000,000 tokens used (91%)" in envelope.message
    fresh = await crew.call("CEO", "agent.create_task", requirement_id=idle, **TASK)
    assert_refused(fresh, rule="GOV-3", code="wrap_up_mode")
    await crew.ok("CEO", "agent.complete_task", task_id=task["id"], evidence="The page is up.")
    under_way = await crew.call("CEO", "agent.create_task", **TASK | {"title": "Fix the header"})
    assert under_way.status_code == 200, under_way.text


@pytest.mark.parametrize("seed", range(4))
async def test_INV_18_INV_19_any_sequence_of_scope_changes_keeps_work_under_ready_scope(
    app: App, seed: int
) -> None:
    """INV-18, INV-19, PLN-2 as a property: after any sequence of propose, accept, cut,
    reopen, dependency and stage changes, a task is created only under a requirement that
    is accepted or in progress, estimated, with every dependency met, in the lowest open
    stage; the graph has no loop; and no open task sits under a cut requirement."""
    crew = await Crew.start(app, team=False, settings=SOLO | {"tasks.max_open": 30})
    choose = random.Random(seed)
    ids = [crew.requirement]
    for _ in range(14):
        target = choose.choice(ids)
        other = choose.choice(ids)
        move = choose.choice(["propose", "accept", "cut", "reopen", "depend", "stage", "claim"])
        if move == "propose":
            ids.append(await propose(crew, stage=choose.choice([1, 1, 2])))
        elif move == "accept":
            await crew.call("CEO", "agent.accept_requirement", requirement_id=target)
        elif move == "cut":
            await app.call(
                "requirements.cut", crew.owner, project_id=crew.project, requirement_id=target,
                reason="Cut by the property test.",
            )  # fmt: skip
        elif move == "reopen":
            await app.call(
                "requirements.reopen", crew.owner, project_id=crew.project, requirement_id=target
            )
        elif move == "depend":
            await app.call(
                "requirements.change", crew.owner, project_id=crew.project,
                requirement_id=target, depends_on=[other],
            )  # fmt: skip
        elif move == "stage":
            await app.call(
                "requirements.change", crew.owner, project_id=crew.project,
                requirement_id=target, stage=choose.choice([1, 2, 3]),
            )  # fmt: skip

        async with app.runtime.sessions() as session:
            rows = {r.id: r for r in await session.scalars(select(Requirement))}
            needs: dict[int, set[int]] = {}
            for edge in await session.scalars(select(RequirementDependency)):
                needs.setdefault(edge.requirement_id, set()).add(edge.depends_on)
        open_scope = [
            r for r in rows.values() if r.state in ("accepted", "in progress", "checking")
        ]
        lowest = min((r.stage for r in open_scope), default=None)
        for requirement in rows.values():
            ready = (
                requirement.state in ("accepted", "in progress")
                and requirement.estimate_runs is not None
                and all(
                    rows[n].state in ("met", "cut", "declined")
                    for n in needs.get(requirement.id, ())
                )
                and requirement.stage == lowest
            )
            made = await crew.call(
                "CEO", "agent.create_task", requirement_id=requirement.id, **TASK
            )
            assert (made.status_code == 200) == ready, (requirement.id, made.text)
            if made.status_code == 200 and move == "claim":
                await crew.call("CEO", "agent.claim_task", task_id=made.json()["id"])
            elif made.status_code == 200:
                await crew.ok(
                    "CEO", "agent.kill_task", task_id=made.json()["id"],
                    reason="Made only to probe readiness.",
                )  # fmt: skip
        assert_acyclic(needs)
        async with app.runtime.sessions() as session:
            stranded = await session.scalars(
                select(Task.id)
                .join(Requirement, Requirement.id == Task.requirement_id)
                .where(Requirement.state == "cut", Task.state.in_(["ready", "claimed", "blocked"]))
            )
            assert list(stranded) == []


async def test_PLN_12_a_team_is_stood_down_when_its_condition_becomes_true(
    app: App, clock: FakeClock
) -> None:
    """PLN-12: a team hired with "requirements met" is stood down by the platform once all
    accepted scope is met, but not while it still holds work. A condition the platform
    cannot check is refused at hire."""
    crew = await Crew.start(app, team=False)
    vague = await crew.call(
        "CEO", "agent.hire_team", team="build", role="Generalist", stand_down_when="when done"
    )
    assert vague.status_code == 403
    assert vague.json()["code"] == "unknown_stand_down_condition"
    await crew.ok(
        "CEO", "agent.hire_team", team="build", role="Generalist",
        stand_down_when="requirements met",
    )  # fmt: skip
    task = await crew.task()
    await crew.ok("build", "agent.claim_task", task_id=task["id"])
    await crew.ok("build", "agent.complete_task", task_id=task["id"], evidence="See summary.md.")
    await crew.ok(
        "Reviewer", "agent.review_task", task_id=task["id"], ok=True, notes="Read it all."
    )
    extra = await crew.task(title="One more page")
    await crew.finish("build")
    await crew.finish("Reviewer")
    await crew.finish("CEO")

    async with app.runtime.sessions() as session, session.begin():
        await session.execute(update(Requirement).values(state="met"))
    await app.planning.tick()
    seats = (await app.ok("roster.show", crew.owner, project_id=crew.project))["seats"]
    assert next(s for s in seats if s["name"] == "build")["state"] == "active"

    await crew.ok("CEO", "agent.kill_task", task_id=extra["id"], reason="Not needed after all.")
    await crew.finish_all()
    app.script("*", {"text": "Nothing to do."})
    while await app.work():
        pass
    clock.advance(minutes=1)
    await app.planning.tick()
    seats = (await app.ok("roster.show", crew.owner, project_id=crew.project))["seats"]
    assert next(s for s in seats if s["name"] == "build")["state"] == "stood down"
