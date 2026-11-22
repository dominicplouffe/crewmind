"""Tables for work and verification: tasks, reviews, audit samples, outside evidence, side
effects and watches (WRK-1 to WRK-17, sections 7.3, 7.15 and 7.16)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, SequenceId, UtcDateTime


class Task(Base):
    """One piece of work with a success test (WRK-1). A subtask has a parent."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(SequenceId, index=True)
    team_id: Mapped[str | None] = mapped_column(String(32))
    assignee_id: Mapped[str | None] = mapped_column(String(32))
    author_id: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    goal: Mapped[str] = mapped_column(Text)
    test_kind: Mapped[str] = mapped_column(String(16))
    success_test: Mapped[str] = mapped_column(Text)
    test_files: Mapped[dict[str, Any]] = mapped_column(JSON)
    test_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    outside_evidence: Mapped[bool] = mapped_column(default=False)
    audience: Mapped[str] = mapped_column(String(16))
    serves: Mapped[str | None] = mapped_column(Text)
    requirement_id: Mapped[int | None] = mapped_column(SequenceId, index=True)
    bet_id: Mapped[int | None] = mapped_column(SequenceId, index=True)
    not_before: Mapped[datetime | None] = mapped_column(UtcDateTime)
    state: Mapped[str] = mapped_column(String(16), index=True)
    claimant_id: Mapped[str | None] = mapped_column(String(32), index=True)
    reserved_for: Mapped[str | None] = mapped_column(String(32))
    claimed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    completion_evidence: Mapped[str | None] = mapped_column(Text)
    check_output: Mapped[str | None] = mapped_column(Text)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str | None] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class TaskAttempt(Base):
    """One attempt at a task: what was claimed as done and what the check or review said."""

    __tablename__ = "task_attempts"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    seat_id: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool | None] = mapped_column()
    output: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class Suggestion(Base):
    """An agent's suggestion for the backlog. It creates no work (WRK-2)."""

    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    handed_to_run: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Review(Base):
    """An independent read of a task by a reviewer seat (WRK-9)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(32), index=True)
    ok: Mapped[bool | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(UtcDateTime)
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class AuditSample(Base):
    """One observable close considered for the chairman's audit: drawn or skipped, once."""

    __tablename__ = "audit_samples"
    __table_args__ = (UniqueConstraint("task_id"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    drawn: Mapped[bool] = mapped_column()
    verdict: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    considered_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Evidence(Base):
    """Outside evidence an agent claims, counted only once the platform verifies it."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[int | None] = mapped_column(SequenceId)
    seat_id: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(String(2000))
    claim: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    failure: Mapped[str | None] = mapped_column(Text)
    filed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    settled_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class SideEffect(Base):
    """Something an agent does outside the project, declared before it fires (WRK-16). A
    launch is a side effect that leaves something running (WRK-17)."""

    __tablename__ = "side_effects"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32))
    run_id: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    what: Mapped[str] = mapped_column(Text)
    is_launch: Mapped[bool] = mapped_column(default=False)
    state: Mapped[str] = mapped_column(String(16))
    fired: Mapped[bool | None] = mapped_column()
    outcome: Mapped[str | None] = mapped_column(Text)
    declared_at: Mapped[datetime] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    retired_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Watch(Base):
    """The check that keeps an eye on a launch, run by the platform at 0 tokens (WRK-17)."""

    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("side_effect_id"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    side_effect_id: Mapped[int] = mapped_column(ForeignKey("side_effects.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    check: Mapped[str] = mapped_column(Text)
    expect: Mapped[str | None] = mapped_column(Text)
    interval_seconds: Mapped[int] = mapped_column(Integer)
    state: Mapped[str | None] = mapped_column(String(16), index=True)
    last_result: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class ProjectGuard(Base):
    """A runaway guard that is open on a project: stalled or spinning (EXE-16, GOV-7)."""

    __tablename__ = "project_guards"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    cause: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)
    cleared_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
