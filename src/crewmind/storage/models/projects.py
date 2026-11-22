"""Tables for projects and their hold reasons (PRJ, section 7.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, UtcDateTime, new_id


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(16))
    goal: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), index=True)
    prior_state: Mapped[str | None] = mapped_column(String(16))
    delete_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    delete_confirmation_hash: Mapped[str | None] = mapped_column(String(64))
    registry_version: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str] = mapped_column(ForeignKey("persons.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    extras: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    """What a project spec carries that no other table holds: controlled domains,
    integrations needed, and credential names with their role scopes (LIB-4)."""
    doctrine_fingerprint: Mapped[str | None] = mapped_column(String(64))
    """The doctrine the project was drafted under (FND-14)."""


class HoldReason(Base):
    """One reason a project is held or paused (section 7.1). Active while `lifted_at` is empty."""

    __tablename__ = "project_hold_reasons"
    __table_args__ = (
        Index(
            "uq_hold_reasons_one_active",
            "project_id",
            "reason",
            unique=True,
            sqlite_where=text("lifted_at IS NULL"),
            postgresql_where=text("lifted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    lift_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    added_at: Mapped[datetime] = mapped_column(UtcDateTime)
    lifted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
