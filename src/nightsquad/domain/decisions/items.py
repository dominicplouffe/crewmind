"""Decision items (HUM-1 to HUM-4, INV-17, section 7.5): one type for everything that
waits on a human. A kind is a registration; the lifecycle here is the same for all.

This module imports no other domain's rules, so any domain can file and settle items.
Each domain registers its own kinds, with what each outcome does.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller, CallerKind, platform_job
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.decisions.model import ITEM_MACHINE, LIVE, ItemState
from nightsquad.domain.projects import lifecycle
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import DecisionItem, Project

HUM_1 = rules.register(
    Rule("HUM-1", "A decision item is decided only by its typed actions, by the chairman.")
)
HUM_3 = rules.register(
    Rule("HUM-3", "Only approvals are extended, by 1 to 30 days, with a reason, while open.")
)
HUM_4 = rules.register(Rule("HUM-4", "The CEO does not ask about a decision it holds."))
INV_17 = rules.register(
    Rule("INV-17", "At its deadline an item resolves to its declared default, never to allow.")
)
WRK_10 = rules.register(Rule("WRK-10", "A figure in a decision item links its basis."))
ITEM_CHANGED = event_type("item.state_changed", "A decision item changed state (7.5).")
ITEM_EDITED = event_type("item.edited", "A decision item got a note or a new deadline.")
ITEMS_JOB = platform_job("decisions: deadlines")
S = ItemState
RECOMMENDATION_LENGTH = (10, 300)  # HUM-1
EXTEND_DAYS = (1, 30)  # HUM-3
REASON_MIN_CHARACTERS = 10
BASIS_KINDS = ("command", "artifact", "evidence")  # WRK-10

Apply = Callable[["Settling"], Awaitable[None]]


@dataclass(frozen=True)
class Settling:
    """What an outcome's effect is given: the item, the outcome and who caused it."""

    session: AsyncSession
    services: Any
    project: Project
    item: DecisionItem
    outcome: str
    caller: Caller
    values: dict[str, Any]
    note: str | None
    now: datetime
    call: Any = None
    """Runs a catalog operation as the deciding person: `await call(name, **values)`.
    It is None when the platform applies a default."""

    @property
    def by_platform(self) -> bool:
        return self.caller.kind is CallerKind.PLATFORM


@dataclass(frozen=True)
class Kind:
    """One kind of decision item (HUM-2). Registering it is all a new kind needs: the
    desk, the chat card, the brief, the agenda and every surface read this registry."""

    name: str
    filed_by: str
    actions: tuple[str, ...]
    title: Callable[[dict[str, Any]], str]
    default: str | None = None
    window: str | timedelta | None = None
    """A project setting's name, a fixed length, or None for no deadline."""
    apply: Apply | None = None
    desk: bool = True
    """Whether an open item of this kind counts as waiting on the chairman (HUM-10)."""
    extendable: bool = False
    verb: str | None = None
    """The authority verb this kind asks about, when the CEO might hold it (HUM-4)."""
    figures: tuple[str, ...] = ()
    """Numeric fields that must link their basis (WRK-10)."""
    decide_from: ItemState = ItemState.OPEN
    """The state an item must be in for a typed action. A flag is acknowledged only once
    the CEO has raised it."""
    decided_state: ItemState = ItemState.DECIDED
    """Where a typed action takes the item. A heads-up is acknowledged, not decided."""
    positive: tuple[str, ...] = field(default_factory=tuple)
    """Outcomes that grant something. A default is never one of these, except where
    HUM-3 says so."""


_KINDS: dict[str, Kind] = {}
POSITIVE_DEFAULTS_ALLOWED = frozenset({"delivery sign-off", "status review"})  # HUM-3


def register(kind: Kind) -> Kind:
    """Add a kind. A default that grants something is refused at import (INV-17, P6)."""
    if kind.default in kind.positive and kind.name not in POSITIVE_DEFAULTS_ALLOWED:
        raise ValueError(f"{kind.name}: a default may not be {kind.default}")
    _KINDS[kind.name] = kind
    return kind


def kind_of(name: str) -> Kind:
    return _KINDS[name]


