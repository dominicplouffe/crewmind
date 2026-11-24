"""Tables for drafting a project in conversation and for grilling a document (FND,
section 7.19)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nightsquad.storage.models.base import Base, SequenceId, UtcDateTime, new_id


class Drafting(Base):
    """One interview: the Founder drafting a new project with a person, or the CEO
    grilling a document in a running project (FND-1, FND-16)."""

    __tablename__ = "draftings"
    __table_args__ = (Index("ix_draftings_person", "person_id", "state"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    """founder (a new project) or grill (a document in a running project)."""
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"))
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(16))
    quick: Mapped[bool] = mapped_column(default=False)
    document: Mapped[str | None] = mapped_column(Text)
    """The pasted or uploaded brief being grilled, when there is one (FND-15)."""
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    """The newest proposed project spec, with its reasons (FND-3, FND-10)."""
    grade: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rehearsal: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rehearsed_draft: Mapped[str | None] = mapped_column(String(64))
    """The fingerprint of the draft the rehearsal ran on (FND-11)."""
    rest_accepted: Mapped[bool] = mapped_column(default=False)
    """The chairman said: use your recommendations for the rest (FND-15)."""
    doctrine: Mapped[str] = mapped_column(String(64))
    """The fingerprint of the doctrine this interview runs under (FND-14)."""
    turn: Mapped[str] = mapped_column(String(16), default="idle")
    """idle, due (the person spoke and the interviewer owes a turn) or failed."""
    turn_attempts: Mapped[int] = mapped_column(Integer, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    failure: Mapped[str | None] = mapped_column(Text)
    rules_hit: Mapped[list[Any]] = mapped_column(JSON, default=list)
    """Each tool call of the interviewer that a rule refused: the tool, the rule, the code."""
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class DraftingMessage(Base):
    """One line of an interview before there is a project chat to hold it (FND-1)."""

    __tablename__ = "drafting_messages"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    drafting_id: Mapped[str] = mapped_column(
        ForeignKey("draftings.id", ondelete="CASCADE"), index=True
    )
    author: Mapped[str] = mapped_column(String(16))
    """person, founder or platform."""
    body: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class DraftingQuestion(Base):
    """One decision put to the chairman, with a recommended answer (FND-3)."""

    __tablename__ = "drafting_questions"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    drafting_id: Mapped[str] = mapped_column(
        ForeignKey("draftings.id", ondelete="CASCADE"), index=True
    )
    settles: Mapped[str] = mapped_column(String(64))
    """The decision it settles: a key of the tree, or `item:<id>` for a grilled passage."""
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list[Any]] = mapped_column(JSON)
    recommended: Mapped[int | None] = mapped_column(Integer)
    changes: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    answer: Mapped[str | None] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(UtcDateTime)
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class LedgerEntry(Base):
    """One settled decision and where it came from (FND-5)."""

    __tablename__ = "drafting_ledger"
    __table_args__ = (UniqueConstraint("drafting_id", "settles"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    drafting_id: Mapped[str] = mapped_column(
        ForeignKey("draftings.id", ondelete="CASCADE"), index=True
    )
    settles: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))
    """words (the chairman's own), answer or assumption."""
    passage: Mapped[str | None] = mapped_column(Text)
    """The chairman's words, or the passage of the document, this entry rests on."""
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class GrillItem(Base):
    """One thing extracted from a document being grilled (FND-15)."""

    __tablename__ = "grill_items"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    drafting_id: Mapped[str] = mapped_column(
        ForeignKey("draftings.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    passage: Mapped[str] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    """clear (nothing to ask), open (a question is owed) or resolved."""
    is_example: Mapped[bool] = mapped_column(default=False)
