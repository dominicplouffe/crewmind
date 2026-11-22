"""Table-driven state machines (section 7). A transition not declared is refused."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules

NEW = "(new)"
"""The pseudo-state before a thing exists."""


@dataclass(frozen=True)
class Transition:
    source: str
    target: str


class StateMachine:
    """One lifecycle from section 7. `rule_id` is the section number, such as `7.1`."""

    def __init__(self, name: str, rule_id: str, transitions: Iterable[tuple[str, str]]) -> None:
        self.name = name
        self.rule_id = rule_id
        self.transitions = frozenset(Transition(source, target) for source, target in transitions)
        rules.register(
            Rule(
                rule_id, f"A {name} changes state only by a transition listed in section {rule_id}."
            )
        )

    @property
    def states(self) -> frozenset[str]:
        return frozenset(
            state
            for transition in self.transitions
            for state in (transition.source, transition.target)
            if state != NEW
        )

    def allows(self, source: str, target: str) -> bool:
        return Transition(source, target) in self.transitions

    def check(self, source: str, target: str) -> None:
        """Refuse a transition that section 7 does not list."""
        if not self.allows(source, target):
            raise Refusal(
                "transition_refused",
                f"A {self.name} cannot go from {source} to {target} (section {self.rule_id}).",
                rule=self.rule_id,
                hint=self._hint(source),
            )

    def _hint(self, source: str) -> str:
        targets = sorted(t.target for t in self.transitions if t.source == source)
        if not targets:
            return f"Nothing can follow {source}."
        return f"From {source} it can go to: {', '.join(targets)}."
