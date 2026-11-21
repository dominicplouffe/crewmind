"""The rule registry: every enforced rule, by id (P1, P10, NFR-20)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum


class RuleMode(StrEnum):
    """A rule refuses, or only warns while it is being tuned (NFR-20)."""

    ENFORCE = "enforce"
    WARN = "warn"


@dataclass(frozen=True)
class Rule:
    """An enforced rule. `id` is the requirement id it enforces, such as `GOV-3`."""

    id: str
    sentence: str
    mode: RuleMode = RuleMode.ENFORCE


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> Rule:
        if rule.id in self._rules:
            raise ValueError(f"rule {rule.id} is already registered")
        self._rules[rule.id] = rule
        return rule

    def get(self, rule_id: str) -> Rule:
        return self._rules[rule_id]

    def __iter__(self) -> Iterator[Rule]:
        return iter(sorted(self._rules.values(), key=lambda rule: rule.id))

    def __len__(self) -> int:
        return len(self._rules)


rules = RuleRegistry()
"""The process-wide rule registry. Every rule in it needs an attack test (P10)."""
