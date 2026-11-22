"""Tables for the crew library (LIB-2). Roles are in the execution tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, UtcDateTime, new_id


class Crew(Base):
    """A named, ready-made job with a team already on it (LIB-2)."""

    __tablename__ = "crews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(Text)
    ceo_role: Mapped[str] = mapped_column(String(100))
    domains: Mapped[list[Any]] = mapped_column(JSON)
    teams: Mapped[list[Any]] = mapped_column(JSON)
    estimate_runs: Mapped[int | None] = mapped_column(Integer)
    estimate_tokens: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
