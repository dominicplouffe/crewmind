"""Connections: what they are, their states, their rules and their names (CON-1 to CON-4,
CON-7, 7.18).

Plain checks only; nothing here reads the database.
"""

from __future__ import annotations

import re
from enum import StrEnum

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW, StateMachine
from crewmind.storage.events import event_type

CON_1 = rules.register(
    Rule("CON-1", "A connection is changed only by its owner: the person, an admin, or a chair.")
)
CON_2 = rules.register(
    Rule("CON-2", "A secret's value is write-only: never shown again, only replaced.")
)
CON_3 = rules.register(Rule("CON-3", "A variable has a name, a description and a plain value."))
CON_4 = rules.register(
    Rule("CON-4", "A run gets only what is attached to its project and granted to its role.")
)
CON_7 = rules.register(
    Rule("CON-7", "A given secret's variable or file name never changes how programs run.")
)


class Kind(StrEnum):
    SECRET = "secret"
    VARIABLE = "variable"
    MCP_SERVER = "mcp_server"


class Scope(StrEnum):
    INSTALL = "install"
    PERSON = "person"
    PROJECT = "project"


class ConnectionState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DELETED = "deleted"


class Delivery(StrEnum):
    SENT_FOR_YOU = "sent_for_you"
    GIVEN = "given"


class HeaderKind(StrEnum):
    BEARER = "bearer"
    BASIC = "basic"
    HEADER = "header"


class Shape(StrEnum):
    TEXT = "text"
    FILE = "file"


S = ConnectionState
CONNECTION_MACHINE = StateMachine(
    "connection",
    "7.18-connection",
    [
        (NEW, S.ACTIVE),
        (S.ACTIVE, S.EXPIRED),
        (S.EXPIRED, S.ACTIVE),
        (S.ACTIVE, S.DELETED),
        (S.EXPIRED, S.DELETED),
    ],
)

ALL_ROLES = "*"
"""A grant to every role of the project (CON-4)."""

SECRET_OWNER = "connection"
"""The owner kind a connection's value is sealed under (CON-2)."""
SECRET_NAME = "value"

ADDED = event_type("connection.added", "A secret, variable or MCP server was added (CON-1).")
CHANGED = event_type("connection.changed", "A connection's description or use changed (CON-1).")
REPLACED = event_type("connection.value_replaced", "A secret's value was replaced (CON-2).")
STATE_CHANGED = event_type("connection.state_changed", "A connection changed state (7.18).")
EXPIRY_WARNED = event_type("connection.expiry_warned", "A secret's expiry was announced (CON-2).")
ATTACHED = event_type("connection.attached", "A connection was attached to a project (CON-4).")
DETACHED = event_type("connection.detached", "A connection was detached from a project (CON-4).")
GRANTED = event_type("connection.grants_changed", "The roles granted a connection changed.")

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
_HOST = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$"
)
_TOKEN = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}$")

RESERVED_ENV_EXACT = frozenset(
    {"PATH", "HOME", "NODE_OPTIONS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS"}
)
RESERVED_ENV_PREFIXES = ("CREWMIND_", "LD_", "PYTHON")
RESERVED_ENV_SUFFIXES = ("_PROXY",)
"""CON-7: names that change how programs run."""

FORBIDDEN_HEADERS = frozenset(
    {"host", "content-length", "transfer-encoding", "connection", "cookie", "mcp-session-id"}
)
"""CON-9: header names a connection may not set."""


def check_name(name: str) -> str:
    if not _NAME.match(name):
        raise Refusal(
            "connection_name_invalid",
            f"{name!r} is not a usable name.",
            rule=CON_1.id,
            hint="Start with a letter; use letters, digits, _, - and . (at most 100).",
        )
    return name


def default_env_name(name: str) -> str:
    """The variable a run gets a connection under, unless one is chosen: the name in upper
    case, with - and . as _."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name).upper()


def check_env_name(name: str) -> str:
    upper = name.upper()
    if not _ENV.match(name):
        raise Refusal(
            "env_name_invalid",
            f"{name!r} is not a usable variable or file name.",
            rule=CON_7.id,
            hint="Use letters, digits and _, not starting with a digit.",
        )
    if (
        upper in RESERVED_ENV_EXACT
        or upper.startswith(RESERVED_ENV_PREFIXES)
        or upper.endswith(RESERVED_ENV_SUFFIXES)
    ):
        raise Refusal(
            "env_name_reserved",
            f"{name} changes how programs run, so it cannot carry a connection.",
            rule=CON_7.id,
            hint="Choose another name, for example with a prefix of your own.",
        )
    return name


def check_site(site: str) -> str:
    """A site is an exact host name: no scheme, path, port or wildcard (CON-6)."""
    host = site.strip().lower().rstrip(".")
    if not _HOST.match(host) or ("." not in host and host != "localhost"):
        raise Refusal(
            "site_invalid",
            f"{site!r} is not a site. Give the exact host name, such as api.example.com.",
            rule=CON_2.id,
            hint="No https://, path, port or wildcard.",
        )
    return host


def check_header_name(name: str) -> str:
    if not _TOKEN.match(name) or name.lower() in FORBIDDEN_HEADERS:
        raise Refusal(
            "header_name_invalid",
            f"{name!r} cannot carry a secret.",
            rule=CON_2.id,
            hint="Use an ordinary header name such as X-Api-Key. Host, Content-Length, "
            "Transfer-Encoding, Connection, Cookie and Mcp-Session-Id are refused.",
        )
    return name


def check_single_line(text: str, what: str, rule: str = CON_2.id) -> str:
    if "\n" in text or "\r" in text:
        raise Refusal(
            f"{what}_multiline", f"The {what.replace('_', ' ')} must be one line.", rule=rule
        )
    return text


KIND_WORDS = {Kind.SECRET: "secret", Kind.VARIABLE: "variable", Kind.MCP_SERVER: "MCP server"}
