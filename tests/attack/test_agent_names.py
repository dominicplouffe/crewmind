"""Agent names (EXE-18): every agent has its own person-like name, only a chair changes it,
mentions reach it by that name, and the agent is told it."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from crewmind.catalog import catalog
from crewmind.catalog.operation import Principal
from crewmind.domain.execution import names
from crewmind.storage.models import Message, Seat
from tests.attack.harness import assert_refused
from tests.support import App, agent_call, live_run, running_project


def _by_seat(roster: dict[str, Any]) -> dict[str, str]:
    return {seat["name"]: seat["display_name"] for seat in roster["seats"]}


def test_EXE_18_the_pool_is_distinct_first_names_that_crews_do_not_use() -> None:
    """EXE-18: the pool holds about sixty different first names, none a name the shipped
    crews or the demo give their members; a project always draws the same name, and a
    used-up pool goes round again with a number."""
    import json
    from importlib import resources

    assert len(names.POOL) >= 50
    assert len({name.casefold() for name in names.POOL}) == len(names.POOL)
    crews = resources.files("crewmind.content").joinpath("library", "crews")
    given = {"Maya", "Theo", "Priya", "Fay", "Noor"}
    for entry in crews.iterdir():
        if entry.name.endswith(".json"):
            for team in json.loads(entry.read_text("utf-8"))["teams"]:
                given.update(team["members"])
    assert given.isdisjoint(names.POOL)
    assert names.draw("p1", set()) == names.draw("p1", set())
    assert names.draw("p1", {names.draw("p1", set()).upper()}) != names.draw("p1", set())
    assert names.draw("p1", set(names.POOL)).endswith(" 2")
    assert names.tidy("  Maya   Lopez ") == "Maya Lopez"


@pytest.mark.attack("EXE-18")
async def test_EXE_18_every_agent_has_its_own_name(app: App) -> None:
    """EXE-18, EXE-1, LIB-2: the CEO and the reviewer draw different first names; members
    hired with names show those names; members hired by count draw names too; a given name
    that another agent already goes by is refused."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    first = _by_seat(await app.ok("roster.show", owner, project_id=project))
    assert set(first) == {"CEO", "Reviewer"}
    assert first["CEO"] in names.POOL
    assert first["Reviewer"] in names.POOL
    assert first["CEO"] != first["Reviewer"]

    named = await app.ok(
        "roster.hire_team", owner, project_id=project, team="web", role="Generalist",
        names=["Theo", "Priya"],
    )  # fmt: skip
    counted = await app.ok(
        "roster.hire_team", owner, project_id=project, team="ops", role="Generalist", members=2
    )
    shown = _by_seat(counted)
    assert _by_seat(named)["Theo"] == "Theo"
    assert shown["Priya"] == "Priya"
    assert shown["ops-1"] in names.POOL
    assert len({name.casefold() for name in shown.values()}) == len(shown)

    clash = await app.call(
        "roster.hire_team", owner, project_id=project, team="more", role="Generalist",
        names=[first["CEO"].lower()],
    )  # fmt: skip
    assert_refused(clash, rule="EXE-1", code="seat_name_taken")


@pytest.mark.attack("EXE-18")
async def test_EXE_18_only_a_chair_renames_an_agent(app: App) -> None:
    """EXE-18, INV-21, ACC-5, P3: the chairman or a co-chair renames an agent and the change
    is recorded with before and after; spaces are tidied; an empty name, or one another
    agent goes by, is refused; an observer and an agent's run token cannot rename, and the
    agent API has no rename at all."""
    owner = await app.person("owner@example.com")
    cochair = await app.person("cochair@example.com")
    observer = await app.person("observer@example.com")
    project = await running_project(app, owner)
    await app.ok("members.add", owner, project_id=project, email=cochair.email, role="co-chair")
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")
    before = _by_seat(await app.ok("roster.show", owner, project_id=project))

    renamed = await app.ok(
        "roster.rename_seat", owner, project_id=project, seat="CEO", display_name="  Ada   Ross "
    )
    assert _by_seat(renamed)["CEO"] == "Ada Ross"
    again = await app.ok(
        "roster.rename_seat", cochair, project_id=project, seat="CEO", display_name="Ada"
    )
    assert _by_seat(again)["CEO"] == "Ada"
    events = [e for e in await app.events(owner, project) if e["type"] == "seat.renamed"]
    assert events[-1]["before"] == {"display_name": "Ada Ross"}
    assert events[-1]["after"] == {"display_name": "Ada"}
    assert any(e["before"] == {"display_name": before["CEO"]} for e in events)

    for wanted, code in (
        ("   ", "name_is_empty"),
        (before["Reviewer"].upper(), "name_taken"),
        ("reviewer", "name_taken"),
    ):
        refused = await app.call(
            "roster.rename_seat", owner, project_id=project, seat="CEO", display_name=wanted
        )
        assert_refused(refused, rule="EXE-18", code=code)
    assert_refused(
        await app.call(
            "roster.rename_seat", observer, project_id=project, seat="CEO", display_name="Bo"
        ),
        rule="ACC-5",
    )
    run = await live_run(app, project)
    as_agent = await app.call(
        "roster.rename_seat", run.token, project_id=project, seat="CEO", display_name="Boss"
    )
    assert as_agent.status_code == 401
    on_agent_api = await agent_call(app, run.token, "roster.rename_seat", seat="CEO")
    assert on_agent_api.status_code == 404
    assert Principal.AGENT_RUN not in catalog.get("roster.rename_seat").principals
    assert _by_seat(await app.ok("roster.show", owner, project_id=project))["CEO"] == "Ada"


async def test_EXE_18_a_mention_by_name_reaches_the_agent_and_the_agent_knows_its_name(
    app: App,
) -> None:
    """EXE-18, CHAT-2, EXE-15: `@Name` addresses the agent shown by that name, without case,
    as `@CEO` still does; the agent's prompt and context pack name it and list the crew by
    name and role."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="web", role="Generalist",
        names=["Theo"],
    )  # fmt: skip
    shown = _by_seat(await app.ok("roster.show", owner, project_id=project))
    ceo = shown["CEO"]
    for body in (f"@{ceo.lower()} how is it going?", "@CEO how is it going?"):
        sent = await app.ok("chat.send", owner, project_id=project, body=body)
        async with app.runtime.sessions() as session:
            message = await session.get(Message, sent["id"])
            seat_id = await session.scalar(
                select(Seat.id).where(Seat.project_id == project, Seat.name == "CEO")
            )
        assert message is not None
        assert message.addressed == [seat_id]

    run = await live_run(app, project)
    pack = (await agent_call(app, run.token, "agent.context")).json()
    assert pack["system_prompt"].startswith(f"You are {ceo}, the CEO")
    assert f"You are {ceo} (seat CEO), the CEO" in pack["context_pack"]
    assert "- Theo: Generalist, team web, lead" in pack["context_pack"]
    me = (await agent_call(app, run.token, "agent.whoami")).json()
    assert (me["seat"], me["name"]) == ("CEO", ceo)
