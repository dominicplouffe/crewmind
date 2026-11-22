"""The outside world: evidence the platform verifies, side effects that fire once, and
launches that must be watched (WRK-12, WRK-16, WRK-17, INV-14, sections 7.15 and 7.16)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Authority, Caller
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import notices
from crewmind.domain.execution.agent import agent_of
from crewmind.domain.execution.agent_operations import work_run_only
from crewmind.domain.execution.model import SeatKind
from crewmind.domain.integrations import push
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.domain.work import tasks
from crewmind.domain.work.model import (
    EFFECT_MACHINE,
    EVIDENCE_MACHINE,
    WATCH_MACHINE,
    EffectState,
    EvidenceState,
    WatchState,
)
from crewmind.services import services_of
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Evidence, Project, Seat, SideEffect, Watch

WRK_12 = rules.register(
    Rule("WRK-12", "Outside evidence counts only once the platform has verified it.")
)
WRK_16 = rules.register(Rule("WRK-16", "A side effect is declared before it fires, once."))
WRK_17 = rules.register(Rule("WRK-17", "A launch must declare a watch."))
INV_14 = rules.register(Rule("INV-14", "A side effect under one key fires at most once."))

EVIDENCE_CHANGED = event_type("evidence.state_changed", "Outside evidence changed state (7.15).")
EFFECT_CHANGED = event_type("side_effect.state_changed", "A side effect changed state (7.16).")
WATCH_CHANGED = event_type("watch.state_changed", "A watch changed state (7.16).")

AGENT = frozenset({Principal.AGENT_RUN})
_TAG = re.compile(r"<[^>]*>")
FETCH_ATTEMPTS = 5  # WRK-12: a fetch failure is retried up to 5 times, then fails closed
E, F, W = EvidenceState, EffectState, WatchState


class EvidenceInput(BaseModel):
    url: str = Field(max_length=2000, description="The public page that shows it.")
    quote: str = Field(
        min_length=5, max_length=1000, description="Words on that page that show what you claim."
    )
    task_id: int | None = Field(default=None, description="The task this is evidence for.")


class EvidenceItem(BaseModel):
    id: int
    url: str
    quote: str
    task_id: int | None
    state: str = Field(description="pending (counts for nothing yet), verified or failed.")
    failure: str | None
    filed_by: str


class EvidenceList(BaseModel):
    items: list[EvidenceItem]


class WatchInput(BaseModel):
    kind: Literal["command", "url"] = Field(description="command (a check) or url.")
    check: str = Field(max_length=2000, description="The command to run, or the URL to fetch.")
    expect: str | None = Field(
        default=None, max_length=500, description="For a url: words the page must contain."
    )
    interval_minutes: int = Field(ge=1, description="How often to run it.")


class DeclareInput(BaseModel):
    key: str = Field(
        min_length=3,
        max_length=200,
        description="An idempotency key: the same words every time you mean the same action.",
    )
    what: str = Field(min_length=10, max_length=2000, description="What you are about to do.")
    launch: bool = Field(
        default=False, description="True if it leaves something running outside the project."
    )
    watch: WatchInput | None = Field(default=None, description="Required for a launch.")


class FinishInput(BaseModel):
    key: str = Field(description="The key you declared it under.")
    fired: bool = Field(description="Whether it actually happened.")
    outcome: str = Field(min_length=5, max_length=2000, description="What happened.")


class EffectItem(BaseModel):
    id: int
    declared_as: str = Field(description="The idempotency key it was declared under.")
    what: str
    launch: bool
    state: str
    fired: bool | None
    outcome: str | None
    by: str
    watch: str | None = Field(description="passing, failing or ended, for a launch.")
    watch_result: str | None
    fire: bool = Field(
        description="Whether to go ahead. False means it was already declared: do not fire again."
    )


class EffectList(BaseModel):
    items: list[EffectItem]


class EffectRef(BaseModel):
    effect_id: int = Field(description="The launch's id.")


class LaunchRef(ProjectRef):
    effect_id: int = Field(description="The launch's id, from `launches list`.")


async def _evidence_item(session: AsyncSession, row: Evidence) -> EvidenceItem:
    seat = await session.get(Seat, row.seat_id)
    return EvidenceItem(
        id=row.id,
        url=row.url,
        quote=row.claim,
        task_id=row.task_id,
        state=row.state,
        failure=row.failure,
        filed_by=seat.name if seat else "",
    )


@operation(
    "agent.file_evidence",
    summary="File outside evidence: a public page and the words on it. The platform verifies it.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def file_evidence(context: Context, payload: EvidenceInput) -> EvidenceItem:
    """WRK-12: agent-claimed evidence starts pending and counts for nothing until the
    platform verifies it. In Deliver and Operate it must name a real task."""
    view = await agent_of(context)
    work_run_only(view)
    if payload.task_id is not None:
        await tasks.get(context.session, view.project.id, payload.task_id)
    elif view.project.type != "explore":
        raise Refusal(
            "evidence_needs_a_task",
            "In this project, evidence must name the task it is for.",
            rule=WRK_12.id,
            hint="Give `task_id`.",
        )
    EVIDENCE_MACHINE.check(NEW, E.PENDING)
    row = Evidence(
        project_id=view.project.id,
        task_id=payload.task_id,
        seat_id=view.seat.id,
        url=payload.url.strip(),
        claim=payload.quote.strip(),
        state=E.PENDING,
        attempts=0,
        filed_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    context.record(
        EVIDENCE_CHANGED,
        subject=("evidence", str(row.id)),
        project_id=view.project.id,
        after={"state": E.PENDING, "url": row.url},
    )
    return await _evidence_item(context.session, row)


@operation(
    "evidence.list",
    summary="List the outside evidence agents have filed and whether it was verified.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_evidence(context: Context, payload: ProjectRef) -> EvidenceList:
    rows = await context.session.scalars(
        select(Evidence).where(Evidence.project_id == payload.project_id).order_by(Evidence.id)
    )
    return EvidenceList(items=[await _evidence_item(context.session, row) for row in rows])


async def controlled_hosts(session: AsyncSession, project_id: str) -> set[str]:
    """Domains the project controls: the hosts its own launches are watched at (WRK-12)."""
    rows = await session.scalars(
        select(Watch.check).where(Watch.project_id == project_id, Watch.kind == "url")
    )
    return {host for check in rows if (host := urlsplit(check).hostname)}


def settle_evidence(
    session: AsyncSession,
    row: Evidence,
    now: datetime,
    caller: Caller,
    *,
    snapshot_hash: str | None = None,
    failure: str | None = None,
) -> None:
    """Section 7.15: pending evidence becomes verified, or fails closed."""
    target = E.VERIFIED if failure is None else E.FAILED
    EVIDENCE_MACHINE.check(row.state, target)
    row.state, row.snapshot_hash, row.failure, row.settled_at = target, snapshot_hash, failure, now
    append_event(
        session,
        type=EVIDENCE_CHANGED,
        caller=caller,
        at=now,
        subject=("evidence", str(row.id)),
        project_id=row.project_id,
        before={"state": E.PENDING},
        after={"state": target, "snapshot": snapshot_hash, "failure": failure},
    )
    notices.notify(
        session,
        row.project_id,
        row.seat_id,
        "evidence settled",
        f"Your evidence {row.id} ({row.url}) is {target}."
        + (f" {failure}" if failure else " It now counts."),
        now,
    )


def found_on_page(quote: str, page: bytes) -> bool:
    """Whether the claimed words are on the page, ignoring case and spacing."""
    text = _TAG.sub(" ", page.decode("utf-8", errors="replace"))
    return " ".join(quote.lower().split()) in " ".join(text.lower().split())


def snapshot(page: bytes) -> str:
    return hashlib.sha256(page).hexdigest()


def _effect_item(row: SideEffect, by: str, watch: Watch | None, *, fire: bool) -> EffectItem:
    return EffectItem(
        id=row.id,
        declared_as=row.idempotency_key,
        what=row.what,
        launch=row.is_launch,
        state=row.state,
        fired=row.fired,
        outcome=row.outcome,
        by=by,
        watch=watch.state if watch else None,
        watch_result=watch.last_result if watch else None,
        fire=fire,
    )


async def _item_of(session: AsyncSession, row: SideEffect, *, fire: bool = False) -> EffectItem:
    seat = await session.get(Seat, row.seat_id)
    watch = await session.scalar(select(Watch).where(Watch.side_effect_id == row.id))
    return _effect_item(row, seat.name if seat else "", watch, fire=fire)


def _move_effect(
    session: AsyncSession, row: SideEffect, target: EffectState, caller: Caller, now: datetime
) -> None:
    EFFECT_MACHINE.check(row.state, target)
    before = row.state
    row.state = target
    append_event(
        session,
        type=EFFECT_CHANGED,
        caller=caller,
        at=now,
        subject=("side_effect", str(row.id)),
        project_id=row.project_id,
        before={"state": before},
        after={"state": target, "fired": row.fired},
    )


def move_watch(
    session: AsyncSession, watch: Watch, target: WatchState, caller: Caller, now: datetime
) -> None:
    WATCH_MACHINE.check(watch.state or NEW, target)
    before = watch.state
    watch.state = target
    append_event(
        session,
        type=WATCH_CHANGED,
        caller=caller,
        at=now,
        subject=("watch", str(watch.id)),
        project_id=watch.project_id,
        before={"state": before},
        after={"state": target, "result": watch.last_result},
    )


@operation(
    "agent.declare_effect",
    summary="Declare something you are about to do outside the project, before you do it.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def declare_effect(context: Context, payload: DeclareInput) -> EffectItem:
    """WRK-16, WRK-17, INV-14: a side effect is declared under an idempotency key before it
    fires. A key already declared returns the existing record and says not to fire again.
    A launch must declare a watch, at an interval no shorter than `watch.min_interval`."""
    view = await agent_of(context)
    work_run_only(view)
    existing = await context.session.scalar(
        select(SideEffect).where(
            SideEffect.project_id == view.project.id, SideEffect.idempotency_key == payload.key
        )
    )
    if existing is not None:
        return await _item_of(context.session, existing, fire=False)
    if payload.launch:
        if payload.watch is None:
            raise Refusal(
                "launch_needs_a_watch",
                "A launch leaves something running outside the project, so it must declare a "
                "watch: a check command, or a URL and what it must show.",
                rule=WRK_17.id,
                hint="Give `watch` with its kind, its check and an interval.",
            )
        least = int(
            await services_of(context).settings.get(
                context.session, Subject(Scope.INSTALL, INSTALL_SUBJECT), "watch.min_interval"
            )
        )
        if payload.watch.interval_minutes * 60 < least:
            raise Refusal(
                "watch_too_often",
                f"A watch runs at most every {least // 60} minutes (`watch.min_interval`).",
                rule=WRK_17.id,
                hint="Give a longer interval.",
            )
        if payload.watch.kind == "url" and not payload.watch.expect:
            raise Refusal(
                "watch_needs_a_condition",
                "A URL watch needs the words the page must contain.",
                rule=WRK_17.id,
                hint="Give `expect`.",
            )
    EFFECT_MACHINE.check(NEW, F.DECLARED)
    row = SideEffect(
        project_id=view.project.id,
        seat_id=view.seat.id,
        run_id=view.run.id,
        idempotency_key=payload.key,
        what=payload.what,
        is_launch=payload.launch,
        state=F.DECLARED,
        declared_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    context.record(
        EFFECT_CHANGED,
        subject=("side_effect", str(row.id)),
        project_id=view.project.id,
        after={"state": F.DECLARED, "key": payload.key, "launch": payload.launch},
    )
    if payload.launch and payload.watch is not None:
        context.session.add(
            Watch(
                side_effect_id=row.id,
                project_id=view.project.id,
                kind=payload.watch.kind,
                check=payload.watch.check,
                expect=payload.watch.expect,
                interval_seconds=payload.watch.interval_minutes * 60,
                state=None,
            )
        )
        await context.session.flush()
    return await _item_of(context.session, row, fire=True)


@operation(
    "agent.finish_effect",
    summary="Record what happened to a side effect you declared: it fired, or it failed.",
    authority=Authority.AGENT,
    reversibility=Reversibility.IRREVERSIBLE,
    principals=AGENT,
)
async def finish_effect(context: Context, payload: FinishInput) -> EffectItem:
    """WRK-16, section 7.16: finished by the agent that declared it, in the declaring run
    or any later one, so a dead run never strands it. A launch that fired starts being
    watched."""
    view = await agent_of(context)
    work_run_only(view)
    row = await context.session.scalar(
        select(SideEffect).where(
            SideEffect.project_id == view.project.id, SideEffect.idempotency_key == payload.key
        )
    )
    if row is None or row.seat_id != view.seat.id:
        raise Refusal(
            "not_your_side_effect",
            f"You have declared no side effect with the key {payload.key}.",
            rule=WRK_16.id,
            hint="Declare it first with agent_declare_effect.",
        )
    row.fired, row.outcome, row.finished_at = payload.fired, payload.outcome, context.now
    _move_effect(context.session, row, F.FINISHED, context.caller, context.now)
    watch = await context.session.scalar(select(Watch).where(Watch.side_effect_id == row.id))
    if watch is not None and payload.fired:
        move_watch(context.session, watch, W.PASSING, tasks.WORK_JOB, context.now)
    return await _item_of(context.session, row)


async def _retire(context: Context, row: SideEffect) -> EffectItem:
    if not row.is_launch:
        raise Refusal(
            "not_a_launch",
            f"Side effect {row.id} is not a launch, so there is nothing to retire.",
            rule=WRK_17.id,
            hint="Only launches are retired.",
        )
    _move_effect(context.session, row, F.RETIRED, context.caller, context.now)
    row.retired_at = context.now
    watch = await context.session.scalar(select(Watch).where(Watch.side_effect_id == row.id))
    if watch is not None and watch.state in (W.PASSING, W.FAILING):
        move_watch(context.session, watch, W.ENDED, tasks.WORK_JOB, context.now)
    return await _item_of(context.session, row)


async def _launch(session: AsyncSession, project_id: str, effect_id: int) -> SideEffect:
    row = await session.get(SideEffect, effect_id)
    if row is None or row.project_id != project_id:
        raise Refusal(
            "launch_not_found",
            f"There is no launch {effect_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            rule=WRK_17.id,
            hint="List them with `launches list`.",
        )
    return row


@operation(
    "agent.retire_launch",
    summary="Retire a launch that is no longer running. Its watch ends.",
    authority=Authority.AGENT,
    reversibility=Reversibility.IRREVERSIBLE,
    principals=AGENT,
)
async def retire_launch(context: Context, payload: EffectRef) -> EffectItem:
    """Section 7.16: the launching seat or the CEO retires a launch."""
    view = await agent_of(context)
    work_run_only(view)
    row = await _launch(context.session, view.project.id, payload.effect_id)
    if row.seat_id != view.seat.id and view.seat.kind != SeatKind.CEO:
        raise Refusal(
            "not_your_launch",
            "A launch is retired by the agent that launched it, the CEO or the chairman.",
            rule=WRK_17.id,
            hint="Ask the CEO.",
        )
    return await _retire(context, row)


@operation(
    "launches.close_unknown",
    summary="Close a side effect its agent never finished, as outcome unknown.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def close_unknown(context: Context, payload: LaunchRef) -> EffectItem:
    """WRK-16, section 7.16: when the agent that declared a side effect can no longer say
    what happened, the chairman closes it as outcome unknown. Nobody then knows whether
    it fired, so a launch is watched from here on, and can be retired."""
    row = await _launch(context.session, view_of(context).project.id, payload.effect_id)
    row.fired, row.finished_at = None, context.now
    row.outcome = "Closed by the chairman: the outcome is unknown."
    _move_effect(context.session, row, F.FINISHED, context.caller, context.now)
    watch = await context.session.scalar(select(Watch).where(Watch.side_effect_id == row.id))
    if watch is not None:
        move_watch(context.session, watch, W.PASSING, tasks.WORK_JOB, context.now)
    return await _item_of(context.session, row)


@operation(
    "launches.retire",
    summary="Retire a launch. Its watch ends.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def retire(context: Context, payload: LaunchRef) -> EffectItem:
    row = await _launch(context.session, view_of(context).project.id, payload.effect_id)
    return await _retire(context, row)


@operation(
    "launches.list",
    summary="List side effects and launches, with each launch's watch.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_launches(context: Context, payload: ProjectRef) -> EffectList:
    rows = await context.session.scalars(
        select(SideEffect)
        .where(SideEffect.project_id == payload.project_id)
        .order_by(SideEffect.id)
    )
    return EffectList(items=[await _item_of(context.session, row) for row in rows])


async def watch_failed(
    session: AsyncSession, watch: Watch, result: str, now: datetime, project: Project
) -> None:
    """WRK-17: a failing watch is flagged in the chat, alarms the chairman and wakes the
    seat that launched it."""
    effect = await session.get(SideEffect, watch.side_effect_id)
    assert effect is not None
    body = f"A watch is failing on a launch ({effect.what}): {result.strip()[-300:]}"
    await conversation.platform_line(
        session, project.id, body, now, detail={"kind": "watch failing", "alarm": True}
    )
    await push.raise_alarm(session, project, body, now)
    notices.notify(
        session, project.id, effect.seat_id, "watch failing",
        f"{body}\nFix what you launched, or retire it with agent_retire_launch "
        f"(effect_id={effect.id}).",
        now, urgent=True,
    )  # fmt: skip


def due(watch: Watch, now: datetime) -> bool:
    return watch.last_run_at is None or now >= watch.last_run_at + timedelta(
        seconds=watch.interval_seconds
    )


async def last_verified(session: AsyncSession, project_id: str) -> datetime | None:
    return await session.scalar(
        select(Evidence.settled_at)
        .where(Evidence.project_id == project_id, Evidence.state == E.VERIFIED)
        .order_by(Evidence.settled_at.desc())
        .limit(1)
    )
