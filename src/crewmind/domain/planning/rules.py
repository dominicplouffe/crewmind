"""The planning rules the platform enforces, registered once (P10)."""

from __future__ import annotations

from crewmind.catalog.rules import Rule, rules

PLN_1 = rules.register(
    Rule("PLN-1", "Scope is accepted and changed only by whoever holds that authority.")
)
PLN_3 = rules.register(
    Rule("PLN-3", "A requirement is accepted only when the plan fits the budget.")
)
PLN_10 = rules.register(
    Rule("PLN-10", "Only the platform writes a requirement met, on a check or a verdict.")
)
INV_18 = rules.register(
    Rule("INV-18", "No task is created under a requirement that is not ready for work.")
)
INV_19 = rules.register(
    Rule("INV-19", "The requirement graph is acyclic and work stays in the lowest open stage.")
)
