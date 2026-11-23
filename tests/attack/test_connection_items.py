"""Attacks on secrets and variables: ownership, write-only values, attachment, grants,
collisions, reserved names, expiry and model clients (CON-1 to CON-5, CON-7, 7.18)."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.registry import catalog
from crewmind.domain.connections import expiry
from crewmind.domain.connections.model import CONNECTION_MACHINE
from crewmind.domain.secrets.store import ensure_master_key
from crewmind.storage.models import Alarm, Event, Seat, StoredSecret
from crewmind.surfaces.mcp.server import tool_name
from tests.attack.harness import assert_refused
from tests.attack.test_connections import blog_project, seats
from tests.attack.test_mcp import client_for, mcp_caller
from tests.conftest import FakeClock
from tests.support import Actor, App


@pytest.fixture(autouse=True)
def master_key(app: App) -> None:
    ensure_master_key(app.runtime.config.master_key_file)


VALUE = "wp-app-password-0451-unguessable"
SECOND = "replaced-password-9917-unguessable"


async def everything_said(app: App, owner: Actor, project: str) -> str:
    """Every read an owner or a model client could make, and the record, as one text."""
    said = [
        await app.ok("connections.list", owner, project_id=project),
        await app.ok("connections.for_project", owner, project_id=project),
        await app.ok("record.list", owner, project_id=project, limit=200),
    ]
    async with app.runtime.sessions() as session:
        said += [
            [event.before, event.after, event.detail]
            for event in await session.scalars(select(Event))
        ]
    return json.dumps(said, default=str)


async def writer_of(app: App, project: str) -> Seat:
    return next(
        seat
        for name, seat in (await seats(app, project)).items()
        if name != "CEO" and seat.kind != "reviewer"
    )


@pytest.mark.attack("CON-2")
async def test_CON_2_a_secret_value_never_comes_back_and_dies_with_its_item(app: App) -> None:
    """CON-2, INV-6, CON-16: a value goes in and never comes out, on any read or in the
    record; it is encrypted at rest; replacing leaves no trace of the old one; deleting
    destroys it. A value too short to mask, or a use that sends it nowhere, is refused."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)

    short = await app.call(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value="zq9x", sites=["example.com"],
    )  # fmt: skip
    assert_refused(short, rule="CON-2", code="secret_too_short")
    assert "zq9x" not in short.json()["message"]
    nowhere = await app.call(
        "connections.add_secret", owner, name="wordpress", description="WordPress.", value=VALUE
    )
    assert_refused(nowhere, rule="CON-2", code="sites_required")
    for site in ("https://example.com", "example.com/wp", "*.example.com", "example.com:443"):
        bad = await app.call(
            "connections.add_secret", owner, name="wordpress", description="WordPress.",
            value=VALUE, sites=[site],
        )  # fmt: skip
        assert_refused(bad, rule="CON-2", code="site_invalid")
    for header in ("Host", "cookie", "Mcp-Session-Id", "bad header"):
        bad = await app.call(
            "connections.add_secret", owner, name="wordpress", description="WordPress.",
            value=VALUE, sites=["example.com"], header_kind="header", header_name=header,
        )  # fmt: skip
        assert_refused(bad, rule="CON-2", code="header_name_invalid")

    added = await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=VALUE, sites=["Example.com"], header_kind="basic", basic_user="dom",
        project_id=project,
    )  # fmt: skip
    assert added["sites"] == ["example.com"]
    assert VALUE not in json.dumps(added)
    shown = await app.ok("connections.show", owner, connection="wordpress")
    assert VALUE not in json.dumps(shown)
    assert VALUE not in await everything_said(app, owner, project)
    async with app.runtime.sessions() as session:
        stored = list(await session.scalars(select(StoredSecret.ciphertext)))
    assert all(VALUE.encode() not in row for row in stored)

    await app.ok("connections.replace_secret", owner, connection="wordpress", value=SECOND)
    said = await everything_said(app, owner, project)
    assert VALUE not in said
    assert SECOND not in said
    await app.ok("connections.delete", owner, connection=added["id"])
    async with app.runtime.sessions() as session:
        owners = list(await session.scalars(select(StoredSecret.owner_id)))
    assert added["id"] not in owners
    gone = await app.call("connections.show", owner, connection=added["id"])
    assert gone.status_code == 404


