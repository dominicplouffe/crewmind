"""What people do with decision items (HUM-1, HUM-3, IF-3.8): the same few operations
for every kind, so a new kind needs no new surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.registry import catalog
from crewmind.domain.decisions import items, spend
from crewmind.domain.decisions.model import LIVE
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.services import services_of
from crewmind.storage.models import DecisionItem, Event, Purchase


class ItemView(BaseModel):
    id: int
    project_id: str
    kind: str
    title: str = Field(description="Built from the item's typed fields.")
    state: str
    filed_by: str = Field(description="agent or platform.")
    fields: dict[str, Any]
    recommendation: str
    if_declined: str
    basis: dict[str, Any] | None
    actions: list[str] = Field(description="What you can do with it now.")
    deadline: datetime | None
    default_outcome: str | None = Field(description="What happens if nobody answers.")
    outcome: str | None
    chairman_note: str | None
    waits_on_you: bool
    opened_at: datetime
    closed_at: datetime | None


class ItemList(BaseModel):
    items: list[ItemView]


class ItemListInput(ProjectRef):
    open_only: bool = Field(default=True, description="Leave out items that are closed.")
    kind: str | None = Field(default=None, description="Only items of this kind.")


class ItemRef(ProjectRef):
    item_id: int = Field(description="The item's id, from `items list`.")


class DecideInput(ItemRef):
    action: str = Field(description="One of the item's actions.")
    note: str | None = Field(default=None, max_length=2000, description="Your note.")
    amount: int | None = Field(default=None, ge=1, description="A number to grant instead.")
    date: datetime | None = Field(default=None, description="A date of your own, where asked.")
    option: int | None = Field(default=None, ge=1, description="The option you pick.")


class ExtendInput(ItemRef):
    days: int = Field(description="How many days more: 1 to 30.")
    reason: str = Field(max_length=2000, description="Why it needs more time.")


class NoteInput(ItemRef):
    note: str = Field(min_length=1, max_length=2000, description="Your note on the item.")


class HistoryLine(BaseModel):
    at: datetime
    actor_kind: str
    what: str
    state: str | None


class ItemDetail(ItemView):
    history: list[HistoryLine]


def view(item: DecisionItem) -> ItemView:
    kind = items.kind_of(item.kind)
    live = item.state in LIVE
    return ItemView(
        id=item.id,
        project_id=item.project_id,
        kind=item.kind,
        title=items.title_of(item),
        state=item.state,
        filed_by=item.filer_kind,
        fields=item.fields,
        recommendation=item.recommendation,
        if_declined=item.if_declined,
        basis=item.basis,
        actions=list(kind.actions) if item.state == "open" else [],
        deadline=item.deadline,
        default_outcome=item.default_outcome,
        outcome=item.outcome,
        chairman_note=item.chairman_note,
        waits_on_you=live and kind.desk and bool(kind.actions),
        opened_at=item.opened_at,
        closed_at=item.closed_at,
    )


@operation(
    "items.list",
    summary="List a project's decision items: what waits on you, and what was decided.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_items(context: Context, payload: ItemListInput) -> ItemList:
    """HUM-1: every kind in one list."""
    wanted = select(DecisionItem).where(DecisionItem.project_id == payload.project_id)
    if payload.open_only:
        wanted = wanted.where(DecisionItem.state.in_(LIVE))
    if payload.kind is not None:
        wanted = wanted.where(DecisionItem.kind == payload.kind)
    rows = await context.session.scalars(wanted.order_by(DecisionItem.id))
    return ItemList(items=[view(row) for row in rows])


@operation(
    "items.show",
    summary="Show one decision item with its full history.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_item(context: Context, payload: ItemRef) -> ItemDetail:
    """HUM-1: an item carries its full history."""
    item = await items.get(context.session, payload.project_id, payload.item_id)
    events = await context.session.scalars(
        select(Event)
        .where(Event.subject_kind == "item", Event.subject_id == str(item.id))
        .order_by(Event.id)
    )
    history = [
        HistoryLine(
            at=event.at,
            actor_kind=event.actor_kind,
            what=event.type,
            state=(event.after or {}).get("state"),
        )
        for event in events
    ]
    return ItemDetail(**view(item).model_dump(), history=history)


@operation(
    "items.decide",
    summary="Decide an item with one of its actions.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def decide_item(context: Context, payload: DecideInput) -> ItemView:
    """HUM-1, HUM-3: approving applies what was asked for."""
    project = view_of(context).project
    item = await items.get(context.session, project.id, payload.item_id)
    values = {
        name: value
        for name, value in (
            ("amount", payload.amount),
            ("date", payload.date),
            ("option", payload.option),
        )
        if value is not None
    }

    async def call(name: str, **given: Any) -> BaseModel:
        target = catalog.get(name)
        return await context.executor.call(
            context, target, target.input(project_id=project.id, **given)
        )

    await items.decide(
        context.session,
        services_of(context),
        project,
        item,
        payload.action,
        context.caller,
        context.now,
        note=payload.note,
        values=values,
        call=call,
    )
    return view(item)


@operation(
    "items.extend",
    summary="Give an open approval more time, with a reason.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def extend_item(context: Context, payload: ExtendInput) -> ItemView:
    """HUM-3: 1 to 30 days; a decided item cannot be extended."""
    item = await items.get(context.session, payload.project_id, payload.item_id)
    await items.extend(
        context.session, item, payload.days, payload.reason, context.caller, context.now
    )
    return view(item)


@operation(
    "items.note",
    summary="Write your note on an item.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def note_item(context: Context, payload: NoteInput) -> ItemView:
    """HUM-1: an optional chairman note."""
    item = await items.get(context.session, payload.project_id, payload.item_id)
    await items.add_note(context.session, item, payload.note, context.caller, context.now)
    return view(item)


class PurchaseLine(BaseModel):
    id: int
    what: str
    amount: float
    state: str = Field(description="committed, bought or cancelled.")
    declared_at: datetime


class SpendView(BaseModel):
    enabled: bool
    currency: str
    monthly_cap: float
    approval_at: float = Field(description="A purchase at or above this needs your approval.")
    committed_this_month: float
    purchases: list[PurchaseLine]


@operation(
    "spend.show",
    summary="Show real-world spend: the cap, what is committed this month, and each purchase.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_spend(context: Context, payload: ProjectRef) -> SpendView:
    """GOV-8: money is budgeted only for real-world spend, and only once it is turned on."""
    project = view_of(context).project
    found = await spend.limits(context.session, services_of(context).settings, project, context.now)
    rows = await context.session.scalars(
        select(Purchase).where(Purchase.project_id == project.id).order_by(Purchase.id)
    )
    return SpendView(
        enabled=found.enabled,
        currency=found.currency,
        monthly_cap=found.cap_cents / spend.CENTS,
        approval_at=found.approval_at_cents / spend.CENTS,
        committed_this_month=found.committed_cents / spend.CENTS,
        purchases=[
            PurchaseLine(
                id=row.id,
                what=row.what,
                amount=row.amount_cents / spend.CENTS,
                state=row.state,
                declared_at=row.declared_at,
            )
            for row in rows
        ],
    )
