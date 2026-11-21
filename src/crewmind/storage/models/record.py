"""Tables for the event log, settings versions, idempotency keys and secrets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, SequenceId, UtcDateTime, new_id


class Event(Base):
    """One state change (INV-21). Append-only. `project_id` is empty for install events."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_project_id_id", "project_id", "id"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(64))
    actor_kind: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str] = mapped_column(String(64))
    via: Mapped[str] = mapped_column(String(120))
    at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    subject_kind: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SettingValue(Base):
    """One version of one setting for one subject (GOV-1). Append-only; the newest wins."""

    __tablename__ = "setting_values"
    __table_args__ = (UniqueConstraint("scope", "subject_id", "name", "version"),)

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_kind: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class IdempotencyKey(Base):
    """The stored result of a write made with an idempotency key (IF-3.5)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("person_id", "operation", "key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    person_id: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(200))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class StoredSecret(Base):
    """A secret value, encrypted under the install master key (ACC-6, NFR-12)."""

    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("owner_kind", "owner_id", "name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_kind: Mapped[str] = mapped_column(String(16))
    owner_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
