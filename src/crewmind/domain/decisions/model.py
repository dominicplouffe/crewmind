"""States of a decision item, declared once from section 7.5."""

from __future__ import annotations

from enum import StrEnum

from crewmind.catalog.state_machine import NEW, StateMachine


class ItemState(StrEnum):
    OPEN = "open"
    DECIDED = "decided"
    DEFAULTED = "defaulted"
    WITHDRAWN = "withdrawn"
    VOID = "void"
    RAISED = "raised"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"
    ARCHIVED = "archived"
    FILED = "filed"


S = ItemState
LIVE = (S.OPEN, S.RAISED, S.ACKNOWLEDGED)
"""States in which an item is still in front of someone."""

GENERAL = [
    (NEW, S.OPEN),
    (S.OPEN, S.DECIDED),
    (S.OPEN, S.DEFAULTED),
    (S.OPEN, S.WITHDRAWN),
    (S.OPEN, S.VOID),
    (S.RAISED, S.VOID),
]
KIND_SPECIFIC = [
    (S.OPEN, S.RAISED),
    (S.RAISED, S.ACKNOWLEDGED),
    (S.OPEN, S.CLEARED),
    (S.RAISED, S.CLEARED),
    (S.ACKNOWLEDGED, S.CLEARED),
    (S.OPEN, S.ACKNOWLEDGED),
    (S.OPEN, S.ARCHIVED),
    (S.OPEN, S.FILED),
]
"""The second table of 7.5: flags, heads-ups and mistake reports."""

ITEM_MACHINE = StateMachine("decision item", "7.5", [*GENERAL, *KIND_SPECIFIC])
