"""Appending to the event log (INV-21). Events are written in the caller's transaction (NFR-10)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.storage.models import Event

_event_types: dict[str, str] = {}


def event_type(name: str, description: str) -> str:
    """Declare an event type. Only declared types can be written."""
    if name in _event_types:
        raise ValueError(f"event type {name} is already declared")
    _event_types[name] = description
    return name


def event_types() -> dict[str, str]:
    return dict(_event_types)


def append_event(
    session: AsyncSession,
    *,
    type: str,
    caller: Caller,
    at: datetime,
    subject: tuple[str, str],
    project_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    detail: dict[str, Any] | None = None,
) -> Event:
    if type not in _event_types:
        raise ValueError(f"event type {type} is not declared")
    event = Event(
        project_id=project_id,
        type=type,
        actor_kind=caller.kind.value,
        actor_id=caller.actor_id,
        via=caller.via,
        at=at,
        subject_kind=subject[0],
        subject_id=subject[1],
        before=before,
        after=after,
        detail=detail,
    )
    session.add(event)
    return event
