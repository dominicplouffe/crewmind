"""Connections and what projects need of them (CON)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, ForeignKey, String, Text, UniqueConstraint
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


class Connection(Base):
    """A secret, a variable or an MCP server, in one of three scopes (CON-1). The value of a
    secret is never here: it is in `secrets`, sealed to this row (CON-2)."""

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(16))
    owner_id: Mapped[str] = mapped_column(String(32), index=True)
    """The person for a person item, the project for a project item, empty for the install."""
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100), index=True)
    """The name folded to lower case: names are unique per owner whatever their case."""
    description: Mapped[str] = mapped_column(String(300))
    env_name: Mapped[str | None] = mapped_column(String(100))
    """The environment variable or file name a run gets it under, where it gets one."""
    state: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    changed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    value_set_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    expires_on: Mapped[date | None] = mapped_column(Date)
    warned: Mapped[list[Any]] = mapped_column(JSON, default=list, server_default="[]")
    """The expiry warnings already given for the current expiry date ("early", "day")."""


class ConnectionSecret(Base):
    """How a secret is used (CON-2): sent for you to named sites, or given to the agent."""

    __tablename__ = "connection_secrets"

    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), primary_key=True
    )
    delivery: Mapped[str] = mapped_column(String(16))
    sites: Mapped[list[Any]] = mapped_column(JSON, default=list)
    header_kind: Mapped[str | None] = mapped_column(String(16))
    header_name: Mapped[str | None] = mapped_column(String(100))
    basic_user: Mapped[str | None] = mapped_column(String(200))
    shape: Mapped[str | None] = mapped_column(String(16))


class ConnectionVariable(Base):
    """A variable's plain value (CON-3)."""

    __tablename__ = "connection_variables"

    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[str] = mapped_column(Text)


class ProjectConnection(Base):
    """A connection attached to a project and granted to some of its roles (CON-4)."""

    __tablename__ = "project_connections"
    __table_args__ = (UniqueConstraint("project_id", "connection_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True
    )
    env_name: Mapped[str | None] = mapped_column(String(100))
    """This project's environment variable or file name, when it differs from the item's."""
    roles: Mapped[list[Any]] = mapped_column(JSON)
    """The role slugs granted, or ["*"] for every role."""
    attached_by: Mapped[str] = mapped_column(String(32))
    attached_at: Mapped[datetime] = mapped_column(UtcDateTime)
    changed_at: Mapped[datetime] = mapped_column(UtcDateTime)
