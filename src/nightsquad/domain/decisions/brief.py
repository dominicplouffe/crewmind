"""The daily brief and since-you-were-away (HUM-11, CHAT-15): built from the event log at
0 tokens. Nothing here asks a model, so a report goes out on time whatever the agents do."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.domain.decisions import agenda, desk, flags, items
from nightsquad.domain.decisions.model import ItemState
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject
from nightsquad.storage.models import BriefRun, DecisionItem, Event, Person, Presence, Project

SECTIONS = (
    "worth your eye",
    "what moved",
    "what the CEO handled itself",
    "what decided itself",
    "what happens next",
)
"""HUM-11: the sections of a brief, in order."""
NEXT_SHOWN = 5
NEXT_WITHIN = timedelta(hours=24)
BRIEFED = ("running", "held", "paused")
_WORST_FIRST = ("cut", "drawn", "at risk", "accepted", "declined")


def _handled(event: Event) -> tuple[int, str] | None:
    """Something an agent decided by itself, with how much it matters (lower is worse)."""
    after = event.after or {}
    state = str(after.get("state", ""))
    if event.actor_kind != "agent":
        return None
    if event.type == "requirement.state_changed" and state in ("accepted", "declined", "cut"):
        return _WORST_FIRST.index(
            state
        ), f"The CEO moved requirement {event.subject_id} to {state}."
    if event.type == "reserve.changed" and state == "drawn":
        return 1, f"The CEO drew the CEO reserve of {after.get('tokens', 0):,} tokens."
    if event.type == "commitment.state_changed" and state == "accepted":
        return 3, "The CEO accepted or reset the commitment at the projection."
    return None


def _decided_itself(event: Event) -> str | None:
    after = event.after or {}
    state = str(after.get("state", ""))
    if event.type == "item.state_changed" and state == "defaulted":
        return f"A {after.get('kind')} item reached its deadline: {after.get('outcome')}."
    if event.type == "cycle.state_changed" and state != "open":
        return f"Cycle {event.subject_id} closed as {state}."
    if event.type == "project.hold_added" and event.actor_kind == "platform":
        return f"The project was paused: {(event.after or {}).get('reason', 'a platform hold')}."
    by_itself = state == "completed" and event.actor_kind == "platform"
    if event.type == "project.state_changed" and by_itself:
        return "The project completed by itself after its sign-off window."
    return None


async def of_project(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    since: datetime,
    now: datetime,
) -> dict[str, list[str]]:
    """One project's brief for the stretch from `since` to now, section by section. It
    separates requirements settled from tasks closed (HUM-11)."""
    events = list(
        await session.scalars(
            select(Event)
            .where(Event.project_id == project.id, Event.at > since, Event.at <= now)
            .order_by(Event.id)
        )
    )
    worth = [entry.title for entry in await desk.of_project(session, project)]
    worth += [items.title_of(flag) for flag in await flags.live(session, project.id)]
    archived = await session.scalars(
        select(DecisionItem).where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == "heads-up",
            DecisionItem.state == ItemState.ARCHIVED,
            DecisionItem.closed_at > since,
        )
    )
    worth += [f"Unacknowledged heads-up: {item.recommendation}" for item in archived]

    met = sum(
        1
        for e in events
        if e.type == "requirement.state_changed" and (e.after or {}).get("state") == "met"
    )
    closed = sum(
        1
        for e in events
        if e.type == "task.state_changed" and (e.after or {}).get("state") == "done"
    )
    moved: list[str] = []
    if met:
        moved.append(f"{met} requirements were settled as met.")
    if closed:
        moved.append(f"{closed} tasks were closed as done.")
    moved += [
        f"The project became {(e.after or {}).get('state')}."
        for e in events
        if e.type == "project.state_changed"
    ]
    handled = sorted(found for e in events if (found := _handled(e)) is not None)
    heads_ups = await session.scalars(
        select(DecisionItem).where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == "heads-up",
            DecisionItem.opened_at > since,
        )
    )
    decided = [text for e in events if (text := _decided_itself(e)) is not None]
    coming = await agenda.build(session, settings, project, now, 1)
    return {
        SECTIONS[0]: worth,
        SECTIONS[1]: moved,
        SECTIONS[2]: [text for _, text in handled]
        + [f"Heads-up: {item.recommendation}" for item in heads_ups],
        SECTIONS[3]: decided,
        SECTIONS[4]: [
            f"{line.at.strftime('%d %b %H:%M UTC')}: {line.what}. {line.consequence}"
            for line in coming[:NEXT_SHOWN]
        ],
    }


async def build(
    session: AsyncSession,
    settings: SettingsService,
    person_id: str,
    since: datetime,
    now: datetime,
) -> dict[str, Any]:
    """A person's brief across the running, held and paused projects they chair."""
    projects: list[dict[str, Any]] = []
    for project in await desk.projects_of(session, person_id):
        if project.state not in BRIEFED:
            continue
        projects.append(
            {
                "project_id": project.id,
                "name": project.name,
                "state": project.state,
                "sections": await of_project(session, settings, project, since, now),
            }
        )
    return {"since": since.isoformat(), "until": now.isoformat(), "projects": projects}


