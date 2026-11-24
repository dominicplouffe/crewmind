"""Tables for artifacts, uploads in progress, directives, action cards and frozen threads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nightsquad.storage.models.base import Base, SequenceId, UtcDateTime, new_id


class Artifact(Base):
    """Any file in the project (ART-1). Its bytes live in content-addressed storage."""

    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16))
    audience: Mapped[str] = mapped_column(String(16))
    locked: Mapped[bool] = mapped_column(default=False)
    mark: Mapped[str | None] = mapped_column(String(16))
    superseded_by: Mapped[str | None] = mapped_column(String(500))
    purpose: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(100))
    author_kind: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(200))
    run_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class UploadInProgress(Base):
    """A resumable upload that has not finished (IF-3.9)."""

    __tablename__ = "uploads_in_progress"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    person_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    received: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Directive(Base):
    """An explicit instruction to act (MSG-3, section 7.17)."""

    __tablename__ = "directives"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32))
    author_id: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    card_id: Mapped[int | None] = mapped_column(SequenceId)
    outcome: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    done_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class ActionCard(Base):
    """An agent's proposal to act on something said in chat (CHAT-7, section 7.17)."""

    __tablename__ = "action_cards"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seat_id: Mapped[str] = mapped_column(String(32))
    message_id: Mapped[int | None] = mapped_column(SequenceId)
    what: Mapped[str] = mapped_column(Text)
    estimated_tokens: Mapped[int] = mapped_column(BigInteger)
    reversible: Mapped[bool] = mapped_column()
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class FrozenThread(Base):
    """A thread the pair breaker froze (MSG-9). `thread_id` 0 is a channel's main line."""

    __tablename__ = "frozen_threads"
    __table_args__ = (UniqueConstraint("channel_id", "thread_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    channel_id: Mapped[str] = mapped_column(String(32))
    thread_id: Mapped[int] = mapped_column(SequenceId)
    frozen: Mapped[bool] = mapped_column(default=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    frozen_at: Mapped[datetime] = mapped_column(UtcDateTime)
