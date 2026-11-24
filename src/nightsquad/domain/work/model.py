"""States of work and verification, declared once from section 7 (7.3, 7.15, 7.16)."""

from __future__ import annotations

from enum import StrEnum

from nightsquad.catalog.state_machine import NEW, StateMachine


class TaskState(StrEnum):
    READY = "ready"
    CLAIMED = "claimed"
    CHECKING = "checking"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    KILLED = "killed"
    CLOSED_UNREAD = "closed unread"


T = TaskState
OPEN_STATES = (T.READY, T.CLAIMED, T.CHECKING, T.REVIEW, T.BLOCKED)
"""A task that is not finished one way or another. Open tasks count against the ceilings."""

TASK_MACHINE = StateMachine(
    "task",
    "7.3",
    [
        (NEW, T.READY),
        (T.READY, T.CLAIMED),
        (T.CLAIMED, T.READY),
        (T.CLAIMED, T.CHECKING),
        (T.CLAIMED, T.REVIEW),
        (T.CLAIMED, T.DONE),
        (T.CHECKING, T.DONE),
        (T.CHECKING, T.READY),
        (T.REVIEW, T.READY),
        (T.CHECKING, T.BLOCKED),
        (T.REVIEW, T.BLOCKED),
        (T.REVIEW, T.DONE),
        (T.REVIEW, T.CLOSED_UNREAD),
        (T.CLAIMED, T.BLOCKED),
        (T.READY, T.BLOCKED),
        (T.READY, T.KILLED),
        (T.CLAIMED, T.KILLED),
        (T.BLOCKED, T.KILLED),
    ],
)


class TestKind(StrEnum):
    COMMAND = "command"
    OBSERVABLE = "observable"


class Audience(StrEnum):
    TEAM = "team"
    CHAIRMAN = "chairman"
    OUTSIDE = "outside"


class Label(StrEnum):
    """WRK-15: what a closed task may honestly be called."""

    VERIFIED = "verified"
    REVIEWED = "reviewed"
    SELF_REPORTED = "self-reported"
    CLOSED_UNREAD = "closed unread"


NOT_YET_CHECKED = "not yet checked"


class EvidenceState(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


E = EvidenceState
EVIDENCE_MACHINE = StateMachine(
    "evidence",
    "7.15",
    [(NEW, E.PENDING), (NEW, E.VERIFIED), (E.PENDING, E.VERIFIED), (E.PENDING, E.FAILED)],
)


class EffectState(StrEnum):
    DECLARED = "declared"
    FINISHED = "finished"
    RETIRED = "retired"


F = EffectState
EFFECT_MACHINE = StateMachine(
    "side effect",
    "7.16-effect",
    [(NEW, F.DECLARED), (F.DECLARED, F.FINISHED), (F.FINISHED, F.RETIRED)],
)


class WatchState(StrEnum):
    PASSING = "passing"
    FAILING = "failing"
    ENDED = "ended"


W = WatchState
WATCH_MACHINE = StateMachine(
    "watch",
    "7.16-watch",
    [
        (NEW, W.PASSING),
        (W.PASSING, W.FAILING),
        (W.FAILING, W.PASSING),
        (W.PASSING, W.ENDED),
        (W.FAILING, W.ENDED),
    ],
)

MAX_FAILURES = 3  # WRK-8
ATTEMPTS_KEPT = 5  # WRK-1
