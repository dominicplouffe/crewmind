"""Alerts (INT-7): one per-person setting, `alerts.level`, decides what reaches a person
as a browser push. Alarms are never held back. Email arrives with mail (phase 8)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.domain.decisions import brief, items
from crewmind.domain.decisions.model import ItemState
from crewmind.storage.models import Alarm, DecisionItem, Project

ALARM, DECISION, OTHER = "alarm", "decision", "other"
RECEIVES = {
    "everything": (ALARM, DECISION, OTHER),
    "decisions_and_alarms": (ALARM, DECISION),
    "alarms_only": (ALARM,),
}
"""INT-7: what each `alerts.level` lets through."""
CHASE_FIRST = timedelta(hours=3)  # INT-7: proposals are chased after 3 hours
CHASE_EVERY = timedelta(days=1)  # INT-7: then daily
CHASED = ("proposed scope", "proposed commitment")


def wants(level: str, alert_level: str) -> bool:
    return alert_level in RECEIVES.get(level, RECEIVES["decisions_and_alarms"])


def queue(
    session: AsyncSession,
    project: Project,
    body: str,
    now: datetime,
    *,
    level: str,
    person_id: str | None = None,
) -> None:
    session.add(
        Alarm(
            project_id=project.id,
            title=project.name,
            body=body,
            level=level,
            person_id=person_id,
            created_at=now,
        )
    )


async def item_filed(
    session: AsyncSession, project: Project, item: DecisionItem, now: datetime
) -> None:
    """A new item that waits on the chairman is a decision alert; anything else is sent
    only to people who asked for everything."""
    kind = items.kind_of(item.kind)
    level = DECISION if kind.desk and kind.actions else OTHER
    queue(session, project, items.title_of(item), now, level=level)


async def item_reminder(
    session: AsyncSession, project: Project, item: DecisionItem, now: datetime
) -> None:
    queue(session, project, f"Still waiting: {items.title_of(item)}", now, level=DECISION)


items.filed_hooks.append(item_filed)
items.reminder_hooks.append(item_reminder)


async def chase(session: AsyncSession, project: Project, now: datetime) -> int:
    """INT-7: proposed scope and commitments that wait on the chairman are chased after 3
    hours, then daily, in one batched message per project."""
    rows = list(
        await session.scalars(
            select(DecisionItem)
            .where(
                DecisionItem.project_id == project.id,
                DecisionItem.kind.in_(CHASED),
                DecisionItem.state == ItemState.OPEN,
            )
            .order_by(DecisionItem.id)
        )
    )
    due = [
        item
        for item in rows
        if now - (item.chased_at or item.opened_at)
        >= (CHASE_EVERY if item.chased_at else CHASE_FIRST)
    ]
    if not due:
        return 0
    for item in rows:
        item.chased_at = now
    titles = "; ".join(items.title_of(item) for item in rows)
    queue(session, project, f"{len(rows)} proposals wait on you: {titles}", now, level=DECISION)
    return len(rows)


async def brief_ready(
    session: AsyncSession, person_id: str, body: dict[str, Any], now: datetime
) -> None:
    """Tell one person their daily brief is ready."""
    first = body["projects"][0]
    project = await session.get(Project, first["project_id"])
    if project is None:
        return
    waiting = sum(len(entry["sections"]["worth your eye"]) for entry in body["projects"])
    session.add(
        Alarm(
            project_id=project.id,
            title="Your daily brief",
            body=f"{len(body['projects'])} projects; {waiting} things worth your eye.",
            level=DECISION,
            person_id=person_id,
            created_at=now,
        )
    )


brief.sent_hooks.append(brief_ready)