@pytest.mark.attack("CON-1")
async def test_CON_1_only_its_owner_sees_or_changes_an_item(app: App) -> None:
    """CON-1: a person's items are theirs alone; install items are added and changed by an
    admin only and seen by everyone; a project's items by its chairs. Someone else's item
    answers like one that does not exist."""
    owner = await app.person("owner@example.com")
    other = await app.person("other@example.com")
    admin = await app.admin()
    mine = await app.ok(
        "connections.add_variable", owner, name="region", description="Where.", value="ca"
    )
    for ref in ("region", mine["id"]):
        assert (await app.call("connections.show", other, connection=ref)).status_code == 404
        refused = await app.call("connections.change_variable", other, connection=ref, value="us")
        assert refused.status_code == 404
    assert [item["name"] for item in (await app.ok("connections.list", other))["items"]] == []

    refused = await app.call(
        "connections.add_secret", owner, name="search", description="Search.", value=VALUE,
        sites=["api.search.example"], scope="install",
    )  # fmt: skip
    assert_refused(refused, rule="CON-1", code="admin_only")
    await app.ok(
        "connections.add_secret", admin, name="search", description="Search key.", value=VALUE,
        sites=["api.search.example"], scope="install",
    )  # fmt: skip
    assert "search" in [item["name"] for item in (await app.ok("connections.list", other))["items"]]
    refused = await app.call("connections.replace_secret", other, connection="search", value=SECOND)
    assert_refused(refused, rule="CON-1", code="not_yours")
    refused = await app.call("connections.delete", other, connection="search")
    assert_refused(refused, rule="CON-1", code="not_yours")

    project = await app.project(owner)
    outsider = await app.call(
        "connections.add_variable", other, name="site", description="Site.", value="x",
        scope="project", project_id=project,
    )  # fmt: skip
    assert outsider.status_code == 404
    taken = await app.call(
        "connections.add_variable", owner, name="REGION", description="Again.", value="us"
    )
    assert_refused(taken, rule="CON-1", code="connection_exists")


@pytest.mark.attack("CON-4")
async def test_CON_4_a_project_gets_only_what_is_attached_and_granted_without_collisions(
    app: App,
) -> None:
    """CON-4, CON-5: the roles that declared a need are granted by default; with no need,
    the chairman chooses; a role not on the roster, another project's item and someone
    else's item are refused; two items giving the same variable to a role are refused,
    naming both."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    other_project = await app.project(owner, name="Other")
    stranger = await app.person("stranger@example.com")

    added = await app.ok(
        "connections.add_secret", owner, name="WordPress", description="WordPress password.",
        value=VALUE, sites=["example.com"], project_id=project,
    )  # fmt: skip
    view = await app.ok("connections.for_project", owner, project_id=project)
    [attached] = view["attached"]
    assert attached["item"]["id"] == added["id"]
    assert attached["roles"] == [view["needs"][0]["roles"][0]]
    assert [(need["name"], need["state"]) for need in view["needs"]] == [("wordpress", "met")]
    assert (await app.ok("projects.readiness", owner, project_id=project))["ready"] is True

    unneeded = await app.call(
        "connections.add_variable", owner, name="tone", description="House tone.",
        value="warm", project_id=project,
    )  # fmt: skip
    assert_refused(unneeded, rule="CON-4", code="roles_required")
    await app.ok(
        "connections.add_variable", owner, name="tone", description="House tone.", value="warm"
    )
    wrong_role = await app.call(
        "connections.attach", owner, project_id=project, connection="tone", roles=["pilot"]
    )
    assert_refused(wrong_role, rule="CON-4", code="role_not_on_roster")
    await app.ok("connections.attach", owner, project_id=project, connection="tone", roles=["*"])

    local = await app.ok(
        "connections.add_variable", owner, name="brand", description="Brand.", value="blue",
        scope="project", project_id=other_project, roles=["*"],
    )  # fmt: skip
    foreign = await app.call(
        "connections.attach", owner, project_id=project, connection=local["id"]
    )
    assert_refused(foreign, rule="CON-4", code="connection_of_another_project")
    theirs = await app.ok(
        "connections.add_variable", stranger, name="theirs", description="Theirs.", value="x"
    )
    hidden = await app.call(
        "connections.attach", owner, project_id=project, connection=theirs["id"], roles=["*"]
    )
    assert hidden.status_code == 404

    clash = await app.call(
        "connections.add_secret", owner, name="tone-key", description="Tone key.", value=VALUE,
        delivery="given", env_name="TONE", project_id=project, roles=["*"],
    )  # fmt: skip
    envelope = assert_refused(clash, rule="CON-4", code="connection_collision")
    assert "tone-key" in envelope.message
    assert "tone" in envelope.message
    site_clash = await app.call(
        "connections.add_secret", owner, name="wp-two", description="Another.", value=VALUE,
        sites=["example.com"], project_id=project, roles=["*"],
    )  # fmt: skip
    assert_refused(site_clash, rule="CON-4", code="connection_collision")


@pytest.mark.attack("CON-5")
async def test_CON_5_attaching_lifts_the_hold_and_detaching_brings_it_back(app: App) -> None:
    """CON-5, CON-14, EXE-4: a started project's held seat goes to work as soon as what it
    needs is attached; detaching or deleting holds it again, with the reason."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    await app.ok("projects.start", owner, project_id=project, without_missing=True)
    assert (await writer_of(app, project)).state == "paused"

    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=VALUE, sites=["example.com"], project_id=project,
    )  # fmt: skip
    released = await writer_of(app, project)
    assert (released.state, released.held_for) == ("active", [])
    await app.ok("connections.detach", owner, project_id=project, connection="wordpress")
    held = await writer_of(app, project)
    assert (held.state, held.held_for) == ("paused", ["secret:wordpress"])
    await app.ok("connections.attach", owner, project_id=project, connection="wordpress")
    assert (await writer_of(app, project)).state == "active"
    await app.ok("connections.delete", owner, connection="wordpress")
    assert (await writer_of(app, project)).state == "paused"


