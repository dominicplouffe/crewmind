"""Attacks on what everyone knows about a project's connections: the Founder sees names and
descriptions and never a value, a spec's grants attach only what its creator can see, a run's
context pack names what it may use and what it lacks, and a broken connection shows in the
project's health with its fix (CON-14, FND-2, FND-9, LIB-4, CON-4)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select

from crewmind.domain.secrets.store import ensure_master_key
from crewmind.gateway.protocol import CompletionRequest
from crewmind.storage.models import Connection, Run
from tests.attack.test_connections import BLOG_WRITER, blog_project
from tests.attack.test_specs import SPEC as BASE_SPEC
from tests.founder_support import BRIEF, SPEC, credential, propose, script, tool
from tests.support import App, running_project

pytestmark = pytest.mark.usefixtures("quick_rehearsal")

VALUE = "wp-app-password-0451-unguessable"
OTHER = "someone-elses-password-7781-unguessable"


@pytest.fixture(autouse=True)
def master_key(app: App) -> None:
    ensure_master_key(app.runtime.config.master_key_file)


def blog_spec(credentials: list[dict[str, Any]]) -> dict[str, Any]:
    spec = {
        key: value for key, value in BASE_SPEC.items() if key not in ("roles", "paying_credential")
    }
    return {
        **spec,
        "teams": [{"name": "Desk", "role": "blog-writer", "members": ["Wren"]}],
        "credentials": credentials,
    }


@pytest.mark.attack("CON-14")
@pytest.mark.attack("LIB-4")
async def test_LIB_4_creating_from_a_spec_attaches_only_what_its_creator_can_see(app: App) -> None:
    """LIB-4, CON-4, CON-5, CON-14, INV-5: each grant of a spec attaches the creator's own or
    the install's connection of that name and kind to the roles named on the roster;
    another person's connection of the same name is never attached; what the creator lacks
    stays an open need, listed as missing."""
    owner = await app.person("owner@example.com")
    other = await app.person("other@example.com")
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=VALUE, sites=["example.com"],
    )  # fmt: skip
    await app.ok(
        "connections.add_variable", other, name="region", description="Their region.",
        value="eu-west",
    )  # fmt: skip
    await app.ok(
        "connections.add_secret", other, name="maps", description="Their maps key.",
        value=OTHER, sites=["maps.example.com"],
    )  # fmt: skip
    created = await app.ok(
        "projects.import_spec",
        owner,
        **blog_spec(
            [
                {"name": "WordPress", "roles": ["blog-writer"]},
                {"name": "region", "kind": "variable", "roles": ["blog-writer"]},
                {"name": "maps", "roles": ["blog-writer", "not-on-roster"]},
            ]
        ),
    )
    project = created["project_id"]
    shown = await app.ok("connections.for_project", owner, project_id=project)
    attached = {link["item"]["name"]: link for link in shown["attached"]}
    assert set(attached) == {"wordpress"}
    assert attached["wordpress"]["roles"] == ["blog-writer"]
    open_needs = {need["name"]: need["state"] for need in shown["needs"]}
    assert open_needs == {"wordpress": "met", "region": "open", "maps": "open"}
    assert any("region" in line for line in created["waiting"])
    assert OTHER not in json.dumps(created) + json.dumps(shown)


@pytest.mark.attack("FND-2")
@pytest.mark.attack("CON-14")
async def test_FND_2_the_founder_sees_connections_by_name_and_never_a_value(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FND-2, FND-9, CON-14, INV-6: the Founder's prompt and its tool list the chairman's
    connections and the install's by name, kind and description, and the needs of each
    role; never a value, and never another person's connection. The draft's view lists each
    need of its roster as had or missing, and granted or not."""
    owner = await app.person("owner@example.com")
    other = await app.person("other@example.com")
    await credential(app, owner, "main")
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="The blog's password.",
        value=VALUE, sites=["example.com"],
    )  # fmt: skip
    await app.ok(
        "connections.add_secret", other, name="hidden", description="Not the owner's.",
        value=OTHER, sites=["example.com"],
    )  # fmt: skip
    sent: list[CompletionRequest] = []
    complete = app.runtime.mock.complete

    async def recording(request: CompletionRequest, **kwargs: Any) -> Any:
        sent.append(request)
        return await complete(request, **kwargs)

    monkeypatch.setattr(app.runtime.mock, "complete", recording)
    teams = [*SPEC["teams"], {"name": "Desk", "role": "blog-writer", "members": ["Wren"]}]
    grants = [{"name": "wordpress", "roles": ["blog-writer"]}]
    script(
        app,
        tool("list_connections"),
        propose(spec={"teams": teams, "credentials": grants}),
        {"text": "The blog writer needs wordpress, which you have."},
    )
    started = await app.ok("founder.start", owner, brief=BRIEF)
    await app.founder.tick()
    said = json.dumps([request.model_dump(mode="json") for request in sent])
    assert "wordpress (secret): The blog's password." in said
    assert "Needs: wordpress" in said
    assert VALUE not in said
    assert OTHER not in said
    assert "hidden" not in said
    shown = await app.ok("founder.show", owner, drafting_id=started["drafting_id"])
    assert shown["needs"] == [
        {"kind": "secret", "name": "wordpress", "roles": ["blog-writer"], "have": True,
         "granted": True},
    ]  # fmt: skip


