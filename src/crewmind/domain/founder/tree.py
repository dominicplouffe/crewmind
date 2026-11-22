"""The decisions a draft rests on, and the order they are asked in (FND-4)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    key: str
    what: str
    level: str
    """root, branch or leaf."""


ROOTS = (
    Decision("finish_line", "The finish line, and the record that settles it", "root"),
    Decision(
        "beneficiary_standard", "Who the work is for, and the standard it is judged by", "root"
    ),
    Decision("project_type", "The project type: explore, deliver or operate", "root"),
    Decision("who_pays", "Which credential pays", "root"),
    Decision("outside_date", "Any date the outside world imposes", "root"),
)
BRANCHES = (
    Decision("budget", "The budget", "branch"),
    Decision("anti_metrics", "What does not count as success", "branch"),
    Decision("chairman_role", "What the chairman will and will not do", "branch"),
    Decision("roster", "The team", "branch"),
)
LEAVES = (
    Decision("quality", "The quality setting", "leaf"),
    Decision("authority_preset", "How much the CEO decides alone", "leaf"),
    Decision("failure_deliverable", "What is owed if the finish line is missed", "leaf"),
    Decision("resource_posture", "How freely to spend, and when that changes", "leaf"),
)
TREE: tuple[Decision, ...] = (*ROOTS, *BRANCHES, *LEAVES)
"""In the order they are asked: prerequisites first, most load-bearing first (FND-4)."""
KEYS = frozenset(decision.key for decision in TREE)
_LEVELS = ("root", "branch", "leaf")


def ready(settled: set[str]) -> list[Decision]:
    """The unsettled decisions whose prerequisites are settled: a branch needs every
    root, and a leaf needs every branch."""
    found: list[Decision] = []
    for index, level in enumerate(_LEVELS):
        before = [d for d in TREE if _LEVELS.index(d.level) < index]
        if all(d.key in settled for d in before):
            found += [d for d in TREE if d.level == level and d.key not in settled]
    return found


def next_one(settled: set[str]) -> Decision | None:
    """The one decision to ask next when asking one at a time."""
    waiting = ready(settled)
    return waiting[0] if waiting else None


def unsettled(settled: set[str]) -> list[Decision]:
    return [decision for decision in TREE if decision.key not in settled]
