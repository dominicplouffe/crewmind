"""What agents put in front of the chairman: questions, assists, heads-ups and approvals
(HUM-2 to HUM-5, HUM-7, SPD-5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.decisions import items
from crewmind.domain.decisions.items import HUM_4, Kind, Settling
from crewmind.domain.decisions.model import ItemState
from crewmind.domain.execution import notices
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import authority
from crewmind.domain.settings.service import SettingsService
from crewmind.domain.work import tasks
from crewmind.domain.work.model import TaskState
from crewmind.storage.models import DecisionItem, Project, Seat, Task

HUM_5 = rules.register(
    Rule("HUM-5", "A question carries its why, options and default, within its limits.")
)
QUESTION, ASSIST, HEADS_UP = "question", "assist", "heads-up"
SPEND, LEGAL, TOOL = "approval: spend", "approval: legal", "approval: tool permission"
WHY_MIN_CHARACTERS = 20  # HUM-5
DEFAULT_MIN_CHARACTERS = 20  # HUM-5
OPTIONS_MOST = 4  # HUM-5
WINDOW_MOST = timedelta(hours=72)  # HUM-2
ARCHIVE_AFTER = timedelta(days=7)  # HUM-2: a heads-up is archived unacknowledged
VERBS = ("accept_scope", "change_scope", "date", "reserve_draw")
OTHER = "other"
DEFAULT_STANDS = "the default stands"


async def _tell(done: Settling, kind: str, body: str) -> None:
    """Tell the item's filer what became of it."""
    seat = await done.session.get(Seat, done.item.filer_id)
    if seat is None:
        seat = await ceo_of(done.session, done.project.id)
    notices.notify(done.session, done.project.id, seat.id, kind, body, done.now, urgent=True)


async def _answered(done: Settling) -> None:
    """HUM-5, SPD-5: the answer reaches the CEO. When it differs from the default the CEO
    already acted on, the item says so and the CEO records what it redid."""
    fields = done.item.fields
    if done.outcome == DEFAULT_STANDS:
        await _tell(
            done, "question lapsed",
            f"Question {done.item.id} was not answered in time. Your default stands on the "
            f"record: {fields['default']}",
        )  # fmt: skip
        return
    option = done.values.get("option")
    options: list[str] = fields["options"]
    if option is not None and not 1 <= int(option) <= len(options):
        raise Refusal(
            "not_an_option",
            f"This question has {len(options)} options; pick one of them, or answer in a note.",
            rule=HUM_5.id,
        )
    if option is None and not (done.note or "").strip():
        raise Refusal("answer_needs_words", "Pick an option, or answer in a note.", rule=HUM_5.id)
    picked = options[int(option) - 1] if option is not None else None
    differs = option is None or int(option) != int(fields["recommended"])
    done.item.outcome_detail = {
        **(done.item.outcome_detail or {}),
        "answer": picked or (done.note or "").strip(),
        "differs_from_default": differs,
        "rework": [],
    }
    answer = f"{picked or ''} {(done.note or '').strip()}".strip()
    closing = (
        " This differs from the default you acted on. Adjust, and record what you redo "
        f"with agent_record_rework (item_id={done.item.id})."
        if differs
        else " It matches the default you acted on."
    )
    await _tell(
        done, "question answered",
        f"The chairman answered question {done.item.id} ({fields['question']}): {answer}."
        + closing,
    )  # fmt: skip


items.register(
    Kind(
        name=QUESTION,
        filed_by="ceo",
        actions=("answer",),
        default=DEFAULT_STANDS,
        title=lambda f: f"Question about {f['concerns'].replace('_', ' ')}",
        apply=_answered,
    )
)