def kinds() -> list[Kind]:
    return [_KINDS[name] for name in sorted(_KINDS)]


def title_of(item: DecisionItem) -> str:
    """HUM-1: the title is built from typed fields, never from free agent text."""
    return kind_of(item.kind).title(item.fields)


def _move(
    session: AsyncSession,
    item: DecisionItem,
    target: ItemState,
    caller: Caller,
    now: datetime,
    detail: dict[str, Any] | None = None,
) -> None:
    """The one place an item changes state (7.5)."""
    ITEM_MACHINE.check(item.state, target)
    before = item.state
    item.state = target
    if target not in LIVE:
        item.closed_at = now
    append_event(
        session,
        type=ITEM_CHANGED,
        caller=caller,
        at=now,
        subject=("item", str(item.id)),
        project_id=item.project_id,
        before={"state": before},
        after={"state": target, "kind": item.kind, "outcome": item.outcome},
        detail=detail,
    )


def _subject(project: Project) -> Subject:
    return Subject(Scope.PROJECT, project.id, project.type)


def check_basis(kind: Kind, fields: dict[str, Any], basis: dict[str, Any] | None) -> None:
    """WRK-10: an item with a numeric field links that number's basis."""
    if not any(fields.get(name) is not None for name in kind.figures):
        return
    ok = (
        basis is not None
        and basis.get("kind") in BASIS_KINDS
        and len(str(basis.get("ref", "")).strip()) > 0
    )
    if not ok:
        raise Refusal(
            "figure_needs_a_basis",
            "This item carries a figure, so it must link the figure's basis: a command "
            "output, a dataset artifact or verified evidence.",
            rule=WRK_10.id,
            hint='Give `basis` as {"kind": "command" | "artifact" | "evidence", "ref": ...}.',
        )


async def file(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    kind_name: str,
    *,
    filer: Caller,
    fields: dict[str, Any],
    recommendation: str,
    if_declined: str,
    now: datetime,
    subject: tuple[str, str] | None = None,
    basis: dict[str, Any] | None = None,
    window: timedelta | None = None,
    default: str | None = None,
    announce: bool = True,
) -> DecisionItem:
    """File an item. Its deadline and default come from its kind unless the kind lets the
    filer state them (a question's window and default)."""
    kind = kind_of(kind_name)
    low, high = RECOMMENDATION_LENGTH
    if not low <= len(recommendation.strip()) <= high:
        raise Refusal(
            "recommendation_length",
            f"A recommendation has {low} to {high} characters; this one has "
            f"{len(recommendation.strip())}.",
            rule=HUM_1.id,
        )
    check_basis(kind, fields, basis)
    length = window
    if length is None and isinstance(kind.window, timedelta):
        length = kind.window
    elif length is None and isinstance(kind.window, str):
        seconds = int(await settings.get(session, _subject(project), kind.window))
        length = timedelta(seconds=seconds) if seconds else None
    item = DecisionItem(
        project_id=project.id,
        kind=kind.name,
        filer_kind=filer.kind,
        filer_id=filer.actor_id,
        subject_kind=subject[0] if subject else None,
        subject_id=subject[1] if subject else None,
        fields=fields,
        recommendation=recommendation.strip(),
        if_declined=if_declined.strip(),
        basis=basis,
        deadline=now + length if length else None,
        default_outcome=default if default is not None else kind.default,
        state="(new)",
        extensions=0,
        reminded=False,
        opened_at=now,
    )
    session.add(item)
    await session.flush()
    _move(session, item, S.OPEN, filer, now)
    if announce:
        await conversation.platform_line(
            session,
            project.id,
            card_text(item),
            now,
            detail={"kind": "decision item", "item": item.id, "item_kind": item.kind},
        )
    for hook in filed_hooks:
        await hook(session, project, item, now)
    return item


reminder_hooks: list[Any] = []
"""Called as `(session, project, item, now)` when an item's reminder is due."""
filed_hooks: list[Any] = []
"""Called as `(session, project, item, now)` when an item is filed: alerts register here."""


