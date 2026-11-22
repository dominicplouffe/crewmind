"""Tables for model credentials, lineups and provider ceilings (LLM-2, LLM-4, LLM-7, LLM-12)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, UtcDateTime, new_id


class ModelCredential(Base):
    """A named credential that pays for model calls, or for web search. The value lives in
    `secrets`, encrypted; this row never holds it (LLM-2, INV-6)."""

    __tablename__ = "model_credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    provider: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(16))
    base_url: Mapped[str | None] = mapped_column(String(500))
    owner_id: Mapped[str] = mapped_column(ForeignKey("persons.id"))
    state: Mapped[str] = mapped_column(String(16))
    breaker_state: Mapped[str] = mapped_column(String(16), default="closed")
    breaker_failures: Mapped[int] = mapped_column(Integer, default=0)
    breaker_cooloff_seconds: Mapped[int] = mapped_column(Integer, default=0)
    breaker_opened_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    auth_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Lineup(Base):
    """Which model a credential uses for a class (LLM-4). `source` is auto or override."""

    __tablename__ = "lineups"
    __table_args__ = (UniqueConstraint("credential_id", "model_class"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    credential_id: Mapped[str] = mapped_column(
        ForeignKey("model_credentials.id", ondelete="CASCADE"), index=True
    )
    model_class: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ProjectCredential(Base):
    """Which credential pays in a project: the primary, the fallback, or one seat's (LLM-7)."""

    __tablename__ = "project_credentials"
    __table_args__ = (UniqueConstraint("project_id", "use", "seat_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[str] = mapped_column(ForeignKey("model_credentials.id"))
    use: Mapped[str] = mapped_column(String(16))
    seat_id: Mapped[str] = mapped_column(String(32), default="")


class ProviderCeiling(Base):
    """An install-wide limit on concurrent runs per provider (LLM-12)."""

    __tablename__ = "provider_ceilings"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    max_concurrent: Mapped[int] = mapped_column(Integer)
