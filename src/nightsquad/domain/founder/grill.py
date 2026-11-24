"""Grilling a document in a running project: the CEO interviews the chairman before
anything in it becomes work (FND-16)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import PERSON_AND_MCP, Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.agent import agent_of
from nightsquad.domain.execution.agent_operations import work_run_only
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.founder import drafting as state
from nightsquad.domain.founder import model as m
from nightsquad.domain.founder.model import DRAFTING_MACHINE, D
from nightsquad.domain.founder.operations import (
    DRAFTING_CHANGED,
    DRAFTING_EDITED,
    LedgerLine,
    QuestionView,
)
from nightsquad.domain.founder.tools import PAGE_CHARACTERS, Ask, Extracted, Toolbox
from nightsquad.domain.memory.pinned import ORDER_ACTIVE
from nightsquad.domain.planning.agent_operations import new_scope_hooks
from nightsquad.domain.projects.access import view_of
from nightsquad.domain.projects.operations import ProjectRef
from nightsquad.storage.models import (
    ClosedDecision,
    Drafting,
    GrillItem,
    Message,
    Project,
    Requirement,
    StandingOrder,
)

FND_16 = rules.register(
    Rule(
        "FND-16",
        "While a document is being grilled, the CEO proposes no new scope from it.",
    )
)
AGENT = frozenset({Principal.AGENT_RUN})
DOCUMENT_MAX = 200_000
CONFLICT = "conflict"
KINDS: dict[str, type[Any]] = {
    "order": StandingOrder,
    "decision": ClosedDecision,
    "requirement": Requirement,
}


class GrillInput(ProjectRef):
    document: str | None = Field(
        default=None,
        max_length=DOCUMENT_MAX,
        description="The text to grill. Left out: your last message in the project chat.",
    )


class GrillAnswer(ProjectRef):
    question_id: int = Field(description="The question's id.")
    answer: str = Field(
        default="", max_length=4000, description='Empty or "yes" accepts the recommendation.'
    )


class PassageView(BaseModel):
    id: int
    kind: str
    passage: str
    problem: str | None
    note: str | None
    state: str


class GrillView(BaseModel):
    grilling: bool = Field(description="Whether a document is being grilled now.")
    state: str | None
    document: str | None = Field(description="The first page of the document.")
    characters: int
    items: list[PassageView]
    questions: list[QuestionView]
    ledger: list[LedgerLine]
    can_confirm: bool


class Conflicting(Extracted):
    conflicts_with: str | None = Field(
        default=None,
        description="For a conflict: `order:<id>`, `decision:<id>` or `requirement:<id>`.",
    )


class ExtractInput(BaseModel):
    items: list[Conflicting] = Field(min_length=1)


class AskInput(BaseModel):
    item_id: int = Field(description="The passage this question settles.")
    text: str = Field(min_length=1, max_length=600)
    options: list[str]
    recommended: int | None = None
    changes: str = Field(min_length=1, max_length=400)


async def open_grilling(session: AsyncSession, project_id: str) -> Drafting | None:
    return await session.scalar(
        select(Drafting).where(
            Drafting.project_id == project_id,
            Drafting.kind == m.GRILL,
            Drafting.state == D.DRAFTING,
        )
    )


async def refuse_new_scope(session: AsyncSession, project: Project) -> None:
    """FND-16: nothing from the document becomes a requirement or a bet until the
    chairman confirms the ledger. Work under existing scope goes on."""
    if await open_grilling(session, project.id) is not None:
        raise Refusal(
            "grilling_in_progress",
            "The chairman asked for a document to be grilled. Until they confirm the "
            "ledger, you propose no new scope.",
            rule=FND_16.id,
            hint="Finish the interview with agent_grill_ask, then wait for the chairman.",
        )


async def _wanted(session: AsyncSession, project_id: str) -> Drafting:
    row = await open_grilling(session, project_id)
    if row is None:
        raise Refusal(
            "no_grilling",
            "No document is being grilled in this project.",
            kind=RefusalKind.NOT_FOUND,
            rule=FND_16.id,
            hint="The chairman starts one with /grill.",
        )
    return row


async def _view(session: AsyncSession, row: Drafting | None) -> GrillView:
    if row is None:
        return GrillView(
            grilling=False, state=None, document=None, characters=0, items=[], questions=[],
            ledger=[], can_confirm=False,
        )  # fmt: skip
    items = list(
        await session.scalars(
            select(GrillItem).where(GrillItem.drafting_id == row.id).order_by(GrillItem.id)
        )
    )
    questions = await state.open_question(session, row.id)
    document = row.document or ""
    return GrillView(
        grilling=row.state == D.DRAFTING,
        state=row.state,
        document=document[:PAGE_CHARACTERS],
        characters=len(document),
        items=[
            PassageView(
                id=item.id,
                kind=item.kind,
                passage=item.passage,
                problem=item.problem,
                note=item.note,
                state=item.state,
            )
            for item in items
        ],
        questions=[
            QuestionView(
                id=question.id,
                settles=question.settles,
                text=question.text,
                options=[str(option) for option in question.options],
                recommended=question.recommended,
                changes=question.changes,
            )
            for question in questions
        ],
        ledger=[
            LedgerLine(
                settles=entry.settles,
                value=entry.value,
                source=entry.source,
                passage=entry.passage,
            )
            for entry in await state.ledger(session, row.id)
        ],
        can_confirm=bool(items)
        and not questions
        and not any(item.state == m.ITEM_OPEN for item in items)
        and row.state == D.DRAFTING,
    )


def _tell_ceo(
    session: AsyncSession, project_id: str, ceo_id: str, body: str, now: datetime
) -> None:
    notices.notify(session, project_id, ceo_id, "grilling", body, now, urgent=True)


@operation(
    "grill.start",
    summary="Have the CEO grill a document, or your last message, before it becomes work.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/grill",
)
async def start(context: Context, payload: GrillInput) -> GrillView:
    """FND-16: the CEO lists what the document says, asks about each contradiction, vague
    term, possible example, unverifiable requirement and conflict with what already
    stands, and proposes nothing from it until you confirm the ledger."""
    session, project = context.session, view_of(context).project
    if await open_grilling(session, project.id) is not None:
        raise Refusal(
            "already_grilling",
            "A document is already being grilled in this project.",
            rule=FND_16.id,
            hint="Confirm it with `grill confirm`, or answer its open question.",
        )
    document = payload.document
    if document is None:
        last = await session.scalar(
            select(Message)
            .where(
                Message.project_id == project.id,
                Message.author_kind == "person",
                Message.author_id == context.caller.actor_id,
                Message.body.not_like("/%"),
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        if last is None:
            raise Refusal(
                "nothing_to_grill",
                "You have written nothing in this chat to grill.",
                rule=FND_16.id,
                hint="Give the text: /grill <text>.",
            )
        document = last.body
    DRAFTING_MACHINE.check(m.NEW, D.DRAFTING)
    row = state.new(context.caller.actor_id, m.GRILL, context.now)
    row.project_id, row.document, row.turn = project.id, document, m.IDLE
    session.add(row)
    await session.flush()
    context.record(
        DRAFTING_CHANGED,
        subject=("drafting", row.id),
        project_id=project.id,
        after={"state": D.DRAFTING, "kind": m.GRILL},
    )
    ceo = await ceo_of(session, project.id)
    _tell_ceo(
        session,
        project.id,
        ceo.id,
        "The chairman asked you to grill a document before anything in it becomes work. "
        "Read it with agent_grill. List what it says with agent_grill_extract: every goal, "
        "requirement, constraint, number, date, name and example, and for each the problem "
        "it has, if any: a contradiction, a vague term, a number that may be an example, a "
        "requirement nobody can verify, or a conflict with a standing order, a closed "
        "decision or existing scope. Then ask about each problem with agent_grill_ask, one "
        "at a time. Propose nothing from the document until the chairman confirms.",
        context.now,
    )
    await conversation.platform_line(
        session,
        project.id,
        f"Grilling started on a document of {len(document):,} characters. The CEO will ask "
        "about it before anything in it becomes work. Other work goes on.",
        context.now,
        detail={"kind": "grilling", "drafting": row.id},
    )
    return await _view(session, row)


@operation(
    "grill.show",
    summary="Show the grilling in this project: the passages, the questions and the ledger.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show(context: Context, payload: ProjectRef) -> GrillView:
    row = await context.session.scalar(
        select(Drafting)
        .where(Drafting.project_id == payload.project_id, Drafting.kind == m.GRILL)
        .order_by(Drafting.created_at.desc())
        .limit(1)
    )
    return await _view(context.session, row)


@operation(
    "grill.answer",
    summary="Answer a question the CEO asked while grilling a document.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def answer(context: Context, payload: GrillAnswer) -> GrillView:
    """FND-16, FND-5: the answer goes into the ledger with the passage it settles. A
    ruling that changes a standing order or a closed decision is still made through that
    order or decision (MSG-4, MSG-5)."""
    session = context.session
    row = await _wanted(session, payload.project_id)
    question = await state.answer(session, row, payload.question_id, payload.answer, context.now)
    row.turn = m.IDLE
    context.record(
        DRAFTING_EDITED,
        subject=("drafting", row.id),
        project_id=payload.project_id,
        after={"what": "answered", "settles": question.settles},
    )
    item = await session.get(GrillItem, int(question.settles.removeprefix(state.ITEM)))
    ceo = await ceo_of(session, payload.project_id)
    _tell_ceo(
        session,
        payload.project_id,
        ceo.id,
        f"The chairman answered your grilling question {question.id}: {question.answer}",
        context.now,
    )
    if item is not None and item.problem == CONFLICT:
        await conversation.platform_line(
            session,
            payload.project_id,
            "That answer settles a conflict with what already stands. If it changes a "
            "standing order or a closed decision, change that too: /retire the order, or "
            "reopen the decision.",
            context.now,
            detail={"kind": "grilling conflict", "item": item.id},
        )
    return await _view(session, row)


@operation(
    "grill.accept_rest",
    summary="Tell the CEO to use its recommendations for every passage still open.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def accept_rest(context: Context, payload: ProjectRef) -> GrillView:
    row = await _wanted(context.session, payload.project_id)
    recorded = await state.accept_the_rest(context.session, row, context.now)
    row.turn = m.IDLE
    context.record(
        DRAFTING_EDITED,
        subject=("drafting", row.id),
        project_id=payload.project_id,
        after={"what": "accepted the rest", "recorded": recorded},
    )
    return await _view(context.session, row)


@operation(
    "grill.confirm",
    summary="Confirm the ledger of a grilled document, so the CEO may propose it as scope.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def confirm(context: Context, payload: ProjectRef) -> GrillView:
    """FND-16: nothing is confirmed while a passage or a question is open. After this the
    CEO proposes scope from the ledger under the usual authority."""
    session = context.session
    row = await _wanted(session, payload.project_id)
    shown = await _view(session, row)
    if not shown.can_confirm:
        raise Refusal(
            "grilling_not_finished",
            "The CEO has not listed the document yet."
            if not shown.items
            else "Passages or questions are still open.",
            rule=FND_16.id,
            hint="Answer the open question, or use `grill accept-rest`.",
        )
    DRAFTING_MACHINE.check(row.state, D.CREATED)
    context.record(
        DRAFTING_CHANGED,
        subject=("drafting", row.id),
        project_id=payload.project_id,
        before={"state": row.state},
        after={"state": D.CREATED},
    )
    row.state = D.CREATED
    ledger = "\n".join(
        f"- {entry.passage or entry.settles}: {entry.value}" for entry in shown.ledger
    )
    ceo = await ceo_of(session, payload.project_id)
    _tell_ceo(
        session,
        payload.project_id,
        ceo.id,
        "The chairman confirmed the ledger of the grilled document. Propose scope from it "
        f"under your usual authority.\n{ledger}",
        context.now,
    )
    await conversation.platform_line(
        session,
        payload.project_id,
        "The grilling is confirmed. The CEO may now propose scope from the document.",
        context.now,
        detail={"kind": "grilling confirmed", "drafting": row.id},
    )
    return await _view(session, row)


async def _box(context: Context) -> tuple[Toolbox, Drafting]:
    view = await agent_of(context)
    work_run_only(view)
    row = await _wanted(context.session, view.project.id)
    return Toolbox(context, row), row


@operation(
    "agent.grill",
    summary="Read the document the chairman asked you to grill, and where the grilling stands.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def read(context: Context, payload: Empty) -> GrillView:
    view = await agent_of(context)
    return await _view(context.session, await open_grilling(context.session, view.project.id))


@operation(
    "agent.grill_extract",
    summary="List what the document says, passage by passage, and the problem each has.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def extract(context: Context, payload: ExtractInput) -> GrillView:
    """FND-15, FND-16: each passage quotes the document. A conflict names the standing
    order, closed decision or requirement it conflicts with, and that must exist."""
    box, row = await _box(context)
    for item in payload.items:
        if item.problem != CONFLICT:
            continue
        kind, _, number = (item.conflicts_with or "").partition(":")
        target: Any = (
            await context.session.get(KINDS[kind], int(number))
            if kind in KINDS and number.isdigit()
            else None
        )
        live = target is not None and target.project_id == row.project_id
        if isinstance(target, StandingOrder):
            live = live and target.state == ORDER_ACTIVE
        if not live:
            raise Refusal(
                "conflict_with_nothing",
                "A conflict names what it conflicts with: `order:<id>`, `decision:<id>` or "
                "`requirement:<id>` of this project.",
                rule=FND_16.id,
            )
    await box.extract(
        [
            Extracted.model_validate(item.model_dump(exclude={"conflicts_with"}))
            for item in payload.items
        ]
    )
    for item in payload.items:
        if item.conflicts_with:
            stored = await context.session.scalar(
                select(GrillItem)
                .where(GrillItem.drafting_id == row.id, GrillItem.passage == item.passage)
                .order_by(GrillItem.id.desc())
                .limit(1)
            )
            if stored is not None:
                stored.note = f"Conflicts with {item.conflicts_with}. {item.note or ''}".strip()
    return await _view(context.session, row)


@operation(
    "agent.grill_ask",
    summary="Ask the chairman about one passage of the document you are grilling.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def ask(context: Context, payload: AskInput) -> GrillView:
    """FND-16, FND-3: a chat card with a recommended answer, no deadline and no default.
    One at a time, about an open passage only."""
    box, row = await _box(context)
    question: dict[str, Any] = {
        "settles": f"{state.ITEM}{payload.item_id}",
        **payload.model_dump(exclude={"item_id"}),
    }
    asked = await box.ask(Ask.model_validate({"questions": [question]}).model_dump())
    waiting = await state.open_question(context.session, row.id)
    card = next(q for q in waiting if q.id == asked["asked"][0])
    options = "\n".join(
        f"{chr(ord('a') + index)}. {option}"
        + (" (recommended)" if index == card.recommended else "")
        for index, option in enumerate(card.options)
    )
    await conversation.platform_line(
        context.session,
        row.project_id or "",
        f"The CEO asks, about the document: {card.text}\n{options}\nIt changes: {card.changes}",
        context.now,
        detail={"kind": "grill question", "question": card.id, "drafting": row.id},
    )
    return await _view(context.session, row)


new_scope_hooks.append(refuse_new_scope)