def card_text(item: DecisionItem) -> str:
    """The item as one chat line, for surfaces that show no card."""
    kind = kind_of(item.kind)
    parts = [f"{title_of(item)}. {item.recommendation}"]
    if item.if_declined:
        parts.append(f"If declined: {item.if_declined}")
    if item.deadline is not None and item.default_outcome is not None:
        when = item.deadline.strftime("%d %b %Y %H:%M UTC")
        parts.append(f"Unanswered by {when}, the outcome is: {item.default_outcome}.")
    if kind.actions:
        parts.append(f"You can: {', '.join(kind.actions)} (item {item.id}).")
    return " ".join(parts)


async def get(session: AsyncSession, project_id: str, item_id: int) -> DecisionItem:
    item = await session.get(DecisionItem, item_id)
    if item is None or item.project_id != project_id:
        raise Refusal("item_not_found", "There is no such item.", kind=RefusalKind.NOT_FOUND)
    return item


async def open_for(
    session: AsyncSession, kind_name: str, subject: tuple[str, str]
) -> DecisionItem | None:
    """The live item of this kind about this subject, if there is one."""
    return await session.scalar(
        select(DecisionItem)
        .where(
            DecisionItem.kind == kind_name,
            DecisionItem.subject_kind == subject[0],
            DecisionItem.subject_id == subject[1],
            DecisionItem.state.in_(LIVE),
        )
        .order_by(DecisionItem.id.desc())
        .limit(1)
    )


async def _apply(
    session: AsyncSession,
    services: Any,
    project: Project,
    item: DecisionItem,
    outcome: str,
    caller: Caller,
    values: dict[str, Any],
    note: str | None,
    now: datetime,
    call: Any = None,
) -> None:
    kind = kind_of(item.kind)
    if kind.apply is not None:
        await kind.apply(
            Settling(session, services, project, item, outcome, caller, values, note, now, call)
        )


async def decide(
    session: AsyncSession,
    services: Any,
    project: Project,
    item: DecisionItem,
    action: str,
    caller: Caller,
    now: datetime,
    *,
    note: str | None = None,
    values: dict[str, Any] | None = None,
    call: Any = None,
) -> None:
    """HUM-1, 7.5: the chairman decides an open item with one of its typed actions. What
    the action does belongs to the item's kind."""
    kind = kind_of(item.kind)
    if caller.kind is not CallerKind.PERSON:
        raise Refusal(
            "only_a_person_decides",
            "A decision item is decided by the chairman, never by an agent.",
            rule=HUM_1.id,
            kind=RefusalKind.FORBIDDEN,
        )
    if action not in kind.actions:
        raise Refusal(
            "not_an_action",
            f'"{action}" is not an action of this item. You can: {", ".join(kind.actions)}.',
            rule=HUM_1.id,
        )
    if item.state != kind.decide_from:
        ITEM_MACHINE.check(item.state, kind.decided_state)
        raise Refusal(
            "not_yet",
            f"This item is {item.state}; that action is taken once it is {kind.decide_from}.",
            rule=HUM_1.id,
        )
    item.outcome, item.chairman_note = action, (note or "").strip() or item.chairman_note
    item.outcome_detail = {**(item.outcome_detail or {}), **(values or {})} or None
    _move(session, item, kind.decided_state, caller, now, {"note": note})
    await _apply(session, services, project, item, action, caller, values or {}, note, now, call)


async def settle(
    session: AsyncSession,
    kind_name: str,
    subject: tuple[str, str],
    outcome: str,
    caller: Caller,
    now: datetime,
) -> None:
    """Close the live item about a subject that was just decided directly, through its own
    operation rather than through the item. The effect has already happened."""
    item = await open_for(session, kind_name, subject)
    if item is None or item.state != S.OPEN:
        return
    item.outcome = outcome
    if caller.kind is CallerKind.PERSON:
        target = S.DECIDED
    elif caller.kind is CallerKind.PLATFORM:
        target = S.DEFAULTED
    else:
        target = S.WITHDRAWN
    _move(session, item, target, caller, now, {"directly": True})


