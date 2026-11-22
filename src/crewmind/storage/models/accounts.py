"""Tables for people, their credentials and project membership (ACC, section 7.8 to 7.11)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, UtcDateTime, new_id


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class LoginAttempts(Base):
    """Failed logins per address, known or unknown (ACC-1)."""

    __tablename__ = "login_attempts"

    address: Mapped[str] = mapped_column(String(320), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime)


class BrowserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), index=True)
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Token(Base):
    """A personal token or an MCP client token. Only the hash is stored (ACC-3, NFR-12)."""

    __tablename__ = "tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    scopes: Mapped[list[Any]] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Link(Base):
    """A single-use invite or password-reset link (ACC-4)."""

    __tablename__ = "links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), index=True)
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        Index(
            "uq_memberships_one_chairman",
            "project_id",
            unique=True,
            sqlite_where=text("role = 'chairman' AND state = 'member'"),
            postgresql_where=text("role = 'chairman' AND state = 'member'"),
        ),
        Index(
            "uq_memberships_one_per_person",
            "project_id",
            "person_id",
            unique=True,
            sqlite_where=text("state = 'member'"),
            postgresql_where=text("state = 'member'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16))
    added_at: Mapped[datetime] = mapped_column(UtcDateTime)
    removed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class McpConfirmToken(Base):
    """A single-use confirm token for one irreversible MCP write (IF-5.3, section 7.10).
    It is bound to the client, the tool and a hash of the exact arguments."""

    __tablename__ = "mcp_confirm_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"))
    client: Mapped[str] = mapped_column(String(160))
    tool: Mapped[str] = mapped_column(String(120))
    arguments_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