async def ask(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    caller: Caller,
    *,
    question: str,
    why: str,
    options: list[str],
    recommended: int,
    default: str,
    concerns: str,
    window_hours: int | None,
    now: datetime,
) -> DecisionItem:
    """HUM-4, HUM-5, SPD-5: the CEO asks and proceeds at once on its stated default. A
    question about a decision the CEO holds is refused. The default is what the CEO does
    within its own authority; at the deadline the platform does nothing but record that
    it stands, so no default can spend, grant or widen scope (R-27)."""
    if concerns not in (*VERBS, OTHER):
        raise Refusal(
            "concerns_unknown",
            f"`concerns` names the decision this is about: {', '.join(VERBS)}, or {OTHER}.",
            rule=HUM_4.id,
        )
    verb = cast(authority.Verb, concerns)
    if concerns != OTHER and await authority.ceo_holds(session, settings, project, verb):
        raise Refusal(
            "you_hold_this_decision",
            "You hold this decision. Decide it and post a heads-up.",
            rule=HUM_4.id,
            hint="Use agent_post_heads_up to tell the chairman what you decided.",
        )
    if len(why.strip()) < WHY_MIN_CHARACTERS or len(default.strip()) < DEFAULT_MIN_CHARACTERS:
        raise Refusal(
            "question_incomplete",
            f"A question says why it matters ({WHY_MIN_CHARACTERS} characters or more) and "
            f"what you will do by default ({DEFAULT_MIN_CHARACTERS} or more).",
            rule=HUM_5.id,
        )
    if not 1 <= len(options) <= OPTIONS_MOST or not 1 <= recommended <= len(options):
        raise Refusal(
            "question_options",
            f"Give 1 to {OPTIONS_MOST} options and recommend one of them by its number.",
            rule=HUM_5.id,
        )
    subject = authority.subject(project)
    limit = int(await settings.get(session, subject, "question.max_open"))
    open_now = await session.scalar(
        select(func.count())
        .select_from(DecisionItem)
        .where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == QUESTION,
            DecisionItem.state == ItemState.OPEN,
        )
    )
    if int(open_now or 0) >= limit:
        raise Refusal(
            "too_many_questions",
            f"{open_now} questions are open and `question.max_open` is {limit}.",
            rule=HUM_5.id,
            hint="Proceed on your defaults; ask again when one is answered.",
        )
    standard = timedelta(seconds=int(await settings.get(session, subject, "question.window")))
    window = timedelta(hours=window_hours) if window_hours else standard
    if window > WINDOW_MOST:
        raise Refusal("window_too_long", "A question waits at most 72 hours.", rule=HUM_5.id)
    return await items.file(
        session,
        settings,
        project,
        QUESTION,
        filer=caller,
        fields={
            "question": question.strip(),
            "why": why.strip(),
            "options": [option.strip() for option in options],
            "recommended": recommended,
            "default": default.strip(),
            "concerns": concerns,
        },
        recommendation=f"Option {recommended}: {options[recommended - 1].strip()}"[:300],
        if_declined=f"Unanswered, the CEO's default stands: {default.strip()}",
        window=window,
        now=now,
    )


async def remind(session: AsyncSession, project: Project, now: datetime) -> int:
    """HUM-5: one reminder goes out halfway through a question's window."""
    rows = await session.scalars(
        select(DecisionItem).where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == QUESTION,
            DecisionItem.state == ItemState.OPEN,
            DecisionItem.reminded.is_(False),
        )
    )
    sent = 0
    for item in rows:
        if item.deadline is None or now < item.opened_at + (item.deadline - item.opened_at) / 2:
            continue
        item.reminded = True
        sent += 1
        for hook in items.reminder_hooks:
            await hook(session, project, item, now)
    return sent


async def record_rework(
    session: AsyncSession, item: DecisionItem, caller: Caller, what: str
) -> None:
    """SPD-5: what the CEO redid because the answer differed is recorded against the
    question."""
    detail = dict(item.outcome_detail or {})
    if item.kind != QUESTION or item.filer_id != caller.actor_id or "answer" not in detail:
        raise Refusal(
            "no_rework_to_record",
            "Rework is recorded against a question of yours that the chairman answered.",
            rule=HUM_5.id,
        )
    detail["rework"] = [*detail.get("rework", []), what.strip()]
    item.outcome_detail = detail