RESERVED = (
    "PATH",
    "HTTPS_PROXY",
    "no_proxy",
    "LD_PRELOAD",
    "CREWMIND_TOKEN",
    "PYTHONPATH",
    "NODE_OPTIONS",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
)


@pytest.mark.attack("CON-3")
@pytest.mark.attack("CON-7")
async def test_CON_7_a_name_that_changes_how_programs_run_is_refused(app: App) -> None:
    """CON-3, CON-7: a variable is shown with its value; no variable or given secret may
    take a name that changes how programs run, or a malformed one."""
    owner = await app.person("owner@example.com")
    shown = await app.ok(
        "connections.add_variable", owner, name="region", description="Where.", value="ca-east"
    )
    assert (shown["value"], shown["env_name"]) == ("ca-east", "REGION")
    for env in RESERVED:
        refused = await app.call(
            "connections.add_variable", owner, name="x", description="X.", value="1", env_name=env
        )
        assert_refused(refused, rule="CON-7", code="env_name_reserved")
        refused = await app.call(
            "connections.add_secret", owner, name="y", description="Y.", value=VALUE,
            delivery="given", env_name=env,
        )  # fmt: skip
        assert_refused(refused, rule="CON-7", code="env_name_reserved")
    for env in ("1ABC", "A-B", "A B"):
        refused = await app.call(
            "connections.add_variable", owner, name="x", description="X.", value="1", env_name=env
        )
        assert_refused(refused, rule="CON-7", code="env_name_invalid")
    for name in ("1abc", "a b", "a/b", ""):
        refused = await app.call(
            "connections.add_variable", owner, name=name, description="X.", value="1"
        )
        assert refused.status_code in (403, 422)


@pytest.mark.attack("CON-2")
async def test_CON_2_a_pasted_env_is_reviewed_without_values_and_saved_whole(app: App) -> None:
    """CON-2: the review shows names, kinds and problems, never a value; saving with a
    problem left is refused and saves nothing; skipped lines are left out; secrets are
    given to the agent under their own name."""
    owner = await app.person("owner@example.com")
    text = "\n".join(
        [
            "# comment",
            f"export OPENAI_API_KEY='{VALUE}'",
            "REGION=ca-east  # inline comment",
            "DB_PASSWORD=short",
            "not a line",
            'GREETING="hello\\nthere"',
        ]
    )
    review = await app.ok("connections.review_env", owner, text=text)
    rows = {row["name"]: row for row in review["lines"]}
    assert (rows["OPENAI_API_KEY"]["kind"], rows["OPENAI_API_KEY"]["problem"]) == ("secret", None)
    assert rows["REGION"]["kind"] == "variable"
    assert rows["DB_PASSWORD"]["problem"]
    assert rows["not a line"]["problem"] == "not KEY=value"
    assert review["saved"] == 0
    assert VALUE not in json.dumps(review)
    assert "ca-east" not in json.dumps(review)

    refused = await app.call("connections.import_env", owner, text=text)
    assert_refused(refused, rule="CON-2", code="import_has_problems")
    assert (await app.ok("connections.list", owner))["items"] == []
    saved = await app.ok(
        "connections.import_env", owner, text=text,
        skip=["DB_PASSWORD", "not a line"], variables=["GREETING"],
    )  # fmt: skip
    assert saved["saved"] == 3
    items = {item["name"]: item for item in (await app.ok("connections.list", owner))["items"]}
    assert (items["OPENAI_API_KEY"]["delivery"], items["OPENAI_API_KEY"]["env_name"]) == (
        "given",
        "OPENAI_API_KEY",
    )
    assert items["REGION"]["value"] == "ca-east"
    assert items["GREETING"]["value"] == "hello\nthere"
    assert VALUE not in json.dumps(items)


