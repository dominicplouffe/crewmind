"""Flags (HUM-6): opened by the platform from arithmetic only, one live flag per
condition. A state flag stays until its condition clears, whatever is said about it. An
event flag closes when the CEO raises it with a proposal and the chairman acknowledges."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import service as conversation
from crewmind.domain.decisions import items
from crewmind.domain.decisions.items import Kind
from crewmind.domain.decisions.model import LIVE, ItemState
from crewmind.domain.execution.model import RunKind, RunState
from crewmind.domain.planning import authority
from crewmind.domain.settings.service import SettingsService
from crewmind.domain.work.model import OPEN_STATES, TaskState
from crewmind.storage.models import (
    Commitment,
    Correction,
    DecisionItem,
    Project,
    ProjectGuard,
    Requirement,
    Run,
    Seat,
    Task,
    Watch,
)

HUM_6 = rules.register(
    Rule("HUM-6", "A flag opens from arithmetic; a state flag closes only when it clears.")
)
FLAG = "flag"
STATE, EVENT = "state", "event"
KINDS: dict[str, str] = {
    "recurring requirement missed": EVENT,
    "cycle missed": EVENT,
    "deadline at risk": STATE,
    "losing ground": STATE,
    "work starved": STATE,
    "self-gated": STATE,
    "budget wrap-up": STATE,
    "spinning": STATE,
    "slow start": STATE,
    "no visible output": STATE,
    "seat idle": STATE,
    "watch failing": STATE,
    "stall": STATE,
    "listening": EVENT,
    "mistake report owed": STATE,
}
"""HUM-6: every flag kind, and whether it is a state or an event flag."""
GUARDS = {
    "stalled": "stall",
    "spinning": "spinning",
    "slow start": "slow start",
    "no output": "no visible output",
    "seat idle": "seat idle",
}
"""The runaway and speed guards of phases 4 and 5, and the flag each one shows as."""
STARVED_AFTER = timedelta(hours=1)  # HUM-6: a cap blocked claimable work for an hour
LISTENING_WINDOW = timedelta(days=7)  # HUM-6
PROPOSAL_MIN_CHARACTERS = 20

items.register(
    Kind(
        name=FLAG,
        filed_by="platform",
        actions=("acknowledge",),
        title=lambda f: f"Flag: {f['flag']}",
        desk=False,
        decide_from=ItemState.RAISED,
        decided_state=ItemState.ACKNOWLEDGED,
    )
)


async def live(session: AsyncSession, project_id: str) -> list[DecisionItem]:
    rows = await session.scalars(
        select(DecisionItem)
        .where(
            DecisionItem.project_id == project_id,
            DecisionItem.kind == FLAG,
            DecisionItem.state.in_(LIVE),
        )
        .order_by(DecisionItem.id)
    )
    return list(rows)


async def open_flag(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    flag: str,
    cause: str,
    now: datetime,
    *,
    key: str = "",
    announce: bool = True,
) -> DecisionItem | None:
    """Open a flag unless one is already live for this condition (HUM-6). An event flag
    is opened once per occurrence: `key` names the occurrence."""
    wanted = select(DecisionItem).where(
        DecisionItem.project_id == project.id, DecisionItem.kind == FLAG
    )
    if KINDS[flag] == STATE:
        wanted = wanted.where(DecisionItem.state.in_(LIVE))
    for item in await session.scalars(wanted):
        if item.fields["flag"] == flag and item.fields["key"] == key:
            return None
    return await items.file(
        session,
        settings,
        project,
        FLAG,
        filer=items.ITEMS_JOB,
        fields={"flag": flag, "key": key, "type": KINDS[flag], "cause": cause},
        recommendation=cause[:300] if len(cause) >= 10 else f"{flag}: {cause}",
        if_declined="",
        now=now,
        announce=announce,
    )


async def clear(
    session: AsyncSession, project: Project, flag: str, now: datetime, *, key: str = ""
) -> None:
    """A state flag clears when its condition no longer holds."""
    for item in await live(session, project.id):
        if item.fields["flag"] == flag and item.fields["key"] == key:
            item.outcome = "cleared"
            items.move(session, item, ItemState.CLEARED, items.ITEMS_JOB, now)


async def raise_flag(
    session: AsyncSession,
    project: Project,
    item: DecisionItem,
    seat: Seat,
    caller: Caller,
    proposal: str,
    now: datetime,
) -> None:
    """HUM-6: the CEO raises a flag in the chat with a proposal. That does not close a
    state flag: only its condition clearing does."""
    if item.kind != FLAG:
        raise Refusal("not_a_flag", "Only a flag is raised.", rule=HUM_6.id)
    if len(proposal.strip()) < PROPOSAL_MIN_CHARACTERS:
        raise Refusal(
            "flag_needs_a_proposal",
            f"Raise a flag with what you propose to do, in at least "
            f"{PROPOSAL_MIN_CHARACTERS} characters.",
            rule=HUM_6.id,
        )
    items.move(session, item, ItemState.RAISED, caller, now, {"proposal": proposal.strip()})
    item.outcome_detail = {"proposal": proposal.strip()}
    await conversation.platform_line(
        session,
        project.id,
        f"{seat.display_name} raises the flag {item.fields['flag']}: {item.fields['cause']} "
        f"Proposal: {proposal.strip()}",
        now,
        detail={"kind": "decision item", "item": item.id, "item_kind": FLAG},
    )


async def _conditions(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> dict[tuple[str, str], str]:
    """Every state condition that holds now, as (flag, key) to its cause."""
    found: dict[tuple[str, str], str] = {}
    guards = await session.scalars(
        select(ProjectGuard).where(
            ProjectGuard.project_id == project.id, ProjectGuard.cleared_at.is_(None)
        )
    )
    for guard in guards:
        if guard.kind in GUARDS:
            found[(GUARDS[guard.kind], "")] = guard.cause
    commitment = await session.scalar(
        select(Commitment)
        .where(Commitment.project_id == project.id, Commitment.state.in_(["at risk", "breached"]))
        .limit(1)
    )
    if commitment is not None and commitment.date is not None:
        found[("deadline at risk", "")] = (
            f"The commitment is {commitment.state}: its date is "
            f"{commitment.date.strftime('%d %b %Y %H:%M UTC')}."
        )
    losing = await session.scalars(
        select(Requirement).where(
            Requirement.project_id == project.id, Requirement.metric.is_not(None)
        )
    )
    for requirement in losing:
        if (requirement.metric or {}).get("losing") and requirement.state != "met":
            found[("losing ground", str(requirement.id))] = (
                f"Requirement {requirement.id} is moving away from its target."
            )
    state = await budget.state(session, settings, project, now)
    if state.spent >= state.wrapup_at and project.state == "running":
        found[("budget wrap-up", "")] = f"Wrap-up mode: {budget.arithmetic(state)}."
    failing = await session.scalars(
        select(Watch).where(Watch.project_id == project.id, Watch.state == "failing")
    )
    for watch in failing:
        found[("watch failing", str(watch.id))] = (
            f"The watch on launch {watch.side_effect_id} is failing."
        )
    if project.state == "running":
        await _work_conditions(session, project, now, found)
    owed = await session.scalar(
        select(func.count())
        .select_from(DecisionItem)
        .where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == "mistake report",
            DecisionItem.state == ItemState.OPEN,
            DecisionItem.opened_at <= now - timedelta(hours=24),
        )
    )
    if owed:
        found[("mistake report owed", "")] = (
            f"{owed} mistake reports have been owed by the CEO for more than 24 hours."
        )
    return found


async def _work_conditions(
    session: AsyncSession, project: Project, now: datetime, found: dict[tuple[str, str], str]
) -> None:
    """Work starved: a run has waited an hour for a lease. Self-gated: every open task
    waits only on a not-before time the CEO set."""
    waiting = await session.scalar(
        select(func.min(Run.queued_at)).where(
            Run.project_id == project.id,
            Run.kind == RunKind.WORK,
            Run.state == RunState.QUEUED,
        )
    )
    if waiting is not None and now - waiting >= STARVED_AFTER:
        found[("work starved", "")] = (
            "A work run has waited more than an hour for a lease: a limit is holding "
            "claimable work back."
        )
    open_tasks = list(
        await session.scalars(
            select(Task).where(Task.project_id == project.id, Task.state.in_(OPEN_STATES))
        )
    )
    gated = [
        task
        for task in open_tasks
        if task.state == TaskState.READY and task.not_before is not None and task.not_before > now
    ]
    if open_tasks and len(gated) == len(open_tasks):
        found[("self-gated", "")] = (
            f"All {len(gated)} open tasks wait on a not-before time the CEO set."
        )


async def sync(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """HUM-6: open a flag for each state condition that holds and has none, and clear
    each state flag whose condition no longer holds. Safe to run any number of times."""
    holding = await _conditions(session, settings, project, now)
    for (flag, key), cause in holding.items():
        said = flag in GUARDS.values()
        await open_flag(session, settings, project, flag, cause, now, key=key, announce=not said)
    for item in await live(session, project.id):
        about = (item.fields["flag"], item.fields["key"])
        if KINDS[about[0]] == STATE and about not in holding:
            item.outcome = "cleared"
            items.move(session, item, ItemState.CLEARED, items.ITEMS_JOB, now)
    await _listening(session, settings, project, now)


async def _listening(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """HUM-6: an agent whose corrections exceed `listening.flag_at` in 7 days."""
    limit = int(await settings.get(session, authority.subject(project), "listening.flag_at"))
    rows = (
        await session.execute(
            select(Seat.name, func.count(), func.max(Correction.id))
            .join(Correction, Correction.seat_id == Seat.id)
            .where(
                Correction.project_id == project.id,
                Correction.created_at >= now - LISTENING_WINDOW,
            )
            .group_by(Seat.name)
        )
    ).all()
    for name, count, newest in rows:
        if int(count) > limit:
            await open_flag(
                session, settings, project, "listening",
                f"{name} was corrected {count} times in 7 days.", now, key=f"{name}:{newest}",
            )  # fmt: skip


async def event(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    flag: str,
    cause: str,
    now: datetime,
    key: str,
) -> None:
    """Open an event flag for something that just happened."""
    assert KINDS[flag] == EVENT
    await open_flag(session, settings, project, flag, cause, now, key=key)


def view_fields(item: DecisionItem) -> dict[str, Any]:
    return dict(item.fields)
