"""The desk, the brief, since-you-were-away and the agenda as operations (HUM-10 to
HUM-12, CHAT-15, IF-3.8). All of them read the record; none calls a model."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.domain.decisions import agenda, brief, desk, items
from crewmind.domain.decisions.operations import ItemRef, ItemView, view
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import Subject
from crewmind.services import services_of

AGENDA_DAYS_MOST = 90  # HUM-12


class DeskEntry(BaseModel):
    project_id: str
    project_name: str
    what: str = Field(description="The item's kind, or expired bet, or frozen thread.")
    title: str
    deadline: datetime | None
    item: ItemView | None


class Desk(BaseModel):
    waiting: list[DeskEntry] = Field(description="Everything that waits on you.")


class SnoozeInput(ItemRef):
    until: datetime = Field(description="When it should come back to your desk.")


class Snoozed(BaseModel):
    item_id: int
    until: datetime


class Brief(BaseModel):
    since: datetime
    until: datetime
    projects: list[dict[str, Any]] = Field(
        description="Per project: worth your eye, what moved, what the CEO handled itself, "
        "what decided itself, and what happens next."
    )


class Away(BaseModel):
    away: bool = Field(description="Whether you were away long enough for a summary.")
    summary: dict[str, list[str]] | None


class AgendaInput(ProjectRef):
    days: int | None = Field(default=None, ge=1, le=AGENDA_DAYS_MOST, description="How far ahead.")


class AgendaLine(BaseModel):
    at: datetime
    what: str
    consequence: str


class Agenda(BaseModel):
    timezone: str
    next_wake: datetime | None = Field(
        description="The next time the clock, not a message, wakes an agent."
    )
    lines: list[AgendaLine]


@operation(
    "desk.show",
    summary="Show everything that waits on you, across your projects.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_desk(context: Context, payload: Empty) -> Desk:
    """HUM-10: one definition of "waiting on you", used everywhere."""
    found = await desk.of_person(context.session, context.caller.actor_id, context.now)
    return Desk(
        waiting=[
            DeskEntry(
                project_id=entry.project_id,
                project_name=entry.project_name,
                what=entry.what,
                title=entry.title,
                deadline=entry.deadline,
                item=view(entry.item) if entry.item is not None else None,
            )
            for entry in found
        ]
    )


@operation(
    "items.snooze",
    summary="Hide an item from your desk for a while. It returns by its deadline.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.REVERSIBLE,
)
async def snooze_item(context: Context, payload: SnoozeInput) -> Snoozed:
    """HUM-10: per person, and never past the item's deadline."""
    item = await items.get(context.session, payload.project_id, payload.item_id)
    until = await desk.snooze(
        context.session, context.caller.actor_id, item, payload.until, context.now
    )
    context.record(
        items.ITEM_EDITED,
        subject=("item", str(item.id)),
        project_id=item.project_id,
        after={"snoozed_until": until.isoformat()},
    )
    return Snoozed(item_id=item.id, until=until)


@operation(
    "brief.show",
    summary="Show your brief for the last day, built from the record now.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_brief(context: Context, payload: Empty) -> Brief:
    """HUM-11: built at 0 tokens from the event log."""
    body = await brief.build(
        context.session,
        services_of(context).settings,
        context.caller.actor_id,
        context.now - timedelta(days=1),
        context.now,
    )
    return Brief.model_validate(body)


@operation(
    "chat.opened",
    summary="Say you opened a project's chat. If you were away, you get what happened.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.REVERSIBLE,
)
async def chat_opened(context: Context, payload: ProjectRef) -> Away:
    """CHAT-15: after `brief.away_after`, the chat starts with a summary from the record."""
    summary = await brief.since_away(
        context.session,
        services_of(context).settings,
        view_of(context).project,
        context.caller.actor_id,
        context.now,
    )
    return Away(away=summary is not None, summary=summary)


@operation(
    "agenda.show",
    summary="Show what will happen in a project in the next days.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_agenda(context: Context, payload: AgendaInput) -> Agenda:
    """HUM-12, INV-22: the next `agenda.days` days, in the project's timezone, agreeing
    with the dispatcher's next time-based wake."""
    project = view_of(context).project
    settings = services_of(context).settings
    days = payload.days or int(
        await settings.get(
            context.session, Subject(Scope.PERSON, context.caller.actor_id), "agenda.days"
        )
    )
    zone = await settings.get(
        context.session, Subject(Scope.PROJECT, project.id, project.type), "project.timezone"
    )
    lines = await agenda.build(context.session, settings, project, context.now, days)
    return Agenda(
        timezone=str(zone),
        next_wake=await agenda.next_time_wake(context.session, settings, project, context.now),
        lines=[
            AgendaLine(at=line.at, what=line.what, consequence=line.consequence) for line in lines
        ],
    )
