"""The declared state machines equal section 7 of the spec, and hold their invariants."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.state_machine import NEW, StateMachine
from crewmind.domain.accounts.model import (
    LINK_MACHINE,
    MEMBERSHIP_MACHINE,
    PERSON_MACHINE,
    SESSION_MACHINE,
    TOKEN_MACHINE,
)
from crewmind.domain.conversation.corrections import CORRECTION_MACHINE
from crewmind.domain.conversation.decisions import DECISION_MACHINE
from crewmind.domain.conversation.directives import CARD_MACHINE, DIRECTIVE_MACHINE
from crewmind.domain.conversation.orders import ORDER_MACHINE
from crewmind.domain.conversation.sessions import CHAT_SESSION_MACHINE
from crewmind.domain.execution.model import RUN_MACHINE, SEAT_MACHINE, TEAM_MACHINE
from crewmind.domain.models.service import BREAKER_MACHINE, CREDENTIAL_MACHINE
from crewmind.domain.projects.model import (
    HOLDABLE,
    PLATFORM_HOLDS,
    PROJECT_MACHINE,
    Hold,
    ProjectState,
    state_under,
)
from crewmind.domain.work.model import (
    EFFECT_MACHINE,
    EVIDENCE_MACHINE,
    TASK_MACHINE,
    WATCH_MACHINE,
)

SECTION_7 = Path(__file__).parents[2] / "docs" / "spec" / "07-state-machines.md"
PRIOR_STATES = ("draft", "stopped", "completed")
NOTHING: set[tuple[str, str]] = set()


def spec_tables() -> dict[str, list[tuple[str, str]]]:
    """Every From/To table in section 7, keyed by its heading, as written."""
    tables: dict[str, list[tuple[str, str]]] = {}
    heading = ""
    for line in SECTION_7.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            heading = line[4:].split(" ")[0]
        elif match := re.match(r"\*\*(.+?)\*\*", line):
            heading = f"{heading.split(':')[0]}:{match.group(1)}"
        elif line.startswith("| ") and not line.startswith(
            ("| From", "| ---", "| Hold", "| State")
        ):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 4:
                tables.setdefault(heading, []).append((cells[0], cells[1]))
    return tables


def expand(rows: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Spec rows as single transitions: lists are split and `(new)` kept as written."""
    pairs: set[tuple[str, str]] = set()
    for sources, targets in rows:
        for source in re.split(r",\s*| or ", sources):
            for target in re.split(r",\s*| or ", targets):
                target = re.sub(r" \(.*\)$", "", target)
                if target == "its prior state":
                    pairs.update((source, prior) for prior in PRIOR_STATES)
                elif source != target:
                    pairs.add((source, target))
    return pairs


def declared(machine: StateMachine) -> set[tuple[str, str]]:
    return {(str(t.source), str(t.target)) for t in machine.transitions}


@pytest.mark.parametrize(
    ("heading", "machine", "extra"),
    [
        ("7.1", PROJECT_MACHINE, {(NEW, "draft")}),
        ("7.8", PERSON_MACHINE, NOTHING),
        ("7.9", LINK_MACHINE, NOTHING),
        ("7.10:Browser session", SESSION_MACHINE, NOTHING),
        ("7.10:Personal token and MCP client token", TOKEN_MACHINE, NOTHING),
        ("7.11", MEMBERSHIP_MACHINE, NOTHING),
        ("7.7", RUN_MACHINE, NOTHING),
        ("7.12:Team:", TEAM_MACHINE, NOTHING),
        ("7.12:Seat:", SEAT_MACHINE, NOTHING),
        ("7.17:Directive", DIRECTIVE_MACHINE, NOTHING),
        ("7.17:Action card", CARD_MACHINE, NOTHING),
        ("7.17:Standing order", ORDER_MACHINE, NOTHING),
        ("7.17:Closed decision", DECISION_MACHINE, NOTHING),
        ("7.17:Correction", CORRECTION_MACHINE, NOTHING),
        ("7.17:Chat session", CHAT_SESSION_MACHINE, NOTHING),
        ("7.3", TASK_MACHINE, NOTHING),
        ("7.15", EVIDENCE_MACHINE, NOTHING),
        ("7.16:Side effect:", EFFECT_MACHINE, NOTHING),
        ("7.16:Watch:", WATCH_MACHINE, NOTHING),
        ("7.18:Model credential", CREDENTIAL_MACHINE, NOTHING),
        ("7.18:Circuit breaker", BREAKER_MACHINE, NOTHING),
    ],
)
def test_section_7_the_declared_transitions_equal_the_spec(
    heading: str, machine: StateMachine, extra: set[tuple[str, str]]
) -> None:
    """Section 7: states are declared once. The code's transitions equal the spec's tables,
    so neither can change without the other. `extra` lists creation, which 7.1 leaves out."""
    tables = spec_tables()
    assert heading in tables, sorted(tables)
    assert declared(machine) == expand(tables[heading]) | extra


def test_section_7_an_unlisted_transition_is_refused_with_the_section_as_its_rule() -> None:
    """Section 7: a transition not listed is refused, naming what may follow."""
    with pytest.raises(Refusal) as refused:
        PROJECT_MACHINE.check(ProjectState.STOPPED, ProjectState.RUNNING)
    envelope = refused.value.envelope
    assert envelope.rule == "7.1"
    assert envelope.hint == "From stopped it can go to: deleting."


holds = st.frozensets(st.sampled_from(list(Hold)))


@given(before=holds, after=holds)
def test_7_1_any_change_of_hold_reasons_is_a_listed_transition(
    before: frozenset[Hold], after: frozenset[Hold]
) -> None:
    """Section 7.1: whatever hold reasons come and go, the state a started project moves to
    is reachable by a listed transition, and equals what the reasons imply."""
    source, target = state_under(before), state_under(after)
    assert source in HOLDABLE
    assert target in HOLDABLE
    assert source == target or PROJECT_MACHINE.allows(source, target)
    assert (target == ProjectState.RUNNING) == (not after)
    assert (target == ProjectState.PAUSED) == bool(after & PLATFORM_HOLDS)
    assert (target == ProjectState.HELD) == (after == frozenset({Hold.CHAIRMAN}))


@given(path=st.lists(st.sampled_from(sorted(PROJECT_MACHINE.states)), max_size=12))
def test_7_1_terminal_states_stay_terminal(path: list[str]) -> None:
    """Section 7.1, PRJ-3: no sequence of listed transitions leaves `deleted`, and a stopped
    project can only go on to deletion."""
    state = "draft"
    for target in path:
        if PROJECT_MACHINE.allows(state, target):
            assert state != ProjectState.DELETED
            if state == ProjectState.STOPPED:
                assert target == ProjectState.DELETING
            state = target
