"""Notices: platform messages to an agent (section 4, EXE-2, EXE-8)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.storage.models import Notice

PENDING, DELIVERED, CONSUMED = "pending", "delivered", "consumed"


def notify(
    session: AsyncSession,
    project_id: str,
    seat_id: str,
    kind: str,
    body: str,
    now: datetime,
    *,
    urgent: bool = False,
) -> None:
    """Leave a notice for an agent. An urgent one wakes it at once (EXE-2)."""
    session.add(
        Notice(
            project_id=project_id,
            seat_id=seat_id,
            kind=kind,
            urgent=urgent,
            body=body,
            state=PENDING,
            run_id=None,
            created_at=now,
        )
    )


async def pending(session: AsyncSession, seat_id: str) -> list[Notice]:
    rows = await session.scalars(
        select(Notice).where(Notice.seat_id == seat_id, Notice.state == PENDING).order_by(Notice.id)
    )
    return list(rows)


async def deliver(session: AsyncSession, seat_id: str, run_id: str) -> list[Notice]:
    """Hand every pending notice to a run. They are consumed when the run does not fail."""
    rows = await pending(session, seat_id)
    for row in rows:
        row.state = DELIVERED
        row.run_id = run_id
    return rows


async def settle(session: AsyncSession, run_id: str, *, failed: bool) -> None:
    """A failed run gives its notices back; any other ending consumes them (EXE-8)."""
    await session.execute(
        update(Notice)
        .where(Notice.run_id == run_id, Notice.state == DELIVERED)
        .values(state=PENDING if failed else CONSUMED, run_id=None if failed else run_id)
    )
