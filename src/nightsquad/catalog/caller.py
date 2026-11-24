"""Who is calling an operation, and what an operation requires of them (section 3, IF-3.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Authority(StrEnum):
    """What an operation requires of its caller. Checked before the handler runs (NFR-11)."""

    ANYONE = "anyone"
    PERSON = "person"
    ADMIN = "admin"
    PROJECT_OBSERVER = "project_observer"
    PROJECT_CHAIR = "project_chair"
    PROJECT_CHAIRMAN_ONLY = "project_chairman_only"
    HOST_OPERATOR = "host_operator"
    AGENT = "agent"
    AGENT_CEO = "agent_ceo"

    @property
    def is_agent(self) -> bool:
        return self in (Authority.AGENT, Authority.AGENT_CEO)

    @property
    def names_a_project(self) -> bool:
        return self in (
            Authority.PROJECT_OBSERVER,
            Authority.PROJECT_CHAIR,
            Authority.PROJECT_CHAIRMAN_ONLY,
        )


class CallerKind(StrEnum):
    ANONYMOUS = "anonymous"
    PERSON = "person"
    AGENT = "agent"
    HOST_OPERATOR = "host"
    PLATFORM = "platform"


class InstanceRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


VIA_DIRECT = "direct"


@dataclass(frozen=True)
class Caller:
    """The actor behind a call (INV-21). `via` is `direct`, or `mcp:<client>` when a person's
    MCP client acts for them (IF-5.4). `actor_id` is a person id, a seat id for an agent, or
    a platform job's name. An agent caller is bound to one run and one project (P3)."""

    kind: CallerKind
    actor_id: str = ""
    role: InstanceRole | None = None
    via: str = VIA_DIRECT
    mcp_scopes: frozenset[str] = frozenset()
    credential_id: str | None = None
    run_id: str | None = None
    project_id: str | None = None
    seat_kind: str | None = None

    @property
    def person_id(self) -> str | None:
        return self.actor_id if self.kind is CallerKind.PERSON else None

    @property
    def is_admin(self) -> bool:
        return self.kind is CallerKind.PERSON and self.role is InstanceRole.ADMIN


ANONYMOUS = Caller(CallerKind.ANONYMOUS, "anonymous")
HOST_OPERATOR = Caller(CallerKind.HOST_OPERATOR, "host operator", via="host")


def platform_job(name: str) -> Caller:
    """The caller for an automatic change made by a named job (BG-4)."""
    return Caller(CallerKind.PLATFORM, name, via="platform")