@pytest.mark.attack("CON-14")
async def test_CON_14_a_run_is_told_what_it_may_use_and_what_its_role_lacks(app: App) -> None:
    """CON-14, CON-6, CON-8: the context pack names a secret sent for the run and its sites,
    without its value, and what the role needs but does not have."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok(
        "connections.add_secret", owner, name="search", description="The search API key.",
        value=VALUE, sites=["api.search.example"], project_id=project, roles=["*"],
    )  # fmt: skip
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="Desk", role=BLOG_WRITER, members=1
    )
    app.script("*", {"text": "done"})
    from tests.support import wake

    await wake(app, project)
    await app.work()
    async with app.runtime.sessions() as session:
        packs = [run.context_pack or "" for run in await session.scalars(select(Run))]
    pack = next(pack for pack in packs if "search" in pack)
    assert "search (secret, sent for you to api.search.example)" in pack
    assert VALUE not in "".join(packs)


@pytest.mark.attack("CON-14")
async def test_CON_5_a_run_is_told_the_chairman_marked_its_need_done(app: App) -> None:
    """CON-5, CON-14, CON-8: secrets given under the chairman's own names (a user name and a
    password apart) are listed with their descriptions, and the run is told the chairman says
    its need is among them, so the agent works out which is which. No value is in the pack."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok(
        "roster.hire_team", owner, project_id=project, team="Desk", role=BLOG_WRITER, members=1
    )
    for name, value in (("WP_USER", "wp-user-name-0451"), ("WP_PASS", VALUE)):
        await app.ok(
            "connections.add_secret", owner, name=name, description=f"WordPress {name}.",
            value=value, delivery="given", scope="project", project_id=project,
            roles=["blog-writer"],
        )  # fmt: skip
    await app.ok("connections.mark_need_done", owner, project_id=project, need="wordpress")
    app.script("*", {"text": "done"})
    from tests.support import wake

    await wake(app, project, seat="Desk")
    await app.work()
    async with app.runtime.sessions() as session:
        packs = [run.context_pack or "" for run in await session.scalars(select(Run))]
    pack = next(pack for pack in packs if "WP_PASS" in pack)
    assert "WP_USER (secret, the environment variable WP_USER)" in pack
    assert "The chairman says these needs of your role are in what you are given" in pack
    assert "the secret wordpress, for blog-writer" in pack
    assert "does not have yet" not in pack
    assert VALUE not in "".join(packs)
    assert "wp-user-name-0451" not in "".join(packs)


@pytest.mark.attack("CON-14")
async def test_CON_14_a_broken_connection_shows_in_project_health_with_its_fix(app: App) -> None:
    """CON-14, CON-16: an expired secret and a missing need of a started project each show
    in the project's health, naming the thing and the fix."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    await app.ok("projects.start", owner, project_id=project, without_missing=True)
    health = (await app.ok("projects.status", owner, project_id=project))["health"]
    assert any("Missing the secret wordpress" in line and "add it" in line for line in health)
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=VALUE, sites=["example.com"], project_id=project,
    )  # fmt: skip
    assert (await app.ok("projects.status", owner, project_id=project))["health"] == []
    async with app.runtime.sessions() as session, session.begin():
        item = await session.scalar(select(Connection).where(Connection.name == "wordpress"))
        assert item is not None
        item.state = "expired"
    health = (await app.ok("projects.status", owner, project_id=project))["health"]
    assert any("wordpress has expired" in line and "replace" in line for line in health)
