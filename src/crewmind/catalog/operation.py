"""An operation: one domain action, defined once (IF-1.1)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from crewmind.catalog.surfaces import Surface

_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_SLASH = re.compile(r"^/[a-z][a-z0-9_-]*$")


class CatalogError(ValueError):
    """An operation definition, or the catalog itself, is invalid."""


class Reversibility(StrEnum):
    """Reversibility class (IF-1.1). An irreversible MCP write needs two calls (IF-5.3)."""

    READ = "read"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class Principal(StrEnum):
    """Who may call an operation (section 9.2). Each principal reaches fixed surfaces (IF-1.3)."""

    PERSON = "person"
    MCP_CLIENT = "mcp_client"
    AGENT_RUN = "agent_run"


Handler = Callable[[Any], Awaitable[BaseModel]]


@dataclass(frozen=True)
class Operation:
    """One domain action (IF-1.1). Surfaces are adapters over it and hold no rules (IF-1.2).

    `name` is `group.verb`. `authority` names the role or scope required. `audit_actor`
    names the actor kind recorded in the event log (INV-21). A host-local operation runs
    on the host without the server (IF-4.2) and serves no principal. `exemptions` maps a
    surface the operation belongs on to the written reason it is absent there (IF-1.3).
    """

    name: str
    summary: str
    input: type[BaseModel]
    output: type[BaseModel]
    handler: Handler
    authority: str
    reversibility: Reversibility
    audit_actor: str
    principals: frozenset[Principal] = frozenset()
    slash_command: str | None = None
    host_local: bool = False
    exemptions: Mapping[Surface, str] = field(default_factory=dict[Surface, str])

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise CatalogError(f"operation name {self.name!r} is not of the form group.verb")
        for label, value in (
            ("summary", self.summary),
            ("authority", self.authority),
            ("audit actor", self.audit_actor),
        ):
            if not value.strip():
                raise CatalogError(f"operation {self.name} has an empty {label}")
        if self.host_local and self.principals:
            raise CatalogError(f"host-local operation {self.name} must not name principals")
        if not self.host_local and not self.principals:
            raise CatalogError(f"operation {self.name} serves no principal")
        if self.slash_command is not None:
            if not _SLASH.match(self.slash_command):
                raise CatalogError(f"operation {self.name} has a malformed slash command")
            if Principal.PERSON not in self.principals:
                raise CatalogError(f"operation {self.name} has a slash command but no person")
        for surface, reason in self.exemptions.items():
            if not reason.strip():
                raise CatalogError(
                    f"operation {self.name} exempts {surface.value} without a written reason"
                )

    @property
    def group(self) -> str:
        return self.name.split(".", 1)[0]

    @property
    def verb(self) -> str:
        return self.name.split(".", 1)[1]
