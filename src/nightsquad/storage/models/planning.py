"""Tables for planning: requirements and their dependencies, commitments, bets, cycles,
metric readings, the CEO reserve, raise requests, gap reviews and where the time went
(PLN, PRJ-4 to PRJ-8, GOV-5, GOV-10, WRK-11, SPD-8; sections 7.2, 7.4, 7.6 and 7.13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nightsquad.storage.models.base import Base, SequenceId, UtcDateTime


class Requirement(Base):
    """One piece of scope (PLN-1). Only the platform writes it met (PLN-10)."""

    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    author_kind: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), index=True)
    test_kind: Mapped[str] = mapped_column(String(16))
    success_test: Mapped[str] = mapped_column(Text)
    test_files: Mapped[dict[str, Any]] = mapped_column(JSON)
    estimate_runs: Mapped[int | None] = mapped_column(Integer)
    actual_runs: Mapped[int | None] = mapped_column(Integer)
    actual_tokens: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[int] = mapped_column(Integer, default=1)
    recurring: Mapped[bool] = mapped_column(default=False)
    metric: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    escalated: Mapped[bool] = mapped_column(default=False)
    ruling: Mapped[str | None] = mapped_column(String(16))
    ruling_note: Mapped[str | None] = mapped_column(Text)
    ruled_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    reason: Mapped[str | None] = mapped_column(Text)
    gap_id: Mapped[int | None] = mapped_column(SequenceId)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    met_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class RequirementDependency(Base):
    """`requirement_id` cannot be worked on until `depends_on` is met (PLN-2)."""

    __tablename__ = "requirement_dependencies"
    __table_args__ = (UniqueConstraint("requirement_id", "depends_on"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    depends_on: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"))


class Commitment(Base):
    """A date the project is held to (PLN-6). The date is the projection or the chairman's."""

    __tablename__ = "commitments"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[datetime | None] = mapped_column(UtcDateTime)
    projected: Mapped[datetime | None] = mapped_column(UtcDateTime)
    scope: Mapped[list[Any]] = mapped_column(JSON)
    settings_version: Mapped[int | None] = mapped_column(Integer)
    resets: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    proposed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    settled_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class TargetDate(Base):
    """A date the chairman would like, with where it comes from (PLN-9). Not a commitment."""

    __tablename__ = "target_dates"
    __table_args__ = (UniqueConstraint("project_id"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    date: Mapped[datetime] = mapped_column(UtcDateTime)
    source: Mapped[str] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Bet(Base):
    """An Explore project's unit of scope: a statement, a kill condition and a kill date."""

    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    statement: Mapped[str] = mapped_column(Text)
    kill_condition: Mapped[str] = mapped_column(Text)
    kill_at: Mapped[datetime] = mapped_column(UtcDateTime)
    state: Mapped[str] = mapped_column(String(16), index=True)
    extended: Mapped[bool] = mapped_column(default=False)
    extension_reason: Mapped[str | None] = mapped_column(Text)
    finding: Mapped[str | None] = mapped_column(String(500))
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Cycle(Base):
    """One period of an Operate project (PRJ-8). At most one is open."""

    __tablename__ = "cycles"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), index=True)
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)
    ends_at: Mapped[datetime] = mapped_column(UtcDateTime)
    due_at: Mapped[datetime] = mapped_column(UtcDateTime)
    scorecard: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    narrative: Mapped[str | None] = mapped_column(Text)
    narrative_by_ceo: Mapped[bool] = mapped_column(default=False)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class MetricReading(Base):
    """One platform reading of a metric requirement's number (PLN-11)."""

    __tablename__ = "metric_readings"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    failure: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class ReserveDraw(Base):
    """A draw of the CEO reserve, with its reason and arithmetic (GOV-10)."""

    __tablename__ = "reserve_draws"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(16))
    tokens: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    arithmetic: Mapped[str] = mapped_column(Text)
    drawn_by: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UtcDateTime)
    settled_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class RaiseRequest(Base):
    """The CEO's request for a higher budget or concurrency (GOV-5)."""

    __tablename__ = "raise_requests"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    what: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    arithmetic: Mapped[str] = mapped_column(Text)
    if_declined: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    granted: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(UtcDateTime)
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class GapReview(Base):
    """A final gap review of a Deliver project's deliverables against its goal (WRK-11)."""

    __tablename__ = "gap_reviews"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(32))
    asked_at: Mapped[datetime] = mapped_column(UtcDateTime)
    filed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Gap(Base):
    """One gap a review found: must-fix or nice-to-have, with its reason."""

    __tablename__ = "gaps"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("gap_reviews.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    text: Mapped[str] = mapped_column(Text)
    must_fix: Mapped[bool] = mapped_column()
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    waived_reason: Mapped[str | None] = mapped_column(Text)


class TimeSpan(Base):
    """A stretch of a project's time and what it went to (SPD-8)."""

    __tablename__ = "time_spans"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    went_to: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(UtcDateTime)
    ended_at: Mapped[datetime] = mapped_column(UtcDateTime)