async def _assisted(done: Settling) -> None:
    """HUM-7: a done assist lets the task go on; otherwise the task is blocked. The rest
    of the project never waited."""
    task_id = done.item.fields.get("task_id")
    if done.outcome == "done":
        await _tell(
            done, "assist done",
            f"The chairman did what you asked in item {done.item.id}: "
            f"{done.item.fields['step']}" + (f" Note: {done.note}" if done.note else ""),
        )  # fmt: skip
        return
    if task_id is not None:
        task = await done.session.get(Task, int(task_id))
        if task is not None and task.state in (TaskState.READY, TaskState.CLAIMED):
            task.reason = f"The human step in item {done.item.id} was not done."
            tasks.move(done.session, task, TaskState.BLOCKED, done.caller, done.now)
    await _tell(
        done, "assist not done",
        f"The step you asked for in item {done.item.id} was not done"
        + (f": {done.note}" if done.note else ".")
        + " Find another way, or kill the task.",
    )  # fmt: skip


items.register(
    Kind(
        name=ASSIST,
        filed_by="agent",
        actions=("done", "cannot"),
        default="cannot",
        window="approval.window",
        title=lambda f: "A step only you can do: " + str(f["what"]),
        apply=_assisted,
        extendable=True,
    )
)
ASSIST_KINDS = ("captcha", "two-factor code", "identity check", "login", "other human step")

items.register(
    Kind(
        name=HEADS_UP,
        filed_by="ceo",
        actions=("acknowledge",),
        title=lambda f: "Heads-up from the CEO",
        desk=False,
        decided_state=ItemState.ACKNOWLEDGED,
    )
)


async def archive_heads_ups(session: AsyncSession, project: Project, now: datetime) -> int:
    """HUM-2: a heads-up nobody acknowledged in 7 days is archived; the brief lists it."""
    rows = await session.scalars(
        select(DecisionItem).where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == HEADS_UP,
            DecisionItem.state == ItemState.OPEN,
            DecisionItem.opened_at <= now - ARCHIVE_AFTER,
        )
    )
    count = 0
    for item in rows:
        item.outcome = "archived unacknowledged"
        items.move(session, item, ItemState.ARCHIVED, items.ITEMS_JOB, now)
        count += 1
    return count


async def _approved(done: Settling) -> None:
    word = "approved" if done.outcome == "approve" else "denied"
    await _tell(
        done, f"approval {word}",
        f"The chairman {word} item {done.item.id} ({items.title_of(done.item)})"
        + (f": {done.note}" if done.note else "."),
    )  # fmt: skip
    for hook in approval_hooks:
        await hook(done)


approval_hooks: list[Any] = []
"""Called with the `Settling` when a spend, legal or tool-permission item is settled."""


def _approval(
    name: str, by: str, title: Callable[[dict[str, Any]], str], figures: tuple[str, ...] = ()
) -> None:
    items.register(
        Kind(
            name=name,
            filed_by=by,
            actions=("approve", "deny"),
            default="deny",
            window="approval.window",
            title=title,
            apply=_approved,
            extendable=True,
            figures=figures,
            positive=("approve",),
        )
    )


def _spend_title(fields: dict[str, Any]) -> str:
    return f"Spend {float(fields['amount']):,.2f} {fields['currency']}"


def _tool_title(fields: dict[str, Any]) -> str:
    return f"Allow the tool {fields['tool']}"


def _legal_title(fields: dict[str, Any]) -> str:
    return "Legal approval"


_approval(SPEND, "ceo", _spend_title, ("amount",))
_approval(LEGAL, "ceo", _legal_title)
_approval(TOOL, "agent", _tool_title)
