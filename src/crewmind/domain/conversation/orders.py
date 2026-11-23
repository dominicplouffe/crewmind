"""Standing orders: the chairman says it once, and every run of every agent carries it
(MSG-4, CHAT-8, MEM-1, section 7.17)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW, StateMachine
from crewmind.domain.accounts.people import person_or_refuse
from crewmind.domain.conversation import service
from crewmind.domain.conversation.service import Author
from crewmind.domain.execution.agent import agent_of
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.memory import pinned
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import Message, StandingOrder

MSG_4 = rules.register(
    Rule("MSG-4", "Only the chairman confirms or retires a standing order; 25 may be active.")
)
ORDER_CHANGED = event_type("standing_order.state_changed", "A standing order changed state.")

MAX_ACTIVE = 25  # MSG-4
MAX_CHARACTERS = 400  # MSG-4


class OrderState(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    DISCARDED = "discarded"
    RETIRED = "retired"


S = OrderState
ORDER_MACHINE = StateMachine(
    "standing order",
    "7.17-order",
    [(NEW, S.PROPOSED), (S.PROPOSED, S.ACTIVE), (S.PROPOSED, S.DISCARDED), (S.ACTIVE, S.RETIRED)],
)


class PinInput(ProjectRef):
    what: str = Field(
        min_length=1,
        max_length=MAX_CHARACTERS,
        description="The order in one sentence, or the id of a message of yours to pin.",
    )


class OrderRef(ProjectRef):
    order_id: int = Field(description="The order's id, from `orders list`.")


class ConfirmInput(OrderRef):
    text: str | None = Field(
        default=None, max_length=MAX_CHARACTERS, description="Your edited sentence, if any."
    )


class ProposeOrderInput(BaseModel):
    text: str = Field(
        min_length=10, max_length=MAX_CHARACTERS, description="The order, in one sentence."
    )


class OrderItem(BaseModel):
    id: int
    text: str
    state: str
    proposed_by: str
    being_shortened: bool = Field(description="A shorter sentence is being written for you.")
    note: str | None = Field(default=None, description="Something for you to act on, if any.")


class OrderList(BaseModel):
    items: list[OrderItem]


def _item(row: StandingOrder, note: str | None = None) -> OrderItem:
    return OrderItem(
        id=row.id,
        text=row.text,
        state=row.state,
        proposed_by=row.proposed_by,
        being_shortened=row.shorten and row.state == S.PROPOSED,
        note=note,
    )


def _move(context: Context, row: StandingOrder, target: OrderState) -> None:
    ORDER_MACHINE.check(row.state, target)
    before = row.state
    row.state = target
    context.record(
        ORDER_CHANGED,
        subject=("standing_order", str(row.id)),
        project_id=row.project_id,
        before={"state": before},
        after={"state": target, "text": row.text},
    )


def first_sentences(text: str, most: int = MAX_CHARACTERS) -> str:
    """The start of a long message, cut at the last sentence end that fits."""
    if len(text) <= most:
        return text
    cut = text[:most]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind("\n"))
    return cut[: end + 1].strip() if end > 0 else cut.rsplit(" ", 1)[0]


async def _order(context: Context, payload: OrderRef) -> StandingOrder:
    row = await context.session.get(StandingOrder, payload.order_id)
    if row is None or row.project_id != payload.project_id:
        raise Refusal(
            "order_not_found",
            f"There is no standing order {payload.order_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            hint="List them with `orders list`.",
        )
    return row


async def _activate(context: Context, row: StandingOrder) -> str | None:
    active = await context.session.scalar(
        select(func.count())
        .select_from(StandingOrder)
        .where(StandingOrder.project_id == row.project_id, StandingOrder.state == S.ACTIVE)
    )
    if (active or 0) >= MAX_ACTIVE:
        raise Refusal(
            "too_many_orders",
            f"{MAX_ACTIVE} standing orders are active, which is the most a project may have.",
            rule=MSG_4.id,
            hint="Retire one with `/unpin <id>` first.",
        )
    _move(context, row, S.ACTIVE)
    row.confirmed_at = context.now
    row.shorten = False
    project = view_of(context).project
    await service.platform_line(
        context.session,
        project.id,
        f"Standing order {row.id}: {row.text}\nEvery agent has it in every run from now on.",
        context.now,
        detail={"kind": "standing order", "order": row.id},
    )
    ceo = await ceo_of(context.session, project.id)
    return await pinned.note_if_over(
        context.session, services_of(context).settings, project, ceo, context.now
    )


@operation(
    "orders.pin",
    summary="Pin a standing order: one sentence every agent follows in every run.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/pin",
)
async def pin(context: Context, payload: PinInput) -> OrderItem:
    """MSG-4, CHAT-8: `/pin <sentence>` is the chairman's own words and is active at once.
    `/pin <message id>` proposes that message as an order for the chairman to confirm or
    edit; a message too long for one order is cut to its opening and marked for shortening."""
    person = await person_or_refuse(context.session, context.caller.actor_id)
    own_words = not payload.what.strip().isdigit()
    text, message_id, shorten = payload.what.strip(), None, False
    if not own_words:
        message = await context.session.get(Message, int(text))
        if (
            message is None
            or message.project_id != payload.project_id
            or message.author_kind != Author.PERSON
        ):
            raise Refusal(
                "not_a_persons_message",
                f"Message {text} is not a person's message in this project.",
                kind=RefusalKind.NOT_FOUND,
                rule=MSG_4.id,
                hint="Pin one of your own messages, or write the order after /pin.",
            )
        message_id, shorten = message.id, len(message.body) > MAX_CHARACTERS
        text = first_sentences(message.body)
    ORDER_MACHINE.check(NEW, S.PROPOSED)
    row = StandingOrder(
        project_id=payload.project_id,
        text=text,
        state=S.PROPOSED,
        message_id=message_id,
        proposed_by=person.name,
        shorten=shorten,
        created_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    context.record(
        ORDER_CHANGED,
        subject=("standing_order", str(row.id)),
        project_id=row.project_id,
        after={"state": S.PROPOSED, "text": text},
    )
    note = await _activate(context, row) if own_words else None
    return _item(row, note)


@operation(
    "orders.confirm",
    summary="Confirm a proposed standing order, with your edit if you have one.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def confirm(context: Context, payload: ConfirmInput) -> OrderItem:
    """MSG-4: only the chairman makes an order active, as proposed or in their own edit."""
    row = await _order(context, payload)
    if payload.text is not None:
        row.text = payload.text.strip()
    return _item(row, await _activate(context, row))


@operation(
    "orders.discard",
    summary="Discard a proposed standing order.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def discard(context: Context, payload: OrderRef) -> OrderItem:
    row = await _order(context, payload)
    _move(context, row, S.DISCARDED)
    return _item(row)


@operation(
    "orders.retire",
    summary="Retire a standing order. Agents are told it is no longer in force.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/unpin",
)
async def retire(context: Context, payload: OrderRef) -> OrderItem:
    """MSG-4: a retired order stays listed as retired, so agents know it is dead."""
    row = await _order(context, payload)
    _move(context, row, S.RETIRED)
    row.retired_at = context.now
    await service.platform_line(
        context.session,
        row.project_id,
        f"Standing order {row.id} is retired: {row.text}",
        context.now,
        detail={"kind": "standing order retired", "order": row.id},
    )
    return _item(row)


@operation(
    "orders.list",
    summary="List a project's standing orders: proposed, active and retired.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_orders(context: Context, payload: ProjectRef) -> OrderList:
    rows = await context.session.scalars(
        select(StandingOrder)
        .where(StandingOrder.project_id == payload.project_id, StandingOrder.state != S.DISCARDED)
        .order_by(StandingOrder.id)
    )
    return OrderList(items=[_item(row) for row in rows])


@operation(
    "agent.propose_order",
    summary="Propose a standing order to the chairman. Only the chairman can confirm it.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=frozenset({Principal.AGENT_RUN}),
)
async def propose(context: Context, payload: ProposeOrderInput) -> OrderItem:
    """MSG-4: the CEO may propose an order. A proposal is talk: nothing is in force until
    the chairman confirms it (INV-23)."""
    view = await agent_of(context)
    ORDER_MACHINE.check(NEW, S.PROPOSED)
    row = StandingOrder(
        project_id=view.project.id,
        text=payload.text.strip(),
        state=S.PROPOSED,
        message_id=None,
        proposed_by=view.seat.name,
        created_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    context.record(
        ORDER_CHANGED,
        subject=("standing_order", str(row.id)),
        project_id=row.project_id,
        after={"state": S.PROPOSED, "text": row.text},
    )
    await service.platform_line(
        context.session,
        view.project.id,
        f"{view.seat.display_name} proposes a standing order: {row.text}\n"
        f"Confirm it with `orders confirm`, or discard it. It is not in force yet.",
        context.now,
        detail={"kind": "standing order proposed", "order": row.id},
    )
    return _item(row)
