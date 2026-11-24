"""What agents do with decision items through the agent API (IF-6.3, HUM-4, HUM-5,
HUM-7, GOV-8). An agent files and withdraws; it never decides."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.decisions import asks, flags, items, mistakes, reviews, spend
from nightsquad.domain.decisions.model import LIVE
from nightsquad.domain.decisions.operations import ItemList, ItemView, view
from nightsquad.domain.execution.agent import agent_of
from nightsquad.domain.execution.agent_operations import work_run_only
from nightsquad.domain.execution.model import SeatKind
from nightsquad.services import services_of
from nightsquad.storage.models import DecisionItem

AGENT = frozenset({Principal.AGENT_RUN})


class QuestionInput(BaseModel):
    question: str = Field(min_length=10, max_length=1000, description="What you ask.")
    why: str = Field(max_length=2000, description="Why the answer matters.")
    options: list[str] = Field(max_length=4, description="Up to 4 options.")
    recommended: int = Field(ge=1, description="The number of the option you recommend.")
    default: str = Field(max_length=2000, description="What you will do now, without waiting.")
    concerns: str = Field(
        description="The decision it is about: accept_scope, change_scope, date, "
        "reserve_draw, or other."
    )
    window_hours: int | None = Field(default=None, ge=1, le=72, description="How long it waits.")


class AssistInput(BaseModel):
    what: Literal["captcha", "two-factor code", "identity check", "login", "other human step"]
    step: str = Field(min_length=10, max_length=2000, description="Exactly what to do.")
    task_id: int | None = Field(default=None, description="The task that waits on it.")


class HeadsUpInput(BaseModel):
    text: str = Field(min_length=10, max_length=300, description="What you decided or did.")


class Basis(BaseModel):
    kind: Literal["command", "artifact", "evidence"]
    ref: str = Field(min_length=1, max_length=2000, description="The output, name or id.")


class ApprovalInput(BaseModel):
    kind: Literal["spend", "legal", "tool permission"]
    recommendation: str = Field(max_length=300, description="What you ask for, in a sentence.")
    if_declined: str = Field(min_length=10, max_length=1000, description="What happens if not.")
    amount: float | None = Field(default=None, gt=0, description="Spend only: the amount.")
    tool: str | None = Field(default=None, max_length=200, description="Tool permission only.")
    basis: Basis | None = Field(default=None, description="Where a figure comes from.")


class ItemRef(BaseModel):
    item_id: int = Field(description="The item's id.")


class ReworkInput(ItemRef):
    what: str = Field(min_length=10, max_length=2000, description="What you redid.")


class PurchaseInput(BaseModel):
    what: str = Field(min_length=5, max_length=500, description="What is bought, from whom.")
    amount: float = Field(gt=0, description="The price, in the project's currency.")


class PurchaseRef(BaseModel):
    purchase_id: int
    bought: bool = Field(description="True when it was bought; false to cancel it.")


class PurchaseView(BaseModel):
    id: int
    what: str
    amount: float
    currency: str
    state: str = Field(description="committed, bought or cancelled.")
    committed_this_month: float
    monthly_cap: float


async def _purchase(context: Context, project: Any, row: Any) -> PurchaseView:
    found = await spend.limits(context.session, services_of(context).settings, project, context.now)
    return PurchaseView(
        id=row.id,
        what=row.what,
        amount=row.amount_cents / spend.CENTS,
        currency=found.currency,
        state=row.state,
        committed_this_month=found.committed_cents / spend.CENTS,
        monthly_cap=found.cap_cents / spend.CENTS,
    )


@operation(
    "agent.ask_question",
    summary="Ask the chairman a question and carry on at once on your stated default.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def ask_question(context: Context, payload: QuestionInput) -> ItemView:
    """HUM-4, HUM-5, SPD-5: never about a decision you hold; at most `question.max_open`."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await asks.ask(
        context.session,
        services_of(context).settings,
        view_.project,
        context.caller,
        question=payload.question,
        why=payload.why,
        options=payload.options,
        recommended=payload.recommended,
        default=payload.default,
        concerns=payload.concerns,
        window_hours=payload.window_hours,
        now=context.now,
    )
    return view(item)


