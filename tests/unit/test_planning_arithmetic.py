"""The plan's pure functions: the dependency graph and the bias multiplier (PLN-2, PLN-3,
INV-19, SPD-2, section 7.2)."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.state_machine import NEW
from nightsquad.domain.execution.roster import check_stand_down
from nightsquad.domain.planning import commitments, cycles, projection
from nightsquad.domain.planning.estimates import adjusted_runs, bias_multiplier
from nightsquad.domain.planning.graph import longest_chain, loop_if_added
from nightsquad.domain.planning.model import REQUIREMENT_MACHINE, RequirementState


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


T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


def at(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def test_PLN_4_active_hours_exclude_time_held_or_paused() -> None:
    """PLN-4: only the stretches a project was running count as active time, and the
    window is the most recent 24 of those hours."""
    changes = [(at(0), "running"), (at(10), "held"), (at(20), "running"), (at(30), "paused")]
    intervals = projection.running_intervals(changes, at(50))
    assert intervals == [(at(0), at(10)), (at(20), at(30))]
    assert projection.hours_of(intervals) == 20
    still = projection.running_intervals([*changes, (at(40), "running")], at(50))
    assert projection.trailing(still) == [(at(6), at(10)), (at(20), at(30)), (at(40), at(50))]
    assert projection.hours_of(projection.trailing(still)) == 24


@pytest.mark.parametrize(
    ("ends", "expected"),
    [
        ([at(h) for h in range(1, 10)], None),
        ([at(h) for h in range(1, 11)], 1.0),
        ([at(1 + h / 10) for h in range(20)], 2.0),
        ([at(15)] * 12, None),
    ],
)
def test_PLN_4_throughput_is_runs_per_active_hour_once_10_runs_exist(
    ends: list[datetime], expected: float | None
) -> None:
    """PLN-4: completed work runs per active hour over the trailing 24 active hours, shown
    once at least 10 runs exist. Runs that ended while the project was held do not count."""
    intervals = [(at(0), at(10))]
    assert projection.throughput(ends, intervals) == expected


@pytest.mark.parametrize(
    ("remaining", "unestimated", "rate", "median", "kind", "hours"),
    [
        (12, 0, 2.0, 600.0, "measured", 6.0),
        (12, 0, None, 1800.0, "best case", 1.5),
        (12, 0, None, None, "unknown", None),
        (0, 3, 2.0, 600.0, "unknown", None),
        (0, 0, None, None, "nothing left", 0.0),
    ],
)
def test_PLN_5_the_projection_is_measured_best_case_or_unknown(
    remaining: int,
    unestimated: int,
    rate: float | None,
    median: float | None,
    kind: str,
    hours: float | None,
) -> None:
    """PLN-5: remaining adjusted runs / throughput; without a measured throughput,
    remaining x median run duration / `run.concurrency`, labelled best case; with no
    estimates, unknown."""
    found = projection.projection_of(
        remaining_runs=remaining, unestimated=unestimated, rate=rate,
        median_run_seconds=median, concurrency=4, now=T0,
    )  # fmt: skip
    assert (found.kind, found.hours) == (kind, hours)
    assert found.at == (None if hours is None else T0 + timedelta(hours=hours))
    if kind == "best case":
        assert "best case" in found.text()


def test_GOV_4_the_burn_rate_is_the_median_tokens_per_active_hour() -> None:
    """GOV-4: median tokens per active hour over the last 24 active hours."""
    intervals = [(at(0), at(4))]
    spends = [(at(0.5), 100), (at(0.7), 50), (at(1.5), 300), (at(3.2), 900), (at(9), 5000)]
    assert projection.burn_rate(spends, intervals) == 225
    assert projection.burn_rate([], []) is None


times = st.integers(min_value=-200, max_value=200)


@given(
    scope_open=st.integers(0, 5), scope_met=st.integers(0, 5),
    date=times, projected=st.one_of(st.none(), times), now=times,
)  # fmt: skip
def test_PLN_7_the_commitment_state_follows_the_numbers(
    scope_open: int, scope_met: int, date: int, projected: int | None, now: int
) -> None:
    """PLN-7: met when all scope is met; breached when the date passed with scope open; at
    risk when the projection is later than the date; otherwise accepted."""
    state = commitments.state_for(
        scope_open=scope_open, scope_met=scope_met, date=at(date),
        projected=None if projected is None else at(projected), now=at(now),
    )  # fmt: skip
    if scope_open == 0 and scope_met > 0:
        assert state == "met"
    elif now > date:
        assert state == "breached"
    elif projected is not None and projected > date:
        assert state == "at risk"
    else:
        assert state == "accepted"


def test_PLN_4_time_waiting_only_on_the_chairman_is_not_active_time() -> None:
    """PLN-4: active hours exclude time the project was waiting only on the chairman."""
    running = [(at(0), at(10)), (at(20), at(30))]
    waits = [(at(2), at(4)), (at(9), at(21)), (at(40), at(50))]
    assert projection.without(running, waits) == [(at(0), at(2)), (at(4), at(9)), (at(21), at(30))]
    assert projection.without(running, []) == running
    assert projection.without(running, [(at(0), at(30))]) == []


@pytest.mark.parametrize(
    ("period", "roll_day", "after", "expected"),
    [
        ("hourly", 0, (2026, 11, 21, 9, 30), (2026, 11, 21, 10, 0)),
        ("daily", 0, (2026, 11, 21, 9, 30), (2026, 11, 22, 0, 0)),
        ("weekly", 0, (2026, 11, 21, 9, 30), (2026, 11, 23, 0, 0)),
        ("weekly", 0, (2026, 11, 23, 0, 0), (2026, 11, 30, 0, 0)),
        ("weekly", 5, (2026, 11, 21, 9, 30), (2026, 11, 28, 0, 0)),
        ("monthly", 1, (2026, 11, 21, 9, 30), (2026, 12, 1, 0, 0)),
        ("monthly", 28, (2026, 11, 21, 9, 30), (2026, 11, 28, 0, 0)),
        ("monthly", 15, (2026, 12, 21, 9, 30), (2027, 1, 15, 0, 0)),
        ("quarterly", 1, (2026, 11, 21, 9, 30), (2027, 1, 1, 0, 0)),
        ("quarterly", 10, (2026, 1, 5, 0, 0), (2026, 1, 10, 0, 0)),
    ],
)
def test_PRJ_8_the_next_roll_follows_the_period_and_the_roll_day(
    period: str,
    roll_day: int,
    after: tuple[int, int, int, int, int],
    expected: tuple[int, int, int, int, int],
) -> None:
    """PRJ-8: weekly cycles roll on weekday `cycle.roll_day` (0 is Monday); monthly and
    quarterly ones on that day of the month; always strictly after the moment asked."""
    moment = datetime(*after, tzinfo=UTC)
    assert cycles.next_roll(period, roll_day, moment) == datetime(*expected, tzinfo=UTC)
