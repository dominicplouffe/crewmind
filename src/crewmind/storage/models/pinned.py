"""Tables for pinned memory: standing orders, closed decisions, corrections, examples and
agents' own pinned notes (MEM-1, MSG-4 to MSG-7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, SequenceId, UtcDateTime


class StandingOrder(Base):
    """One sentence the chairman said once and every run must follow (MSG-4)."""

    __tablename__ = "standing_orders"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(400))
    state: Mapped[str] = mapped_column(String(16))
    message_id: Mapped[int | None] = mapped_column(SequenceId)
    proposed_by: Mapped[str] = mapped_column(String(200))
    shorten: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    retired_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class ClosedDecision(Base):
    """A topic and the chairman's ruling on it (MSG-5)."""

    __tablename__ = "closed_decisions"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(String(200))
    ruling: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    decided_at: Mapped[datetime] = mapped_column(UtcDateTime)
    reopened_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class ReopenRequest(Base):
    """An agent's request to reopen a closed decision, with the evidence it links (INV-26)."""

    __tablename__ = "reopen_requests"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("closed_decisions.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    seat_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[Any]] = mapped_column(JSON)
    approved: Mapped[bool | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Correction(Base):
    """ "Not what I asked": the reply, the chairman's words and the question (MSG-6)."""

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32), index=True)
    message_id: Mapped[int] = mapped_column(SequenceId)
    reply: Mapped[str] = mapped_column(Text)
    words: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class ExampleMark(Base):
    """A message the chairman marked as an example: an illustration, not data (MSG-7)."""

    __tablename__ = "example_marks"
    __table_args__ = (UniqueConstraint("message_id"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int] = mapped_column(SequenceId)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class PinnedNote(Base):
    """A note an agent pinned for itself. It is in every one of that agent's runs (MEM-1)."""

    __tablename__ = "pinned_notes"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class HeldPost(Base):
    """A status post held until the next reporting slot (MSG-8)."""

    __tablename__ = "held_posts"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    marker: Mapped[str | None] = mapped_column(String(16))
    run_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    due_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
