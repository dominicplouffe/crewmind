"""Tables for the roster, runs, the ledger and notices (EXE, GOV, LLM-9, section 7.7, 7.12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from nightsquad.storage.models.base import Base, SequenceId, UtcDateTime, new_id


class Role(Base):
    """One version of an agent template (LIB-1). A team pins the version it was hired from."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", "version"),
        UniqueConstraint("slug", "version", name="uq_roles_slug_version"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), server_default="")
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    seat_kind: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(40), server_default="")
    domains: Mapped[list[Any]] = mapped_column(JSON, server_default="[]")
    description: Mapped[str] = mapped_column(Text)
    charter: Mapped[str] = mapped_column(Text)
    tools: Mapped[list[Any]] = mapped_column(JSON)
    skills: Mapped[list[Any]] = mapped_column(JSON, server_default="[]")
    credential_names: Mapped[list[Any]] = mapped_column(JSON)
    min_class: Mapped[str | None] = mapped_column(String(16))
    needs_vision: Mapped[bool] = mapped_column(default=False)
    needs_web: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(16), server_default="starter")
    """starter (shipped with nightsquad) or custom (imported, or embedded in a spec)."""
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    state: Mapped[str] = mapped_column(String(16))
    stand_down_when: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Seat(Base):
    """One working identity in a project (section 4). The CEO seat has no team."""

    __tablename__ = "seats"
    __table_args__ = (
        Index(
            "uq_seats_one_ceo",
            "project_id",
            unique=True,
            sqlite_where=text("kind = 'ceo'"),
            postgresql_where=text("kind = 'ceo'"),
        ),
        UniqueConstraint("project_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    name: Mapped[str] = mapped_column(String(100))
    """The seat's identity: events, mentions and scripts use it. It never changes."""
    display_name: Mapped[str] = mapped_column(String(100))
    """The person-like name people read, such as "Maya" (EXE-18). The chairman may change it."""
    kind: Mapped[str] = mapped_column(String(16))
    is_lead: Mapped[bool] = mapped_column(default=False)
    state: Mapped[str] = mapped_column(String(16))
    pause_reason: Mapped[str | None] = mapped_column(Text)
    held_for: Mapped[list[Any]] = mapped_column(JSON, default=list, server_default="[]")
    """Why the platform holds this seat: the needs of its role that are not met, or a
    failed seat check (CON-5, LLM-6). Empty for a seat that is not held."""
    override_class: Mapped[str | None] = mapped_column(String(16))
    override_model: Mapped[str | None] = mapped_column(String(100))
    override_effort: Mapped[str | None] = mapped_column(String(16))
    substitution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Wake(Base):
    """Why an agent was woken (EXE-2, EXE-4). One wake may take several run attempts (EXE-8)."""

    __tablename__ = "wakes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(ForeignKey("seats.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Run(Base):
    """One sandboxed agent execution (section 7.7). What it runs on is pinned at lease (EXE-6)."""

    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_project_state", "project_id", "state"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    seat_id: Mapped[str] = mapped_column(ForeignKey("seats.id", ondelete="CASCADE"), index=True)
    wake_id: Mapped[str] = mapped_column(ForeignKey("wakes.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    not_before: Mapped[datetime | None] = mapped_column(UtcDateTime)
    queued_at: Mapped[datetime] = mapped_column(UtcDateTime)
    leased_by: Mapped[str | None] = mapped_column(String(64))
    leased_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    end_detail: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_revoked: Mapped[bool] = mapped_column(default=False)
    refusals: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(100))
    provider: Mapped[str | None] = mapped_column(String(50))
    credential_id: Mapped[str | None] = mapped_column(String(32))
    harness: Mapped[str | None] = mapped_column(String(50))
    effort: Mapped[str | None] = mapped_column(String(16))
    max_tokens: Mapped[int | None] = mapped_column(BigInteger)
    reached_model: Mapped[bool] = mapped_column(default=False)
    rewrite_asked: Mapped[bool] = mapped_column(default=False)
    memory_extracted: Mapped[bool] = mapped_column(default=False)
    delivered: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    context_pack: Mapped[str | None] = mapped_column(Text)


class RunStep(Base):
    """One step of a run's trace: a model call, a tool call or text (EXE-11)."""

    __tablename__ = "run_steps"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class RunRefusal(Base):
    """A refusal an agent met during a run (EXE-10)."""

    __tablename__ = "run_refusals"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    operation: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(64))
    rule: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    got_past: Mapped[bool] = mapped_column(default=False)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class LedgerLine(Base):
    """One metered line (section 4, LLM-9). Tokens by kind for a model call; a count for a
    search. `counted` is what the line costs the budget: non-cached tokens only (GOV-2)."""

    __tablename__ = "ledger_lines"
    __table_args__ = (Index("ix_ledger_project_at", "project_id", "at"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(String(32))
    run_id: Mapped[str | None] = mapped_column(String(32), index=True)
    seat_id: Mapped[str | None] = mapped_column(String(32))
    credential_id: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))
    unit: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    counted: Mapped[int] = mapped_column(BigInteger, default=0)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class Notice(Base):
    """A platform message to an agent (section 4). Urgent kinds wake it (EXE-2)."""

    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    seat_id: Mapped[str] = mapped_column(ForeignKey("seats.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    urgent: Mapped[bool] = mapped_column(default=False)
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    run_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