@pytest.mark.attack("7.18-connection")
async def test_7_18_a_secret_warns_then_expires_and_its_seats_wait(
    app: App, clock: FakeClock
) -> None:
    """7.18, CON-2, CON-14: the chairman is told before and on the day; the day after, the
    secret expires, its need is open and its seats wait; a new value brings it back."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    soon = (clock() + timedelta(days=3)).date()
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=VALUE, sites=["example.com"], project_id=project, expires_on=soon.isoformat(),
    )  # fmt: skip
    await app.ok("projects.start", owner, project_id=project)

    async def tick() -> list[str]:
        async with app.runtime.sessions() as session, session.begin():
            await expiry.check(session, app.runtime.services.settings, clock())
        async with app.runtime.sessions() as session:
            return list(await session.scalars(select(Alarm.body).order_by(Alarm.id)))

    assert any("expires on" in body for body in await tick())
    assert len(await tick()) == 1
    clock.advance(days=3)
    assert any("end of today" in body for body in await tick())
    clock.advance(days=1)
    assert any("has expired" in body for body in await tick())
    owner = await app.login(owner.email, owner.person_id)
    assert (await writer_of(app, project)).state == "paused"
    [need] = (await app.ok("connections.for_project", owner, project_id=project))["needs"]
    assert need["state"] == "open"
    await app.ok("connections.replace_secret", owner, connection="wordpress", value=SECOND)
    assert (await writer_of(app, project)).state == "active"
    shown = await app.ok("connections.show", owner, connection="wordpress")
    assert shown["item"]["state"] == "active"


VALUE_VERBS = (
    "connections.add_secret",
    "connections.review_env",
    "connections.replace_secret",
    "connections.import_env",
    "connections.change_secret",
    "connections.delete",
)


@pytest.mark.attack("IF-5.6")
@pytest.mark.attack("CON-2")
async def test_IF_5_6_a_model_client_sees_names_and_never_sets_a_value(app: App) -> None:
    """IF-5.6, CON-15: even a configure client cannot add or replace a value, import, change
    where a secret is sent, or delete; it lists names and kinds, never a value."""
    owner = await app.person("owner@example.com")
    project = await blog_project(app, owner)
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=VALUE, sites=["example.com"], project_id=project,
    )  # fmt: skip
    minted = await app.ok(
        "mcp_clients.mint", owner, client_name="Helper", scopes=["configure", "steer", "create"]
    )
    caller = await mcp_caller(app, minted["token"])
    async with client_for(app, caller) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
        for name in VALUE_VERBS:
            assert tool_name(name) not in listed
            assert catalog.get(name).mcp_scope is None
            result = await client.call_tool(tool_name(name), {"connection": "wordpress"})
            assert result.structured_content is not None
            assert result.structured_content["code"] == "unknown_tool"
        assert tool_name("connections.attach") in listed
        seen = await client.call_tool("connections_for_project", {"project_id": project})
        assert seen.structured_content is not None
        assert seen.structured_content["attached"][0]["item"]["name"] == "wordpress"
        assert VALUE not in json.dumps(seen.structured_content)


@given(path=st.lists(st.sampled_from(sorted(CONNECTION_MACHINE.states - {"(new)"})), max_size=10))
def test_7_18_a_connection_moves_only_by_listed_transitions(path: list[str]) -> None:
    """7.18: deleted is final; every other move follows the table or is refused."""
    state = "active"
    for target in path:
        if target == state:
            continue
        if CONNECTION_MACHINE.allows(state, target):
            assert state != "deleted"
            state = target
        else:
            with pytest.raises(Refusal):
                CONNECTION_MACHINE.check(state, target)
