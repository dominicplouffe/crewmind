"""Project states, hold reasons and the project lifecycle (section 7.1, PRJ-1 to PRJ-3, PRJ-10)."""

from __future__ import annotations

from enum import StrEnum

from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW, StateMachine


class ProjectType(StrEnum):
    EXPLORE = "explore"
    DELIVER = "deliver"
    OPERATE = "operate"


class ProjectState(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    HELD = "held"
    PAUSED = "paused"
    READY = "ready"
    COMPLETED = "completed"
    STOPPED = "stopped"
    DELETING = "deleting"
    DELETED = "deleted"


class Hold(StrEnum):
    """Why a project is held or paused (section 7.1). Each is lifted by its own trigger."""

    CHAIRMAN = "chairman"
    BUDGET_WALL = "budget_wall"
    AUTH_FAILURES = "auth_failures"
    SKIPPED_CYCLES = "skipped_cycles"


PLATFORM_HOLDS = frozenset({Hold.BUDGET_WALL, Hold.AUTH_FAILURES, Hold.SKIPPED_CYCLES})

LIFTED_BY: dict[Hold, str] = {
    Hold.CHAIRMAN: "`/resume`, or its lift time",
    Hold.BUDGET_WALL: "a budget raise, a reserve draw, or the Operate monthly reset",
    Hold.AUTH_FAILURES: "`/resume`, once the credential passes a check",
    Hold.SKIPPED_CYCLES: "`/resume`",
}

S = ProjectState
_STOPPABLE = (S.DRAFT, S.RUNNING, S.HELD, S.PAUSED, S.READY)
_DELETABLE = (S.DRAFT, S.STOPPED, S.COMPLETED)

PROJECT_MACHINE = StateMachine(
    "project",
    "7.1",
    [
        (NEW, S.DRAFT),
        (S.DRAFT, S.RUNNING),
        (S.RUNNING, S.HELD),
        (S.RUNNING, S.PAUSED),
        (S.HELD, S.PAUSED),
        (S.PAUSED, S.HELD),
        (S.HELD, S.RUNNING),
        (S.PAUSED, S.RUNNING),
        (S.RUNNING, S.READY),
        (S.READY, S.RUNNING),
        (S.READY, S.COMPLETED),
        (S.RUNNING, S.COMPLETED),
        (S.HELD, S.COMPLETED),
        (S.PAUSED, S.COMPLETED),
        (S.COMPLETED, S.RUNNING),
        *((state, S.STOPPED) for state in _STOPPABLE),
        *((state, S.DELETING) for state in _DELETABLE),
        *((S.DELETING, state) for state in _DELETABLE),
        (S.DELETING, S.DELETED),
    ],
)

PRJ_1 = rules.register(Rule("PRJ-1", "A project starts only when every start check passes."))
PRJ_2 = rules.register(Rule("PRJ-2", "A hold is lifted only by its own trigger."))
PRJ_10 = rules.register(Rule("PRJ-10", "Deleting a project is chairman-only and takes two steps."))
INV_5 = rules.register(
    Rule("INV-5", "A project you cannot see answers exactly like one that does not exist.")
)

GOAL_MAX_LENGTH = 6_000  # section 4, a fixed rule


def state_under(holds: frozenset[Hold]) -> ProjectState:
    """The state a started project has under a set of hold reasons (section 7.1)."""
    if not holds:
        return ProjectState.RUNNING
    if holds & PLATFORM_HOLDS:
        return ProjectState.PAUSED
    return ProjectState.HELD


HOLDABLE = frozenset({ProjectState.RUNNING, ProjectState.HELD, ProjectState.PAUSED})
"""States in which hold reasons decide the state."""