def due_date(time_of_day: str, zone: str, now: datetime) -> str | None:
    """The local date whose brief is due now, or None before `brief.time` or when off."""
    if time_of_day == "off":
        return None
    local = now.astimezone(ZoneInfo(zone))
    hour, minute = (int(part) for part in time_of_day.split(":"))
    if (local.hour, local.minute) < (hour, minute):
        return None
    return local.date().isoformat()


async def send_due(
    session: AsyncSession, settings: SettingsService, now: datetime
) -> list[BriefRun]:
    """HUM-11: build each person's brief once per local day at their `brief.time`. It is a
    platform job: it fires on time and waits for no agent."""
    built: list[BriefRun] = []
    people = await session.scalars(select(Person).where(Person.state == "active"))
    for person in people:
        subject = Subject(Scope.PERSON, person.id)
        date = due_date(
            str(await settings.get(session, subject, "brief.time")),
            str(await settings.get(session, subject, "person.timezone")),
            now,
        )
        if date is None:
            continue
        already = await session.scalar(
            select(BriefRun.id).where(BriefRun.person_id == person.id, BriefRun.local_date == date)
        )
        if already is not None:
            continue
        last = await session.scalar(
            select(BriefRun.built_at)
            .where(BriefRun.person_id == person.id)
            .order_by(BriefRun.id.desc())
            .limit(1)
        )
        body = await build(session, settings, person.id, last or now - timedelta(days=1), now)
        if not body["projects"]:
            continue
        run = BriefRun(person_id=person.id, local_date=date, body=body, built_at=now)
        session.add(run)
        built.append(run)
        for hook in sent_hooks:
            await hook(session, person.id, body, now)
    return built


sent_hooks: list[Any] = []
"""Called as `(session, person_id, body, now)` when a brief is built: alerts register."""


async def since_away(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    person_id: str,
    now: datetime,
) -> dict[str, list[str]] | None:
    """CHAT-15: when a person opens a project's chat after `brief.away_after`, what moved,
    what decided itself, what waits on them and what happens next. Opening is recorded."""
    row = await session.scalar(
        select(Presence).where(Presence.person_id == person_id, Presence.project_id == project.id)
    )
    away_after = int(
        await settings.get(session, Subject(Scope.PERSON, person_id), "brief.away_after")
    )
    last = row.seen_at if row is not None else None
    if row is None:
        session.add(Presence(person_id=person_id, project_id=project.id, seen_at=now))
    else:
        row.seen_at = now
    if last is None or now - last < timedelta(seconds=away_after):
        return None
    sections = await of_project(session, settings, project, last, now)
    return {
        "what moved": sections[SECTIONS[1]] + sections[SECTIONS[2]],
        "what decided itself": sections[SECTIONS[3]],
        "what waits on you": [entry.title for entry in await desk.of_project(session, project)],
        "what happens next": sections[SECTIONS[4]],
    }
