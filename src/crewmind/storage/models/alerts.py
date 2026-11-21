"""Tables for push alerts: each browser's push subscription and the alarms to send."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from crewmind.storage.models.base import Base, SequenceId, UtcDateTime, new_id


class PushSubscription(Base):
    """One browser a person has turned alerts on in (CHAT-20)."""

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Alarm(Base):
    """An alarm for a project's members, sent once by the alarm sender (CHAT-20)."""

    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(SequenceId, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime, index=True)
