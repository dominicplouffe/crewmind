"""Reading the event log (INV-21, IF-3.5, IF-3.8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.pagination import PageRequest, fetch_page
from crewmind.storage.models import Event


class RecordInput(PageRequest):
    project_id: str = Field(description="The project's id.")
    type: str | None = Field(None, description="Only events of this type.")


class InstallRecordInput(PageRequest):
    type: str | None = Field(None, description="Only events of this type.")


class EventItem(BaseModel):
    id: int
    type: str
    actor_kind: str = Field(description="person, platform or host.")
    actor: str
    via: str = Field(description="direct, mcp:<client>, platform or host.")
    at: datetime
    subject_kind: str
    subject_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    detail: dict[str, Any] | None


class Record(BaseModel):
    items: list[EventItem]
    next: str | None = None


async def _record(
    context: Context, project_id: str | None, page: PageRequest, type: str | None
) -> Record:
    statement = select(Event).where(
        Event.project_id.is_(None) if project_id is None else Event.project_id == project_id
    )
    if type is not None:
        statement = statement.where(Event.type == type)
    rows, cursor = await fetch_page(context.session, statement, page, key=Event.id, at=Event.at)
    return Record(
        items=[
            EventItem(
                id=row.id,
                type=row.type,
                actor_kind=row.actor_kind,
                actor=row.actor_id,
                via=row.via,
                at=row.at,
                subject_kind=row.subject_kind,
                subject_id=row.subject_id,
                before=row.before,
                after=row.after,
                detail=row.detail,
            )
            for row in rows
        ],
        next=cursor,
    )


@operation(
    "record.list",
    summary="Show a project's event log: every state change, with who made it.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_record(context: Context, payload: RecordInput) -> Record:
    return await _record(context, payload.project_id, payload, payload.type)


@operation(
    "record.list_install",
    summary="Show the install's event log: accounts, tokens and install settings.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.READ,
)
async def list_install_record(context: Context, payload: InstallRecordInput) -> Record:
    return await _record(context, None, payload, payload.type)
