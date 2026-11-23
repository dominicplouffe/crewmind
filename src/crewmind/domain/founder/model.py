"""The drafting conversation's lifecycle and words (section 7.19, FND-1, FND-5, FND-12)."""

from __future__ import annotations

from enum import StrEnum

from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import StateMachine


class DraftingState(StrEnum):
    DRAFTING = "drafting"
    CREATED = "created"
    CREATING = "creating"
    STARTING = "starting"
    STARTED = "started"
    FAILED = "failed"
    DISCARDED = "discarded"


D = DraftingState
NEW = "(new)"
DRAFTING_MACHINE = StateMachine(
    "drafting conversation",
    "7.19",
    {
        (NEW, D.DRAFTING),
        (D.DRAFTING, D.CREATED),
        (D.DRAFTING, D.CREATING),
        (D.CREATING, D.STARTING),
        (D.STARTING, D.STARTED),
        (D.CREATING, D.FAILED),
        (D.STARTING, D.FAILED),
        (D.DRAFTING, D.DISCARDED),
    },
)

FOUNDER, GRILL = "founder", "grill"
PERSON, PLATFORM = "person", "platform"
WORDS, ANSWER, ASSUMPTION = "words", "answer", "assumption"
"""Where a ledger entry came from (FND-5)."""
IDLE, DUE, FAILED_TURN = "idle", "due", "failed"

OPEN, ANSWERED = "open", "answered"
ITEM_CLEAR, ITEM_OPEN, ITEM_RESOLVED = "clear", "open", "resolved"
ITEM_KINDS = ("goal", "requirement", "constraint", "number", "date", "name", "example")
PROBLEMS = ("contradiction", "vague", "example_or_real", "unverifiable", "grammar_gap", "conflict")
"""FND-15: what makes an extracted item a question. `conflict` is with a standing order,
a closed decision or existing scope, in a running project (FND-16)."""

FND_3 = rules.register(
    Rule("FND-3", "A question is one decision with a recommended answer and 2 to 4 options.")
)
FND_4 = rules.register(
    Rule("FND-4", "A decision is asked only once its prerequisites are settled, in order.")
)
FND_5 = rules.register(
    Rule("FND-5", "A project is created only from a confirmed ledger with nothing left open.")
)
FND_9 = rules.register(Rule("FND-9", "A Deliver or Operate roster staffs a plan adversary."))
FND_10 = rules.register(Rule("FND-10", "The Founder sets a setting only with its reason."))
FND_11 = rules.register(Rule("FND-11", "A draft is rehearsed before it is called ready."))
FND_15 = rules.register(
    Rule("FND-15", "A document is grilled, every item resolved, before anything is drafted.")
)
