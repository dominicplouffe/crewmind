"""The settings service: defaults, versions and scopes (GOV-1, Appendix A, section 3)."""

from __future__ import annotations

from typing import Any

from crewmind.domain.settings.service import CONSTRAINTS
from crewmind.services import Services
from tests.support import App

REASON = "A reason long enough to count."


def value(view: dict[str, Any], name: str) -> Any:
    return next(item for item in view["items"] if item["name"] == name)["value"]


async def test_appendix_A_defaults_follow_the_project_type(app: App) -> None:
    """Appendix A, GOV-2: each project type has its own budget default, and a setting that
    belongs to another type does not exist on the project."""
    owner = await app.person("owner@example.com")
    expected = {"deliver": 20_000_000, "explore": 10_000_000, "operate": 40_000_000}
    project = ""
    for project_type, tokens in expected.items():
        project = await app.project(owner, type=project_type)
        view = await app.ok("settings.show_project", owner, project_id=project)
        names = {item["name"] for item in view["items"]}
        assert value(view, "budget.tokens") == tokens
        assert value(view, "run.concurrency") == 4
        assert ("cycle.period" in names) == (project_type == "operate")
        assert ("evidence.min_share" in names) == (project_type == "explore")
        assert "chat.brevity" not in names
        assert "delete.grace" not in names
    operate = await app.ok("settings.show_project", owner, project_id=project)
    assert value(operate, "cycle.roll_day") == 0
    monthly = await app.ok(
        "settings.change_project",
        owner,
        project_id=project,
        changes={"cycle.period": "monthly"},
        reason=REASON,
    )
    assert value(monthly, "cycle.roll_day") == 1


async def test_GOV_1_changes_are_versioned_with_their_reason_and_author(app: App) -> None:
    """GOV-1: every change is a new version, kept with who made it and why, and takes
    effect at once. A bundle applies together."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    for concurrency in (6, 8):
        view = await app.ok(
            "settings.change_project",
            owner,
            project_id=project,
            changes={"run.concurrency": concurrency, "quality": "best"},
            reason=f"{REASON} ({concurrency})",
        )
        assert value(view, "run.concurrency") == concurrency
    history = (await app.ok("settings.history_project", owner, project_id=project))["items"]
    concurrency_history = [item for item in history if item["name"] == "run.concurrency"]
    assert [(item["version"], item["value"]) for item in concurrency_history] == [(1, 6), (2, 8)]
    assert concurrency_history[1]["reason"] == f"{REASON} (8)"
    assert concurrency_history[1]["changed_by"] == owner.person_id
    assert [item["version"] for item in history if item["name"] == "quality"] == [1, 2]


async def test_section_3_a_preset_writes_all_six_verbs_and_a_verb_change_makes_it_custom(
    app: App,
) -> None:
    """Section 3, Appendix A: choosing a preset sets the six authority verbs in one change;
    changing one verb alone turns the preset to custom; restoring it turns it back."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    view = await app.ok("settings.show_project", owner, project_id=project)
    assert value(view, "authority.preset") == "autonomous"
    assert value(view, "authority.verdict") == "reviewer"

    async def change(changes: dict[str, str]) -> dict[str, Any]:
        return await app.ok(
            "settings.change_project", owner, project_id=project, changes=changes, reason=REASON
        )

    supervised = await change({"authority.preset": "supervised"})
    verbs = {
        i["name"]: i["value"] for i in supervised["items"] if i["name"].startswith("authority.")
    }
    assert set(verbs.values()) == {"supervised", "chairman"}
    assert value(await change({"authority.date": "ceo"}), "authority.preset") == "custom"
    assert value(await change({"authority.date": "chairman"}), "authority.preset") == "supervised"


async def test_GOV_1_person_and_install_scopes(app: App) -> None:
    """GOV-1: a person changes their own preferences with no reason; an admin changes
    install settings with one. Both are audited in the install event log."""
    admin = await app.admin()
    alice = await app.person("alice@example.com")
    mine = await app.ok("settings.change_mine", alice, changes={"person.timezone": "Europe/Paris"})
    assert value(mine, "person.timezone") == "Europe/Paris"
    project = await app.project(alice)
    project_view = await app.ok("settings.show_project", alice, project_id=project)
    assert value(project_view, "project.timezone") == "Europe/Paris"

    install = await app.ok(
        "settings.change_install", admin, changes={"delete.grace": 172_800}, reason=REASON
    )
    assert value(install, "delete.grace") == 172_800
    record = await app.ok("record.list_install", admin, type="setting.changed")
    scopes = [(e["detail"]["scope"], e["actor"], e["detail"]["reason"]) for e in record["items"]]
    assert ("person", alice.person_id, None) in scopes
    assert ("install", admin.person_id, REASON) in scopes


async def test_appendix_A_every_constraint_is_implemented_and_listed(app: App) -> None:
    """Appendix A: each constraint in the registry has a check, and the registry operation
    serves the same definitions the spec lists."""
    services = app.runtime.services
    assert isinstance(services, Services)
    assert {c.id for c in services.registry.constraints} == set(CONSTRAINTS)
    alice = await app.person("alice@example.com")
    registry = await app.ok("settings.registry", alice)
    assert len(registry["settings"]) == len(services.registry.settings)
    assert registry["version"] == services.registry.version
    assert len(registry["constraints"]) == 4
