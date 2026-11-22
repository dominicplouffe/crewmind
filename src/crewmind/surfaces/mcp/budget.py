"""The context budget for MCP payloads (IF-5.7): tools summarise by default and return
full detail on request. Whatever is cut is marked; nothing is cut silently."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Budget:
    string: int
    items: int
    payload: int


SUMMARY = Budget(string=600, items=20, payload=6_000)  # IF-5.7
FULL = Budget(string=20_000, items=200, payload=40_000)  # IF-5.7
TRUNCATED = "truncated"
"""The key that marks a payload from which something was left out."""
SMALLEST_LIST = 1


def _cut(data: Any, budget: Budget, items: int, notes: list[str]) -> Any:
    if isinstance(data, str):
        if len(data) <= budget.string:
            return data
        notes.append(f"a text of {len(data):,} characters was cut to {budget.string:,}")
        left = len(data) - budget.string
        return f"{data[: budget.string]} [truncated: {left:,} more characters]"
    if isinstance(data, list):
        rows: list[Any] = data  # pyright: ignore[reportUnknownVariableType]
        kept = [_cut(row, budget, items, notes) for row in rows[:items]]
        if len(rows) > items:
            notes.append(f"a list of {len(rows)} items was cut to {items}")
        return kept
    if isinstance(data, dict):
        fields: dict[str, Any] = data  # pyright: ignore[reportUnknownVariableType]
        return {key: _cut(value, budget, items, notes) for key, value in fields.items()}
    return data


def fit(data: Any, *, full: bool) -> Any:
    """`data` within the budget. Strings and lists are cut to their limits; if the whole
    payload is still too large, lists are cut further. The result says what was cut."""
    budget = FULL if full else SUMMARY
    items = budget.items
    while True:
        notes: list[str] = []
        cut = _cut(data, budget, items, notes)
        if len(json.dumps(cut)) <= budget.payload or items <= SMALLEST_LIST:
            break
        items = max(items // 2, SMALLEST_LIST)
    if not notes:
        return cut
    hint = "" if full else " Ask again with detail set to full for more."
    marked: dict[str, Any] = {TRUNCATED: "; ".join(dict.fromkeys(notes)) + "." + hint}
    if isinstance(cut, dict):
        whole: dict[str, Any] = cut  # pyright: ignore[reportUnknownVariableType]
        return {**whole, **marked}
    return {"items": cut, **marked}
