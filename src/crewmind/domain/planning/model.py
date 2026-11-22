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
