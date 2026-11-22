"""Helpers for the planning tests: a solo crew that meets requirements quickly, and
direct control of spend and run length so the arithmetic can be asserted exactly."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import update

from crewmind.storage.models import LedgerLine, Requirement
from tests.attack.work_support import Crew
from tests.conftest import FakeClock
from tests.support import App

SOLO: dict[str, Any] = {"review.independent": False}
TASK = {
    "title": "Do the work for it",
    "goal": "Produce what the requirement asks for.",
    "success_test": "The requirement's own test will pass.",
    "test_kind": "observable",
}


async def view(crew: Crew) -> dict[str, Any]:
    return await crew.app.ok("plan.show", crew.owner, project_id=crew.project)


async def command_requirement(crew: Crew, name: str, runs: int = 2, **fields: Any) -> int:
    """Scope the chairman adds that is met when `<name>.txt` exists in the workspace."""
    return await crew.add_requirement(
        text=f"The {name} page is published.", test_kind="command",
        success_test=f"test -f {name}.txt", estimate_runs=runs, **fields,
    )  # fmt: skip


async def meet(crew: Crew, clock: FakeClock, requirement: int, name: str) -> None:
    """Do one task under a command requirement and let the platform find it met."""
    crew.write(f"{name}.txt", "done")
    task = await crew.ok("CEO", "agent.create_task", requirement_id=requirement, **TASK)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    await crew.ok("CEO", "agent.complete_task", task_id=task["id"], evidence="The file is there.")
    clock.advance(minutes=1)
    await crew.app.planning.tick()


async def spend(app: App, project: str, tokens: int, at: datetime | None = None) -> None:
    """Put tokens on the ledger as a model call would, without running a model."""
    async with app.runtime.sessions() as session, session.begin():
        session.add(
            LedgerLine(
                project_id=project,
                kind="model",
                unit="tokens",
                provider="mock",
                model="mock",
                input_tokens=tokens,
                counted=tokens,
                at=at or app.runtime.clock(),
            )
        )


async def set_states(app: App, states: dict[int, str]) -> None:
    """Put requirements in a state directly, to set up an arithmetic case."""
    async with app.runtime.sessions() as session, session.begin():
        for requirement, state in states.items():
            await session.execute(
                update(Requirement).where(Requirement.id == requirement).values(state=state)
            )
