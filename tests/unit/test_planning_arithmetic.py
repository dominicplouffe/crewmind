"""The plan's pure functions: the dependency graph and the bias multiplier (PLN-2, PLN-3,
INV-19, SPD-2, section 7.2)."""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.state_machine import NEW
from crewmind.domain.execution.roster import check_stand_down
from crewmind.domain.planning.estimates import adjusted_runs, bias_multiplier
from crewmind.domain.planning.graph import longest_chain, loop_if_added
from crewmind.domain.planning.model import REQUIREMENT_MACHINE, RequirementState


@pytest.mark.parametrize(
    ("settled", "multiplier"),
    [
        ([], 1.0),
        ([(4, 12)], 1.0),
        ([(4, 6), (4, 6)], 1.5),
        ([(4, 2), (4, 2)], 1.0),
        ([(2, 2), (0, 9), (2, 6)], 2.0),
        ([(1, 3)] * 12 + [(1, 100)], 3.0),
    ],
)
def test_PLN_3_the_bias_multiplier_is_actual_over_estimated_and_never_below_1(
    settled: list[tuple[int, int]], multiplier: float
) -> None:
    """PLN-3: measured from the 12 most recently settled requirements, at least 2 needed,
    never below 1. An estimate of 0 is left out."""
    assert bias_multiplier(settled) == multiplier


def test_PLN_3_adjusted_runs_round_up() -> None:
    """PLN-3: adjusted runs = estimate x multiplier, as whole runs."""
    assert [adjusted_runs(3, 1.0), adjusted_runs(3, 1.5), adjusted_runs(1, 1.01)] == [3, 5, 2]


def acyclic(graph: dict[int, set[int]]) -> bool:
    done: set[int] = set()
    nodes = set(graph) | {n for needed in graph.values() for n in needed}
    while True:
        free = {n for n in nodes - done if graph.get(n, set()) <= done}
        if not free:
            return done == nodes
        done |= free


edges = st.lists(st.tuples(st.integers(1, 7), st.integers(1, 7)), max_size=40)


@given(wanted=edges)
def test_INV_19_any_sequence_of_edges_leaves_the_graph_acyclic(
    wanted: list[tuple[int, int]],
) -> None:
    """INV-19, PLN-2: whatever edges are asked for in whatever order, adding only those
    that close no loop keeps the graph acyclic, and a refused edge names a real loop."""
    graph: dict[int, set[int]] = {}
    for requirement, depends_on in wanted:
        loop = loop_if_added(graph, requirement, depends_on)
        if loop is None:
            graph.setdefault(requirement, set()).add(depends_on)
            assert acyclic(graph)
            continue
        assert loop[0] == loop[-1] == requirement
        assert loop[1] == depends_on
        for node, needed in itertools.pairwise(loop[1:]):
            assert needed in graph[node]


def test_SPD_2_the_longest_chain_is_the_one_that_takes_the_most_runs() -> None:
    """SPD-2, PLN-2: the longest dependency chain by runs, in the order it must be done."""
    graph = {2: {1}, 3: {2}, 4: {1}, 5: {4}}
    assert longest_chain(graph, {1: 2, 2: 3, 3: 1, 4: 1, 5: 9}) == (12, [1, 4, 5])
    assert longest_chain(graph, {1: 2, 2: 3, 3: 1}) == (6, [1, 2, 3])
    assert longest_chain({}, {}) == (0, [])


states = st.sampled_from(sorted(RequirementState))


@given(path=st.lists(states, max_size=12))
def test_7_2_only_the_listed_moves_reach_met_and_proposed_scope_is_never_worked(
    path: list[RequirementState],
) -> None:
    """Section 7.2: along any sequence of listed transitions, met is reached only from
    checking, in progress only from accepted or checking, and declined is final."""
    current: str = NEW
    for target in path:
        if not REQUIREMENT_MACHINE.allows(current, target):
            continue
        if target == RequirementState.MET:
            assert current == RequirementState.CHECKING
        if target == RequirementState.IN_PROGRESS:
            assert current in (RequirementState.ACCEPTED, RequirementState.CHECKING)
        assert current != RequirementState.DECLINED
        current = target


def test_PLN_12_a_stand_down_condition_is_one_the_platform_can_check() -> None:
    """PLN-12: "requirements met" or "stage N cleared", and nothing free-form."""
    assert check_stand_down(None) is None
    assert check_stand_down(" Requirements  met ") == "requirements met"
    assert check_stand_down("Stage 2 cleared") == "stage 2 cleared"
    with pytest.raises(Refusal):
        check_stand_down("when the CEO feels done")