@operation(
    "agent.file_assist",
    summary="Ask for a step only a human can do. The task waits; the project does not.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def file_assist(context: Context, payload: AssistInput) -> ItemView:
    """HUM-7: any agent may file one."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await items.file(
        context.session,
        services_of(context).settings,
        view_.project,
        asks.ASSIST,
        filer=context.caller,
        fields={"what": payload.what, "step": payload.step, "task_id": payload.task_id},
        recommendation=f"Do this step for {view_.seat.name}, then mark it done.",
        if_declined="The task that needs it is blocked; the rest of the project goes on.",
        now=context.now,
    )
    return view(item)


@operation(
    "agent.post_heads_up",
    summary="Tell the chairman what you decided or did. It asks for nothing.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def post_heads_up(context: Context, payload: HeadsUpInput) -> ItemView:
    """HUM-2, HUM-4: a heads-up has no deadline and no default."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await items.file(
        context.session,
        services_of(context).settings,
        view_.project,
        asks.HEADS_UP,
        filer=context.caller,
        fields={"text": payload.text},
        recommendation=payload.text,
        if_declined="",
        now=context.now,
    )
    return view(item)


@operation(
    "agent.request_approval",
    summary="Ask the chairman to approve spend, a legal step or a tool. A figure needs its basis.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def request_approval(context: Context, payload: ApprovalInput) -> ItemView:
    """HUM-2, HUM-3, WRK-10: spend and legal are the CEO's to ask; any agent may ask for a
    tool. These stay with the chairman at every authority setting."""
    view_ = await agent_of(context)
    work_run_only(view_)
    kind = f"approval: {payload.kind}"
    if payload.kind != "tool permission" and view_.seat.kind != SeatKind.CEO:
        raise Refusal(
            "only_the_ceo_asks",
            f"Only the CEO asks for a {payload.kind} approval.",
            kind=RefusalKind.FORBIDDEN,
        )
    services = services_of(context)
    fields: dict[str, Any] = {}
    if payload.kind == "spend":
        found = await spend.limits(context.session, services.settings, view_.project, context.now)
        fields = {"amount": payload.amount, "currency": found.currency}
        if payload.amount is None:
            raise Refusal("spend_needs_an_amount", "A spend approval names its amount.")
    elif payload.kind == "tool permission":
        fields = {"tool": payload.tool or ""}
        if not payload.tool:
            raise Refusal("tool_needs_a_name", "A tool-permission approval names the tool.")
    item = await items.file(
        context.session,
        services.settings,
        view_.project,
        kind,
        filer=context.caller,
        fields=fields,
        recommendation=payload.recommendation,
        if_declined=payload.if_declined,
        basis=payload.basis.model_dump() if payload.basis else None,
        now=context.now,
    )
    return view(item)


@operation(
    "agent.items",
    summary="List the open decision items of this project.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def list_items(context: Context, payload: Empty) -> ItemList:
    """HUM-1: agents see what waits, so they do not ask twice."""
    view_ = await agent_of(context)
    rows = await context.session.scalars(
        select(DecisionItem)
        .where(DecisionItem.project_id == view_.project.id, DecisionItem.state.in_(LIVE))
        .order_by(DecisionItem.id)
    )
    return ItemList(items=[view(row) for row in rows])


@operation(
    "agent.withdraw_item",
    summary="Withdraw an item you filed that no longer needs an answer.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def withdraw_item(context: Context, payload: ItemRef) -> ItemView:
    """7.5: only the filer withdraws."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await items.get(context.session, view_.project.id, payload.item_id)
    await items.withdraw(context.session, item, context.caller, context.now)
    return view(item)


@operation(
    "agent.record_rework",
    summary="Record what you redid because the chairman's answer differed from your default.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def record_rework(context: Context, payload: ReworkInput) -> ItemView:
    """SPD-5: rework is recorded against the question."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await items.get(context.session, view_.project.id, payload.item_id)
    await asks.record_rework(context.session, item, context.caller, payload.what)
    context.record(
        items.ITEM_EDITED,
        subject=("item", str(item.id)),
        project_id=view_.project.id,
        after={"rework": payload.what},
    )
    return view(item)


@operation(
    "agent.declare_purchase",
    summary="Declare a real-world purchase before you make it.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def declare_purchase(context: Context, payload: PurchaseInput) -> PurchaseView:
    """GOV-8, INV-10: refused past the monthly cap; needs an approval at the threshold."""
    view_ = await agent_of(context)
    work_run_only(view_)
    row = await spend.declare(
        context.session,
        services_of(context).settings,
        view_.project,
        view_.seat,
        context.caller,
        what=payload.what,
        amount=payload.amount,
        now=context.now,
    )
    return await _purchase(context, view_.project, row)


@operation(
    "agent.finish_purchase",
    summary="Say a purchase you declared was made, or cancel it.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def finish_purchase(context: Context, payload: PurchaseRef) -> PurchaseView:
    """GOV-8: a cancelled purchase no longer counts against the cap."""
    view_ = await agent_of(context)
    work_run_only(view_)
    row = await spend.finish(
        context.session,
        view_.project,
        view_.seat,
        context.caller,
        payload.purchase_id,
        payload.bought,
        context.now,
    )
    return await _purchase(context, view_.project, row)


class RaiseInput(ItemRef):
    proposal: str = Field(max_length=2000, description="What you propose to do about it.")


class MistakeInput(ItemRef):
    what_was_wrong: str = Field(max_length=2000)
    cause: str = Field(max_length=2000)
    fix: str = Field(max_length=2000)
    prevention: str = Field(max_length=500, description="Kept as a pinned lesson.")


class NarrativeInput(ItemRef):
    text: str = Field(max_length=10_000, description="Answer each item of the last plan.")


@operation(
    "agent.raise_flag",
    summary="Raise a flag in the chat with what you propose to do about it.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def raise_flag(context: Context, payload: RaiseInput) -> ItemView:
    """HUM-6: raising does not close a state flag; only its condition clearing does."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await items.get(context.session, view_.project.id, payload.item_id)
    await flags.raise_flag(
        context.session, view_.project, item, view_.seat, context.caller, payload.proposal,
        context.now,
    )  # fmt: skip
    return view(item)


@operation(
    "agent.file_mistake_report",
    summary="File a mistake report you owe: what was wrong, the cause, the fix, the prevention.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.IRREVERSIBLE,
    principals=AGENT,
)
async def file_mistake_report(context: Context, payload: MistakeInput) -> ItemView:
    """HUM-8: filed once; the cost is the platform's number; the prevention is pinned."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await items.get(context.session, view_.project.id, payload.item_id)
    await mistakes.file_report(
        context.session,
        item,
        context.caller,
        {
            "what_was_wrong": payload.what_was_wrong,
            "cause": payload.cause,
            "fix": payload.fix,
            "prevention": payload.prevention,
        },
        context.now,
    )
    return view(item)


@operation(
    "agent.write_review_narrative",
    summary="Add your narrative to an open status review.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def write_review_narrative(context: Context, payload: NarrativeInput) -> ItemView:
    """HUM-9: the numbers are the platform's; the narrative is the CEO's."""
    view_ = await agent_of(context)
    work_run_only(view_)
    item = await items.get(context.session, view_.project.id, payload.item_id)
    await reviews.write_narrative(context.session, item, context.caller, payload.text, context.now)
    return view(item)
