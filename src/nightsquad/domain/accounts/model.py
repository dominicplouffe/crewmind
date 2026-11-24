"""States and lifecycles of accounts, credentials and membership (section 7.8 to 7.11)."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

from nightsquad.catalog.state_machine import NEW, StateMachine


class PersonState(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class LinkKind(StrEnum):
    INVITE = "invite"
    RESET = "reset"


class LinkState(StrEnum):
    UNUSED = "unused"
    USED = "used"
    EXPIRED = "expired"


class SessionState(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class TokenKind(StrEnum):
    PERSONAL = "personal"
    MCP = "mcp"


class TokenState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ProjectRole(StrEnum):
    CHAIRMAN = "chairman"
    CO_CHAIR = "co-chair"
    OBSERVER = "observer"


REMOVED = "removed"

PERSON_MACHINE = StateMachine(
    "person account",
    "7.8",
    [
        (NEW, PersonState.INVITED),
        (PersonState.INVITED, PersonState.ACTIVE),
        (PersonState.ACTIVE, PersonState.DEACTIVATED),
        (PersonState.DEACTIVATED, PersonState.ACTIVE),
    ],
)

LINK_MACHINE = StateMachine(
    "single-use link",
    "7.9",
    [
        (NEW, LinkState.UNUSED),
        (LinkState.UNUSED, LinkState.USED),
        (LinkState.UNUSED, LinkState.EXPIRED),
    ],
)

SESSION_MACHINE = StateMachine(
    "browser session",
    "7.10-session",
    [(NEW, SessionState.ACTIVE), (SessionState.ACTIVE, SessionState.ENDED)],
)

TOKEN_MACHINE = StateMachine(
    "token",
    "7.10-token",
    [
        (NEW, TokenState.ACTIVE),
        (TokenState.ACTIVE, TokenState.EXPIRED),
        (TokenState.ACTIVE, TokenState.REVOKED),
    ],
)

MEMBERSHIP_MACHINE = StateMachine(
    "project membership",
    "7.11",
    [
        (NEW, ProjectRole.CO_CHAIR),
        (NEW, ProjectRole.OBSERVER),
        (NEW, ProjectRole.CHAIRMAN),
        (ProjectRole.CO_CHAIR, ProjectRole.OBSERVER),
        (ProjectRole.OBSERVER, ProjectRole.CO_CHAIR),
        (ProjectRole.CO_CHAIR, REMOVED),
        (ProjectRole.OBSERVER, REMOVED),
        (ProjectRole.CHAIRMAN, ProjectRole.CO_CHAIR),
        (ProjectRole.CO_CHAIR, ProjectRole.CHAIRMAN),
        (ProjectRole.OBSERVER, ProjectRole.CHAIRMAN),
    ],
)

# Fixed rules the spec states without a setting name (section 0: "a fixed rule").
PASSWORD_MIN_LENGTH = 12  # ACC-1
LOGIN_FAILURES_BEFORE_LOCK = 10  # ACC-1
LOGIN_LOCK = timedelta(minutes=15)  # ACC-1
SESSION_MAX_AGE = timedelta(days=14)  # ACC-2
SESSION_MAX_IDLE = timedelta(days=3)  # ACC-2
LINK_LIFETIME = timedelta(hours=72)  # ACC-4
