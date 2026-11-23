"""Connections and what projects need of them (CON)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, UtcDateTime, new_id


class ProjectNeed(Base):
    """Something a project's roles need from outside: a secret, a variable or an MCP server
    (CON-5). Met by an attached connection, open, waived for now, or dropped."""

    __tablename__ = "project_needs"
    __table_args__ = (UniqueConstraint("project_id", "kind", "name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    roles: Mapped[list[Any]] = mapped_column(JSON)
    """The slugs of the roles that need it."""
    source: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    changed_at: Mapped[datetime] = mapped_column(UtcDateTime)
