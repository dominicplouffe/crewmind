"""Attacks on settings (GOV-1, Appendix A)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.attack.harness import assert_refused
from tests.support import App

REASON = "The team asked for more parallel work."


@pytest.mark.attack("GOV-1")
@pytest.mark.parametrize(
    ("changes", "reason", "code"),
    [
        ({"run.concurrency": 6}, "too short", "reason_required"),
        ({"run.concurrency": 6}, "          ", "reason_required"),
        ({"run.concurency": 6}, REASON, "unknown_setting"),
        ({"run.concurrency": 17}, REASON, "value_out_of_range"),
        ({"run.concurrency": "six"}, REASON, "value_out_of_range"),
        ({"budget.warn_at": 95, "budget.wrapup_at": 60}, REASON, "constraint_broken"),
        ({"budget.warn_at": 95}, REASON, "constraint_broken"),
        ({"authority.verdict": "ceo"}, REASON, "value_out_of_range"),
        ({"authority.preset": "custom"}, REASON, "preset_custom"),
        ({"authority.preset": "supervised", "authority.date": "ceo"}, REASON, "preset_conflict"),
        ({"cycle.period": "daily"}, REASON, "setting_not_applicable"),
        ({"chat.brevity": "short"}, REASON, "setting_not_applicable"),
        ({"delete.grace": 86_400}, REASON, "setting_not_applicable"),
        ({}, REASON, "no_changes"),
    ],
)
async def test_GOV_1_a_bad_change_is_refused_and_changes_nothing(
    app: App, changes: dict[str, Any], reason: str, code: str
) -> None:
    """GOV-1, Appendix A: a missing or short reason, an unknown name, a value out of range,
    a broken constraint and a setting of another scope or project type are each refused.
    A refused bundle changes nothing, even its valid parts."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner, type="deliver")
    before = await app.ok("settings.show_project", owner, project_id=project)
    bundle = {"quality": "best", **changes} if changes else changes
    refused = await app.call(
        "settings.change_project", owner, project_id=project, changes=bundle, reason=reason
    )
    assert_refused(refused, rule="GOV-1", code=code)
    assert await app.ok("settings.show_project", owner, project_id=project) == before
    history = await app.ok("settings.history_project", owner, project_id=project)
    assert [item["name"] for item in history["items"]] == ["project.timezone"]


@pytest.mark.attack("GOV-1")
async def test_GOV_1_an_unknown_setting_names_the_closest_real_one(app: App) -> None:
    """GOV-1: the refusal names the closest real setting."""
    owner = await app.person("owner@example.com")
    project = await app.project(owner)
    refused = await app.call(
        "settings.change_project",
        owner,
        project_id=project,
        changes={"budget.token": 5_000_000},
        reason=REASON,
    )
    assert "budget.tokens" in assert_refused(refused, rule="GOV-1").message


@pytest.mark.attack("GOV-1")
async def test_GOV_1_only_the_right_person_changes_each_scope(app: App) -> None:
    """GOV-1: project settings need the chairman or a co-chair; install settings need an
    admin and a reason; a person changes only their own preferences."""
    admin = await app.admin()
    owner = await app.person("owner@example.com")
    observer = await app.person("observer@example.com")
    project = await app.project(owner)
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")

    as_observer = await app.call(
        "settings.change_project",
        observer,
        project_id=project,
        changes={"run.concurrency": 6},
        reason=REASON,
    )
    assert_refused(as_observer, rule="ACC-5", code="role_required")
    as_member = await app.call(
        "settings.change_install", owner, changes={"delete.grace": 86_400}, reason=REASON
    )
    assert_refused(as_member, rule="IF-3.2", code="admin_only")
    no_reason = await app.call(
        "settings.change_install", admin, changes={"delete.grace": 86_400}, reason="short"
    )
    assert_refused(no_reason, rule="GOV-1", code="reason_required")
    wrong_scope = await app.call("settings.change_mine", owner, changes={"run.concurrency": 6})
    assert_refused(wrong_scope, rule="GOV-1", code="setting_not_applicable")

    await app.ok("settings.change_mine", owner, changes={"chat.brevity": "short"})
    mine = await app.ok("settings.show_mine", observer)
    assert next(i for i in mine["items"] if i["name"] == "chat.brevity")["value"] == "normal"
