"""Attacks on project specs: import, export and clone (LIB-4, LIB-5, PRJ-9, INV-6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightsquad.domain.secrets.store import ensure_master_key
from tests.attack.harness import assert_refused
from tests.support import App

SPEC: dict[str, Any] = {
    "name": "Atlas",
    "goal": "Publish a road atlas a driver can use without a phone.",
    "type": "deliver",
    "deadline": {"date": "2027-03-01T00:00:00Z", "source": "The print slot is booked."},
    "budget_tokens": 5_000_000,
    "quality": "best",
    "paying_credential": "main",
    "settings": {"run.concurrency": 6},
    "ceo": {"role": "ceo"},
    "teams": [
        {"name": "Maps", "role": "researcher", "members": ["Rey", "Sol"]},
        {"name": "Checks", "role": "fact-checker", "members": ["Fay"]},
    ],
    "standing_orders": ["Every distance is in kilometres."],
    "controlled_domains": ["atlas.example.com"],
    "integrations": ["email"],
    "roles": [
        {
            "slug": "fact-checker",
            "name": "Fact checker",
            "kind": "reviewer",
            "category": "review",
            "description": "Checks every claim against its source.",
            "tools": ["files", "web"],
            "charter": "Check each claim against its source and say which do not hold.",
        }
    ],
    "credentials": [{"name": "maps-api", "roles": ["researcher"]}],
}
KEY = "sk-test-0123456789abcdef"


@pytest.mark.attack("LIB-4")
async def test_LIB_4_a_spec_never_holds_or_yields_a_secret(app: App) -> None:
    """LIB-4, INV-6, PRJ-9: a spec that carries a credential value is refused, whoever
    wrote it. An export and a clone name the paying credential and never hold its value,
    and a spec that names a credential the person lacks creates the project and says so.
    A secret its roles need is listed as what the squad waits for (CON-5)."""
    owner = await app.person("owner@example.com")
    smuggling: list[dict[str, Any]] = [
        {**SPEC, "credentials": [{"name": "maps-api", "roles": [], "value": KEY}]},
        {**SPEC, "credentials": [{"name": "maps-api", "key": KEY}]},
        {**SPEC, "api_key": KEY},
    ]
    for smuggled in smuggling:
        refused = await app.call("projects.import_spec", owner, **smuggled)
        assert_refused(refused, rule="LIB-4", code="spec_holds_a_secret")

    created = await app.ok("projects.import_spec", owner, **SPEC)
    assert created["state"] == "draft"
    assert any("no credential named main" in line for line in created["missing"])
    # A role's secret is a need of the project: who waits for it is listed (CON-5).
    assert any("maps-api" in line and "researcher" in line for line in created["waiting"])
    assert any("email" in line for line in created["missing"])

    ensure_master_key(app.runtime.config.master_key_file)
    await app.ok("credentials.add", owner, name="main", provider="mock", key=KEY)
    project = created["project_id"]
    await app.ok("models.set_payer", owner, project_id=project, credential="main")
    exported = await app.ok("projects.export", owner, project_id=project)
    assert exported["paying_credential"] == "main"
    assert KEY not in json.dumps(exported)
    cloned = await app.ok("projects.clone", owner, project_id=project, name="Atlas two")
    assert not [line for line in cloned["missing"] if "main" in line]
    again = await app.ok("projects.export", owner, project_id=cloned["project_id"])
    assert KEY not in json.dumps(again)
    assert {**again, "name": "Atlas"} == exported


@pytest.mark.attack("LIB-4")
async def test_LIB_5_a_spec_goes_round_and_a_bad_one_creates_nothing(app: App) -> None:
    """LIB-4, LIB-5, PRJ-9: what a spec says is what the project has (goal, settings,
    target date, roster with named members and pinned role versions, standing orders,
    controlled domains), and exporting it gives the spec back. A spec with a problem is
    refused whole: no project, no role, nothing. A clone has no history."""
    owner = await app.person("owner@example.com")
    before = len((await app.ok("projects.list", owner))["items"])
    for broken, said in (
        ({**SPEC, "teams": [{"name": "Maps", "role": "nobody", "members": ["Rey"]}]}, "nobody"),
        ({**SPEC, "ceo": {"role": "researcher"}}, "can be the CEO"),
        ({**SPEC, "settings": {"run.concurency": 6}}, "run.concurency"),
        ({**SPEC, "settings": {"run.concurrency": 99}}, ""),
        ({**SPEC, "standing_orders": ["Every distance is in kilometres."] * 26}, ""),
    ):
        refused = await app.call("projects.import_spec", owner, **broken)
        assert refused.status_code in (403, 422), refused.text
        assert said in refused.text
    assert len((await app.ok("projects.list", owner))["items"]) == before
    roles = {role["slug"] for role in (await app.ok("roles.list", owner))["items"]}
    assert "fact-checker" not in roles
    checked = await app.ok("specs.check", owner, **{**SPEC, "ceo": {"role": "researcher"}})
    assert (checked["ok"], len(checked["problems"])) == (False, 1)

    created = await app.ok("projects.import_spec", owner, **SPEC)
    project = created["project_id"]
    roster = await app.ok("roster.show", owner, project_id=project)
    seats = {seat["name"]: seat for seat in roster["seats"]}
    assert {"CEO", "Rey", "Sol", "Fay"} <= set(seats)
    assert (seats["Rey"]["lead"], seats["Sol"]["lead"]) == (True, False)
    settings = await app.ok("settings.show_project", owner, project_id=project)
    values = {entry["name"]: entry["value"] for entry in settings["items"]}
    assert (values["budget.tokens"], values["quality"], values["run.concurrency"]) == (
        5_000_000,
        "best",
        6,
    )
    orders = (await app.ok("orders.list", owner, project_id=project))["items"]
    assert [(order["text"], order["state"]) for order in orders] == [
        ("Every distance is in kilometres.", "active")
    ]
    exported = await app.ok("projects.export", owner, project_id=project)
    sent: dict[str, Any] = {**SPEC, "paying_credential": None}
    for key, value in sent.items():
        if key == "teams":
            got = sorted(exported["teams"], key=lambda team: team["name"], reverse=True)
            assert [team["version"] for team in got] == [1, 1]
            assert [{**team, "version": 1, "stand_down_when": None} for team in value] == got
        elif key == "roles":
            assert exported["roles"][0]["charter"] == value[0]["charter"]
        elif key == "settings":
            assert exported["settings"]["run.concurrency"] == 6
        elif key == "deadline":
            assert exported["deadline"]["source"] == value["source"]
        elif key == "credentials":
            assert exported[key] == [{"kind": "secret", **grant} for grant in value]
        else:
            assert exported[key] == value, key

    cloned = await app.ok("projects.clone", owner, project_id=project, name="Atlas two")
    events = await app.events(owner, cloned["project_id"])
    assert events[0]["type"] == "project.created"
    assert not [event for event in events if event["type"].startswith(("run.", "task."))]
    history = await app.ok("chat.history", owner, project_id=cloned["project_id"])
    assert all(line["author_kind"] != "person" for line in history["items"])
    stranger = await app.person("stranger@example.com")
    assert (await app.call("projects.export", stranger, project_id=project)).status_code in (
        403,
        404,
    )
    assert (
        await app.call("projects.clone", stranger, project_id=project, name="Mine now")
    ).status_code in (403, 404)


EXAMPLES = Path(__file__).parents[2] / "content" / "examples"


async def test_LIB_5_every_shipped_example_is_a_spec_that_creates_a_project(app: App) -> None:
    """LIB-4, LIB-5: each example project in `content/examples` is in the one format,
    names only roles the library has, and creates a draft project."""
    owner = await app.person("owner@example.com")
    files = sorted(EXAMPLES.glob("*.json"))
    assert len(files) >= 12
    for file in files:
        spec = json.loads(file.read_text(encoding="utf-8"))
        checked = await app.ok("specs.check", owner, **spec)
        assert checked["ok"], f"{file.name}: {checked['problems']}"
        created = await app.ok("projects.import_spec", owner, **spec)
        assert (created["state"], created["type"]) == ("draft", spec["type"]), file.name
