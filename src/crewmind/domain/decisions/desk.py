"""The desk (HUM-10): one definition of "waiting on you", used everywhere. Snoozing is a
person's own and never outlasts an item's deadline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.decisions import items
from crewmind.domain.decisions.model import ItemState
from crewmind.storage.models import (
    Bet,
    DecisionItem,
    FrozenThread,
    Membership,
    Project,
    Snooze,
)

HUM_10 = rules.register(
    Rule("HUM-10", "A snooze is a person's own and never outlasts the item's deadline.")
)
SNOOZE_MOST = timedelta(days=7)  # HUM-10: an item with no deadline returns within 7 days
CHAIRS = ("chairman", "co-chair")
LIVE_PROJECTS = ("running", "held", "paused", "ready")


@dataclass(frozen=True)
class Entry:
    """One thing that waits on a person."""

    project_id: str
    project_name: str
    what: str
    title: str
    deadline: datetime | None
    item: DecisionItem | None = None


async def of_project(session: AsyncSession, project: Project) -> list[Entry]:
    """Everything in one project that waits on its chairman: open items of the kinds
    that ask for a decision, expired bets, and frozen threads."""
    found: list[Entry] = []
    rows = await session.scalars(
        select(DecisionItem)
        .where(DecisionItem.project_id == project.id, DecisionItem.state == ItemState.OPEN)
        .order_by(DecisionItem.id)
    )
    for item in rows:
        kind = items.kind_of(item.kind)
        if kind.desk and kind.actions:
            found.append(
                Entry(
                    project.id, project.name, item.kind, items.title_of(item), item.deadline, item
                )
            )
    for bet in await session.scalars(
        select(Bet).where(Bet.project_id == project.id, Bet.state == "expired").order_by(Bet.id)
    ):
        found.append(
            Entry(
                project.id,
                project.name,
                "expired bet",
                f"Bet {bet.id} expired with no finding",
                None,
            )
        )
    for thread in await session.scalars(
        select(FrozenThread).where(FrozenThread.project_id == project.id, FrozenThread.frozen)
    ):
        found.append(
            Entry(
                project.id,
                project.name,
                "frozen thread",
                f"Thread {thread.thread_id} is frozen until you unfreeze it",
                None,
            )
        )
    return found


async def waits(session: AsyncSession, project: Project) -> bool:
    return bool(await of_project(session, project))


async def projects_of(session: AsyncSession, person_id: str) -> list[Project]:
    """The live projects this person chairs or co-chairs."""
    rows = await session.scalars(
        select(Project)
        .join(Membership, Membership.project_id == Project.id)
        .where(
            Membership.person_id == person_id,
            Membership.state == "member",
            Membership.role.in_(CHAIRS),
            Project.state.in_(LIVE_PROJECTS),
        )
        .order_by(Project.created_at, Project.id)
    )
    return list(rows)


async def of_person(session: AsyncSession, person_id: str, now: datetime) -> list[Entry]:
    """The desk: what waits on this person across their projects, leaving out what they
    snoozed."""
    snoozed = set(
        await session.scalars(
            select(Snooze.item_id).where(Snooze.person_id == person_id, Snooze.until > now)
        )
    )
    found: list[Entry] = []
    for project in await projects_of(session, person_id):
        for entry in await of_project(session, project):
            if entry.item is None or entry.item.id not in snoozed:
                found.append(entry)
    return found


async def snooze(
    session: AsyncSession, person_id: str, item: DecisionItem, until: datetime, now: datetime
) -> datetime:
    """HUM-10: hide an item from one person's desk for a while. It comes back at its
    deadline at the latest, or within 7 days when it has none."""
    latest = item.deadline if item.deadline is not None else now + SNOOZE_MOST
    if until <= now or until > latest:
        raise Refusal(
            "snooze_too_long",
            f"Snooze this item until {latest.strftime('%d %b %Y %H:%M UTC')} at the latest.",
            rule=HUM_10.id,
        )
    row = await session.scalar(
        select(Snooze).where(Snooze.person_id == person_id, Snooze.item_id == item.id)
    )
    if row is None:
        session.add(Snooze(person_id=person_id, item_id=item.id, until=until))
    else:
        row.until = until
    return until
