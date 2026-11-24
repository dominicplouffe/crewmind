"""The settings registry matches Appendix A and validates values (Appendix A, GOV-1, NFR-7)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nightsquad.domain.settings.registry import (
    Scope,
    Setting,
    SettingValueError,
    UnknownSettingError,
    load_registry,
)

APPENDIX_A = Path(__file__).parents[2] / "docs" / "spec" / "appendix-a-settings.md"
REGISTRY = load_registry()
RANGED = [s for s in REGISTRY.settings.values() if s.is_whole_number]


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split(" | ")]


def _appendix_a() -> tuple[dict[str, list[str]], list[str], dict[str, list[str]]]:
    """The settings table, the constraints list and the operational table, as written."""
    settings: dict[str, list[str]] = {}
    constraints: list[str] = []
    operational: dict[str, list[str]] = {}
    section = "settings"
    for line in APPENDIX_A.read_text(encoding="utf-8").splitlines():
        if line.startswith("### Constraints"):
            section = "constraints"
        elif line.startswith("### Operational"):
            section = "operational"
        elif section == "constraints" and line.startswith("- "):
            constraints.append(line[2:])
        elif match := re.match(r"\| `([^`]+)` \|", line):
            (settings if section == "settings" else operational)[match.group(1)] = _cells(line)[1:]
    return settings, constraints, operational


def test_appendix_A_every_setting_matches_the_spec() -> None:
    """Appendix A: names, defaults, ranges, scopes and "Used by" equal the spec, in order."""
    spec, _, _ = _appendix_a()
    assert list(REGISTRY.settings) == list(spec)
    for name, (default, allowed, scope, used_by) in spec.items():
        setting = REGISTRY.settings[name]
        assert (setting.spec_default, setting.spec_range) == (default, allowed), name
        assert setting.scope == Scope(scope), name
        assert ", ".join(setting.used_by) == used_by, name


def test_appendix_A_constraints_match_the_spec() -> None:
    """Appendix A, GOV-1: the constraints are the spec's, and name real settings."""
    _, spec, _ = _appendix_a()
    assert [constraint.spec for constraint in REGISTRY.constraints] == spec
    for constraint in REGISTRY.constraints:
        assert set(constraint.settings) <= set(REGISTRY.settings), constraint.id


def test_NFR_7_operational_settings_match_the_spec() -> None:
    """NFR-7, Appendix A: every environment variable equals the spec's operational table."""
    _, _, spec = _appendix_a()
    assert list(REGISTRY.operational) == list(spec)
    for name, (default, allowed, used_by) in spec.items():
        variable = REGISTRY.operational[name]
        assert (variable.spec_default, variable.spec_range) == (default, allowed), name
        assert ", ".join(variable.used_by) == used_by, name


def test_appendix_A_every_default_is_allowed() -> None:
    """Appendix A: each default, including per-type defaults, passes its own validation."""
    for definition in (*REGISTRY.settings.values(), *REGISTRY.operational.values()):
        if definition.default is not None:
            assert definition.validate_value(definition.default) == definition.default
        if definition.default_by is not None:
            for value in definition.default_by.values.values():
                definition.validate_value(value)
        assert (
            definition.default is not None
            or definition.default_by is not None
            or definition.default_from is not None
            or not isinstance(definition, Setting)
        ), f"{definition.name} has no default"


@given(data=st.data())
def test_appendix_A_values_inside_the_range_are_accepted(data: st.DataObject) -> None:
    """Appendix A: any whole number inside a setting's range is accepted."""
    setting = data.draw(st.sampled_from(RANGED))
    low = int(setting.min) if setting.min is not None else 0
    high = int(setting.max) if setting.max is not None else low + 10**12
    value = data.draw(st.integers(low, high))
    assert setting.validate_value(value) == value


@given(data=st.data())
def test_appendix_A_values_outside_the_range_are_refused(data: st.DataObject) -> None:
    """Appendix A: a value below the minimum or above the maximum is refused, naming the range."""
    setting = data.draw(st.sampled_from(RANGED))
    choices: list[st.SearchStrategy[int]] = []
    if setting.min is not None:
        below = st.integers(max_value=int(setting.min) - 1)
        choices.append(below.filter(lambda v: v != 0) if setting.zero_means_off else below)
    if setting.max is not None:
        choices.append(st.integers(min_value=int(setting.max) + 1))
    value = data.draw(st.one_of(choices))
    with pytest.raises(SettingValueError, match=re.escape(setting.spec_range)):
        setting.validate_value(value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("quality", "superb"),
        ("review.independent", "yes"),
        ("run.concurrency", True),
        ("run.concurrency", 2.5),
        ("brief.time", "25:00"),
        ("spend.currency", "dollars"),
        ("otel.endpoint", "collector:4317"),
        ("project.timezone", "Mars/Olympus"),
        ("authority.verdict", "ceo"),
    ],
)
def test_appendix_A_wrong_values_are_refused(name: str, value: object) -> None:
    """Appendix A, P5: values of the wrong type or outside the choices are refused. The
    verdict verb can never be given to the CEO."""
    with pytest.raises(SettingValueError):
        REGISTRY.get(name).validate_value(value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("run.max_tokens", 0),
        ("correction.ttl", "forever"),
        ("report.cadence", "off"),
        ("brief.time", "off"),
        ("otel.endpoint", "https://collector.example:4318"),
        ("project.timezone", "America/Toronto"),
        ("spend.monthly_cap", 250.5),
    ],
)
def test_appendix_A_special_values_are_accepted(name: str, value: object) -> None:
    """Appendix A: off, forever and zero-means-off are allowed where the spec says so."""
    assert REGISTRY.get(name).validate_value(value) == value


def test_GOV_1_an_unknown_setting_names_the_closest_real_one() -> None:
    """GOV-1: an unknown setting name is refused, naming the closest real one."""
    with pytest.raises(UnknownSettingError) as refused:
        REGISTRY.get("budget.token")
    assert refused.value.closest == "budget.tokens"
    assert "budget.tokens" in str(refused.value)