async def withdraw(
    session: AsyncSession, item: DecisionItem, caller: Caller, now: datetime
) -> None:
    """7.5: the filer withdraws its own open item."""
    if caller.actor_id != item.filer_id:
        raise Refusal(
            "not_your_item", "Only the filer withdraws an item.", rule=HUM_1.id,
            kind=RefusalKind.FORBIDDEN,
        )  # fmt: skip
    item.outcome = "withdrawn"
    _move(session, item, S.WITHDRAWN, caller, now)


async def extend(
    session: AsyncSession,
    item: DecisionItem,
    days: int,
    reason: str,
    caller: Caller,
    now: datetime,
) -> None:
    """HUM-3: an approval's deadline can be extended by 1 to 30 days with a reason. A
    decided item cannot be extended."""
    kind = kind_of(item.kind)
    low, high = EXTEND_DAYS
    if not kind.extendable or item.state != S.OPEN or item.deadline is None:
        raise Refusal(
            "cannot_extend",
            "Only an open approval with a deadline can be extended.",
            rule=HUM_3.id,
        )
    if not low <= days <= high or len(reason.strip()) < REASON_MIN_CHARACTERS:
        raise Refusal(
            "extension_needs_days_and_a_reason",
            f"Extend by {low} to {high} days, with a reason of at least "
            f"{REASON_MIN_CHARACTERS} characters.",
            rule=HUM_3.id,
        )
    before = item.deadline
    assert before is not None
    later = max(before, now) + timedelta(days=days)
    item.deadline = later
    item.extensions += 1
    append_event(
        session,
        type=ITEM_EDITED,
        caller=caller,
        at=now,
        subject=("item", str(item.id)),
        project_id=item.project_id,
        before={"deadline": before.isoformat()},
        after={"deadline": later.isoformat()},
        detail={"reason": reason.strip()},
    )


async def add_note(
    session: AsyncSession, item: DecisionItem, note: str, caller: Caller, now: datetime
) -> None:
    item.chairman_note = note.strip()
    append_event(
        session,
        type=ITEM_EDITED,
        caller=caller,
        at=now,
        subject=("item", str(item.id)),
        project_id=item.project_id,
        after={"note": True},
    )


async def apply_defaults(
    session: AsyncSession, services: Any, project: Project, now: datetime
) -> list[DecisionItem]:
    """INV-17: every open item past its deadline resolves to its declared default."""
    due = list(
        await session.scalars(
            select(DecisionItem)
            .where(
                DecisionItem.project_id == project.id,
                DecisionItem.state == S.OPEN,
                DecisionItem.deadline.is_not(None),
                DecisionItem.deadline <= now,
            )
            .order_by(DecisionItem.id)
        )
    )
    for item in due:
        outcome = item.default_outcome or "expired"
        item.outcome = outcome
        _move(session, item, S.DEFAULTED, ITEMS_JOB, now, {"default": outcome})
        await _apply(session, services, project, item, outcome, ITEMS_JOB, {}, None, now)
    return due


async def void_all(session: AsyncSession, project: Project, now: datetime) -> None:
    """7.5: a stopped project's open and raised items are void."""
    rows = await session.scalars(
        select(DecisionItem).where(
            DecisionItem.project_id == project.id,
            DecisionItem.state.in_([S.OPEN, S.RAISED]),
        )
    )
    for item in rows:
        _move(session, item, S.VOID, ITEMS_JOB, now)


async def close_quietly(
    session: AsyncSession, kind_name: str, subject: tuple[str, str], now: datetime, why: str
) -> None:
    """Withdraw the platform's own item about a subject that no longer needs an answer."""
    item = await open_for(session, kind_name, subject)
    if item is not None and item.state == S.OPEN:
        item.outcome = why
        _move(session, item, S.WITHDRAWN, ITEMS_JOB, now, {"why": why})


def move(
    session: AsyncSession,
    item: DecisionItem,
    target: ItemState,
    caller: Caller,
    now: datetime,
    detail: dict[str, Any] | None = None,
) -> None:
    """For the kind-specific states (flags, heads-ups, mistake reports)."""
    _move(session, item, target, caller, now, detail)


lifecycle.stop_hooks.append(void_all)
