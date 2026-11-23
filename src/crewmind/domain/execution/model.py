"""States, lifecycles and fixed rules of the roster and of runs (section 7.7, 7.12, EXE)."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW, StateMachine


class SeatKind(StrEnum):
    CEO = "ceo"
    LEAD = "lead"
    WORKER = "worker"
    REVIEWER = "reviewer"


class SeatState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOOD_DOWN = "stood down"


class TeamState(StrEnum):
    ACTIVE = "active"
    STOOD_DOWN = "stood down"


class RunKind(StrEnum):
    WORK = "work"
    CHAT = "chat"
    CHECK = "check"


class RunState(StrEnum):
    QUEUED = "queued"
    DROPPED = "dropped"
    LEASED = "leased"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    KILLED = "killed"
    TERMINATED = "terminated"
    REAPED = "reaped"


LIVE_STATES = (RunState.LEASED, RunState.RUNNING)
OPEN_STATES = (RunState.QUEUED, RunState.LEASED, RunState.RUNNING)

R = RunState
RUN_MACHINE = StateMachine(
    "run",
    "7.7",
    [
        (NEW, R.QUEUED),
        (R.QUEUED, R.DROPPED),
        (R.QUEUED, R.LEASED),
        (R.LEASED, R.FAILED),
        (R.LEASED, R.RUNNING),
        (R.LEASED, R.REAPED),
        (R.LEASED, R.KILLED),
        (R.RUNNING, R.FINISHED),
        (R.RUNNING, R.FAILED),
        (R.RUNNING, R.KILLED),
        (R.RUNNING, R.TERMINATED),
        (R.RUNNING, R.REAPED),
    ],
)

TEAM_MACHINE = StateMachine(
    "team",
    "7.12-team",
    [
        (NEW, TeamState.ACTIVE),
        (TeamState.ACTIVE, TeamState.STOOD_DOWN),
        (TeamState.STOOD_DOWN, TeamState.ACTIVE),
    ],
)

SEAT_MACHINE = StateMachine(
    "seat",
    "7.12-seat",
    [
        (NEW, SeatState.ACTIVE),
        (SeatState.ACTIVE, SeatState.PAUSED),
        (SeatState.PAUSED, SeatState.ACTIVE),
        (SeatState.ACTIVE, SeatState.STOOD_DOWN),
        (SeatState.PAUSED, SeatState.STOOD_DOWN),
        (SeatState.STOOD_DOWN, SeatState.ACTIVE),
    ],
)

# Fixed rules the spec states without a setting name.
HEARTBEAT_EVERY = timedelta(seconds=20)  # EXE-7
LEASE_TTL = timedelta(seconds=90)  # EXE-7
MAX_ATTEMPTS = 3  # EXE-8
RETRY_BACKOFF = timedelta(seconds=30)  # EXE-8: 30 seconds x attempt
CAP_WARNING_SHARE = 0.8  # GOV-6: the gateway warns the harness at 80% of the per-run cap

EXE_1 = rules.register(Rule("EXE-1", "The roster is one CEO plus teams, within `teams.max`."))
EXE_18 = rules.register(
    Rule("EXE-18", "Every agent has its own name in a project; only a person changes it.")
)
EXE_10 = rules.register(Rule("EXE-10", "At the refusal cap a run's token is revoked."))
P3 = rules.register(Rule("P3", "An agent acts only through the agent API, with its own run token."))
