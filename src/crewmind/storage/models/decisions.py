"""Decision items: everything that waits on a human, in one shape (HUM-1, section 7.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, SequenceId, UtcDateTime


class DecisionItem(Base):
    """One item that waits on a human, or that the platform keeps in front of them: an
    approval, a question, a flag, a review. Its kind decides its fields and actions."""

    __tablename__ = "decision_items"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)
    filer_kind: Mapped[str] = mapped_column(String(16))
    filer_id: Mapped[str] = mapped_column(String(64))
    subject_kind: Mapped[str | None] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(64), index=True)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON)
    recommendation: Mapped[str] = mapped_column(Text)
    if_declined: Mapped[str] = mapped_column(Text)
    basis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    deadline: Mapped[datetime | None] = mapped_column(UtcDateTime, index=True)
    default_outcome: Mapped[str | None] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(16), index=True)
    outcome: Mapped[str | None] = mapped_column(String(40))
    outcome_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    chairman_note: Mapped[str | None] = mapped_column(Text)
    extensions: Mapped[int] = mapped_column(Integer, default=0)
    reminded: Mapped[bool] = mapped_column(default=False)
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Snooze(Base):
    """A person's own "not now" on an item. It never outlasts the item's deadline (HUM-10)."""

    __tablename__ = "snoozes"
    __table_args__ = (UniqueConstraint("person_id", "item_id"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("decision_items.id", ondelete="CASCADE"))
    until: Mapped[datetime] = mapped_column(UtcDateTime)


class Purchase(Base):
    """A real-world purchase an agent declared (GOV-8). Committed purchases count against
    the monthly cap until they are cancelled (INV-10)."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32))
    what: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16))
    approval_item_id: Mapped[int | None] = mapped_column(SequenceId)
    declared_at: Mapped[datetime] = mapped_column(UtcDateTime)
    settled_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
