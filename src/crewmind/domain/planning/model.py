"""States of planning, declared once from section 7 (7.2, 7.4, 7.6, 7.13)."""

from __future__ import annotations

from enum import StrEnum

from crewmind.catalog.state_machine import NEW, StateMachine


class RequirementState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    IN_PROGRESS = "in progress"
    CHECKING = "checking"
    MET = "met"
    CUT = "cut"


R = RequirementState
OPEN_SCOPE = (R.ACCEPTED, R.IN_PROGRESS, R.CHECKING)
"""Accepted scope that is not yet met. It counts in the plan and blocks completion."""

REQUIREMENT_MACHINE = StateMachine(
    "requirement",
    "7.2",
    [
        (NEW, R.PROPOSED),
        (NEW, R.ACCEPTED),
        (R.PROPOSED, R.ACCEPTED),
        (R.PROPOSED, R.DECLINED),
        (R.ACCEPTED, R.IN_PROGRESS),
        (R.IN_PROGRESS, R.CHECKING),
        (R.CHECKING, R.MET),
        (R.CHECKING, R.IN_PROGRESS),
        (R.ACCEPTED, R.CUT),
        (R.IN_PROGRESS, R.CUT),
        (R.MET, R.ACCEPTED),
        (R.CUT, R.ACCEPTED),
    ],
)


class RequirementTest(StrEnum):
    COMMAND = "command"
    OBSERVABLE = "observable"
    METRIC = "metric"


class CommitmentState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    AT_RISK = "at risk"
    BREACHED = "breached"
    MET = "met"


C = CommitmentState
LIVE_COMMITMENT = (C.ACCEPTED, C.AT_RISK, C.BREACHED)
COMMITMENT_MACHINE = StateMachine(
    "commitment",
    "7.6",
    [
        (NEW, C.PROPOSED),
        (C.PROPOSED, C.ACCEPTED),
        (C.PROPOSED, C.DECLINED),
        *(
            (source, target)
            for source in LIVE_COMMITMENT
            for target in (C.AT_RISK, C.BREACHED, C.MET, C.ACCEPTED)
            if source != target
        ),
    ],
)


class BetState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CONFIRMED = "confirmed"
    KILLED = "killed"
    INCONCLUSIVE = "inconclusive"


B = BetState
FINDINGS = (B.CONFIRMED, B.KILLED, B.INCONCLUSIVE)
BET_MACHINE = StateMachine(
    "bet",
    "7.4",
    [
        (NEW, B.ACTIVE),
        (B.ACTIVE, B.EXPIRED),
        (B.EXPIRED, B.ACTIVE),
        *((source, target) for source in (B.ACTIVE, B.EXPIRED) for target in FINDINGS),
    ],
)
