"""Tables for the one conversation model (MSG-1, MSG-13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, SequenceId, UtcDateTime, new_id


class Channel(Base):
    """A conversation space: the project chat, leadership, or one room per team (MSG-1)."""

    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_channel_id", "channel_id", "id"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    author_kind: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))
    body: Mapped[str] = mapped_column(Text)
    reply_to: Mapped[int | None] = mapped_column(SequenceId)
    thread_id: Mapped[int | None] = mapped_column(SequenceId, index=True)
    addressed: Mapped[list[Any]] = mapped_column(JSON)
    run_id: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ReadPosition(Base):
    """How far a reader has read a channel. One per reader, shared by every surface (MSG-13)."""

    __tablename__ = "read_positions"
    __table_args__ = (UniqueConstraint("channel_id", "reader_kind", "reader_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    reader_kind: Mapped[str] = mapped_column(String(16))
    reader_id: Mapped[str] = mapped_column(String(64))
    last_read: Mapped[int] = mapped_column(SequenceId)
