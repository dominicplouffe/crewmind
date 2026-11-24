"""Directives and action cards: the only way chat words change state (MSG-3, CHAT-6, CHAT-7,
P15, section 7.17)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Authority, Caller, platform_job
from nightsquad.catalog.define import operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.state_machine import NEW, StateMachine
from nightsquad.domain.conversation import service
from nightsquad.domain.conversation.operations import addressed_seats
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.agent import agent_of
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.projects import lifecycle
from nightsquad.domain.projects.access import view_of
from nightsquad.domain.projects.model import ProjectState
from nightsquad.domain.projects.operations import ProjectRef
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import ActionCard, Directive, Project, Seat

DIRECTIVE_CHANGED = event_type("directive.state_changed", "A directive changed state (7.17).")
CARD_CHANGED = event_type("action_card.state_changed", "An action card changed state (7.17).")
MSG_3 = rules.register(Rule("MSG-3", "Chat words change state only through a directive."))
DIRECTIVES_JOB = platform_job("dispatcher: directives")


class DirectiveState(StrEnum):
    ISSUED = "issued"
    WAITING = "waiting"
    DONE = "done"
    VOID = "void"


class CardState(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


D = DirectiveState
DIRECTIVE_MACHINE = StateMachine(
    "directive",
    "7.17-directive",
    [
        (NEW, D.ISSUED),
        (D.ISSUED, D.WAITING),
        (D.WAITING, D.ISSUED),
        (D.ISSUED, D.DONE),
        (D.ISSUED, D.VOID),
        (D.WAITING, D.VOID),
    ],
)
CARD_MACHINE = StateMachine(
    "action card",
    "7.17-card",
    [
        (NEW, CardState.OPEN),
        (CardState.OPEN, CardState.ACCEPTED),
        (CardState.OPEN, CardState.DISMISSED),
    ],
)


class DoInput(ProjectRef):
    instruction: str = Field(min_length=3, max_length=4000, description="What to do.")


class DirectiveItem(BaseModel):
    id: int
    to: str
    text: str
    state: str
    outcome: str | None
    at: datetime


class DirectiveList(BaseModel):
    items: list[DirectiveItem]


class CardItem(BaseModel):
    id: int
    by: str
    what: str
    estimated_tokens: int
    reversible: bool
    state: str


class CardList(BaseModel):
    items: list[CardItem]


class CardRef(ProjectRef):
    card_id: int = Field(description="The card's id.")


class AcceptInput(CardRef):
    edited: str | None = Field(
        default=None, description="An edited instruction, to replace the proposal."
    )


class ProposeInput(BaseModel):
    what: str = Field(
        min_length=10, max_length=2000, description="What you will do, in a sentence."
    )
    estimated_tokens: int = Field(ge=0, description="Your estimate of the tokens it will take.")
    reversible: bool = Field(description="Whether it can be undone.")


class DoneInput(BaseModel):
    directive_id: int = Field(description="The directive you carried out.")
    outcome: str = Field(min_length=10, max_length=2000, description="What you did.")


def _move(
    session: AsyncSession, row: Directive, target: DirectiveState, caller: Caller, now: datetime
) -> None:
    source = row.state
    DIRECTIVE_MACHINE.check(source, target)
    row.state = target
    append_event(
        session,
        type=DIRECTIVE_CHANGED,
        caller=caller,
        at=now,
        subject=("directive", str(row.id)),
        project_id=row.project_id,
        before={"state": source},
        after={"state": target},
    )


async def issue(
    session: AsyncSession,
    project: Project,
    seat: Seat,
    text: str,
    *,
    caller: Caller,
    now: datetime,
    card_id: int | None = None,
) -> Directive:
    """MSG-3: record the directive, echo it in the chat, and wake its addressee. On a held
    or paused project it waits until the project runs again (INV-20)."""
    if project.state in (ProjectState.STOPPED, ProjectState.DELETING, ProjectState.DRAFT):
        raise Refusal(
            "project_not_started",
            f"The project is {project.state}; a directive needs a started project.",
            rule=MSG_3.id,
            hint="Start the project first.",
        )
    DIRECTIVE_MACHINE.check(NEW, D.ISSUED)
    row = Directive(
        project_id=project.id,
        seat_id=seat.id,
        author_id=caller.actor_id,
        text=text,
        state=D.ISSUED,
        card_id=card_id,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    append_event(
        session,
        type=DIRECTIVE_CHANGED,
        caller=caller,
        at=now,
        subject=("directive", str(row.id)),
        project_id=project.id,
        after={"state": D.ISSUED, "to": seat.name, "text": text},
    )
    waiting = project.state != ProjectState.RUNNING
    if waiting:
        _move(session, row, D.WAITING, DIRECTIVES_JOB, now)
    else:
        _notify(session, row, seat, now)
    ceo = await ceo_of(session, project.id)
    if seat.id != ceo.id:
        notices.notify(
            session, project.id, ceo.id, "directive to another agent",
            f"The chairman directed {seat.display_name}: {text}", now,
        )  # fmt: skip
    await service.platform_line(
        session,
        project.id,
        f"Directive {row.id} to {seat.display_name}: {text}"
        + (f"\nIt waits until the project runs again (it is {project.state})." if waiting else ""),
        now,
        detail={"kind": "directive", "directive": row.id, "to": seat.name},
    )
    return row


def _notify(session: AsyncSession, row: Directive, seat: Seat, now: datetime) -> None:
    notices.notify(
        session,
        row.project_id,
        seat.id,
        "directive issued",
        f"Directive {row.id} from the chairman: {row.text}\nCarry it out, then report it "
        f"done with agent_complete_directive (directive_id={row.id}).",
        now,
        urgent=True,
    )


async def release_waiting(session: AsyncSession, project: Project, now: datetime) -> None:
    """Section 7.17: a waiting directive is issued again when the project runs again."""
    if project.state != ProjectState.RUNNING:
        return
    rows = await session.scalars(
        select(Directive).where(Directive.project_id == project.id, Directive.state == D.WAITING)
    )
    for row in rows:
        seat = await session.get(Seat, row.seat_id)
        assert seat is not None
        _move(session, row, D.ISSUED, DIRECTIVES_JOB, now)
        _notify(session, row, seat, now)


async def _void(session: AsyncSession, project: Project, now: datetime) -> None:
    rows = await session.scalars(
        select(Directive).where(
            Directive.project_id == project.id, Directive.state.in_([D.ISSUED, D.WAITING])
        )
    )
    for row in rows:
        _move(session, row, D.VOID, DIRECTIVES_JOB, now)


lifecycle.stop_hooks.append(_void)


def _item(row: Directive, seat_name: str) -> DirectiveItem:
    return DirectiveItem(
        id=row.id,
        to=seat_name,
        text=row.text,
        state=row.state,
        outcome=row.outcome,
        at=row.created_at,
    )


@operation(
    "directives.issue",
    summary="Tell an agent to act. `@name` at the start addresses an agent other than the CEO.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/do",
)
async def do(context: Context, payload: DoInput) -> DirectiveItem:
    """MSG-3, P15: `/do` is the explicit instruction to act. A plain message never is."""
    project = view_of(context).project
    addressed = await addressed_seats(context, project.id, payload.instruction.split(" ", 1)[0])
    seat = (
        await context.session.get(Seat, addressed[0])
        if addressed
        else await ceo_of(context.session, project.id)
    )
    assert seat is not None
    row = await issue(
        context.session, project, seat, payload.instruction, caller=context.caller, now=context.now
    )
    return _item(row, seat.name)


@operation(
    "directives.list",
    summary="List a project's directives and what became of them.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=frozenset({Principal.PERSON, Principal.MCP_CLIENT}),
    mcp_scope="read",
)
async def list_directives(context: Context, payload: ProjectRef) -> DirectiveList:
    rows = await context.session.execute(
        select(Directive, Seat)
        .join(Seat, Seat.id == Directive.seat_id)
        .where(Directive.project_id == payload.project_id)
        .order_by(Directive.id)
    )
    return DirectiveList(items=[_item(row, seat.name) for row, seat in rows.all()])


@operation(
    "agent.complete_directive",
    summary="Report a directive carried out, saying what you did.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=frozenset({Principal.AGENT_RUN}),
)
async def complete(context: Context, payload: DoneInput) -> DirectiveItem:
    """MSG-3: only the agent a directive addresses can report it done."""
    view = await agent_of(context)
    row = await context.session.get(Directive, payload.directive_id)
    if row is None or row.project_id != view.project.id or row.seat_id != view.seat.id:
        raise Refusal(
            "not_your_directive",
            "There is no directive with that id addressed to you.",
            kind=RefusalKind.FORBIDDEN,
            rule=MSG_3.id,
        )
    _move(context.session, row, D.DONE, context.caller, context.now)
    row.outcome, row.done_at = payload.outcome, context.now
    await service.platform_line(
        context.session,
        view.project.id,
        f"{view.seat.display_name} carried out directive {row.id}: {payload.outcome}",
        context.now,
        detail={"kind": "directive done", "directive": row.id},
    )
    return _item(row, view.seat.name)


def _card(row: ActionCard, seat_name: str) -> CardItem:
    return CardItem(
        id=row.id,
        by=seat_name,
        what=row.what,
        estimated_tokens=row.estimated_tokens,
        reversible=row.reversible,
        state=row.state,
    )


@operation(
    "agent.propose_action",
    summary="Propose to act on something said in chat. The chairman decides with one tap.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=frozenset({Principal.AGENT_RUN}),
)
async def propose(context: Context, payload: ProposeInput) -> CardItem:
    """CHAT-7: a card says what the agent will do, its estimated tokens and whether it can
    be undone. Posting a card is talk; it changes nothing until accepted (INV-23)."""
    view = await agent_of(context)
    CARD_MACHINE.check(NEW, CardState.OPEN)
    row = ActionCard(
        project_id=view.project.id,
        seat_id=view.seat.id,
        what=payload.what,
        estimated_tokens=payload.estimated_tokens,
        reversible=payload.reversible,
        state=CardState.OPEN,
        created_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    target = await service.channel(context.session, view.project.id, service.PROJECT_CHAT)
    waiting = await service.unanswered_from_people(context.session, view.seat)
    message = await service.post(
        context.session,
        target,
        author=service.Author.AGENT,
        author_id=view.seat.id,
        author_name=view.seat.name,
        body=f"I propose: {payload.what}\nEstimated {payload.estimated_tokens:,} tokens. "
        f"{'It can be undone.' if payload.reversible else 'It cannot be undone.'}",
        now=context.now,
        reply_to=waiting[0].id if waiting else None,
        run_id=view.run.id,
        detail={"kind": "action card", "card": row.id},
    )
    row.message_id = message.id
    context.record(
        CARD_CHANGED,
        subject=("action card", str(row.id)),
        project_id=view.project.id,
        after={"state": CardState.OPEN, "by": view.seat.name},
    )
    return _card(row, view.seat.name)


async def _open_card(context: Context, payload: CardRef) -> tuple[ActionCard, Seat]:
    row = await context.session.get(ActionCard, payload.card_id)
    if row is None or row.project_id != payload.project_id:
        raise Refusal(
            "card_not_found", "There is no action card with that id.", kind=RefusalKind.NOT_FOUND
        )
    seat = await context.session.get(Seat, row.seat_id)
    assert seat is not None
    return row, seat


@operation(
    "cards.accept",
    summary="Accept an agent's proposal (Do it), optionally edited. It becomes a directive.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def accept(context: Context, payload: AcceptInput) -> CardItem:
    """CHAT-7, MSG-3: "Do it" creates a directive to the agent that proposed."""
    row, seat = await _open_card(context, payload)
    CARD_MACHINE.check(row.state, CardState.ACCEPTED)
    row.state = CardState.ACCEPTED
    context.record(
        CARD_CHANGED,
        subject=("action card", str(row.id)),
        project_id=payload.project_id,
        before={"state": CardState.OPEN},
        after={"state": CardState.ACCEPTED},
    )
    await issue(
        context.session,
        view_of(context).project,
        seat,
        payload.edited or row.what,
        caller=context.caller,
        now=context.now,
        card_id=row.id,
    )
    return _card(row, seat.name)


@operation(
    "cards.dismiss",
    summary="Dismiss an agent's proposal (Not now).",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def dismiss(context: Context, payload: CardRef) -> CardItem:
    row, seat = await _open_card(context, payload)
    CARD_MACHINE.check(row.state, CardState.DISMISSED)
    row.state = CardState.DISMISSED
    context.record(
        CARD_CHANGED,
        subject=("action card", str(row.id)),
        project_id=payload.project_id,
        before={"state": CardState.OPEN},
        after={"state": CardState.DISMISSED},
    )
    return _card(row, seat.name)


@operation(
    "cards.list",
    summary="List the action cards agents have proposed.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=frozenset({Principal.PERSON, Principal.MCP_CLIENT}),
    mcp_scope="read",
)
async def list_cards(context: Context, payload: ProjectRef) -> CardList:
    rows = await context.session.execute(
        select(ActionCard, Seat)
        .join(Seat, Seat.id == ActionCard.seat_id)
        .where(ActionCard.project_id == payload.project_id)
        .order_by(ActionCard.id)
    )
    return CardList(items=[_card(row, seat.name) for row, seat in rows.all()])
