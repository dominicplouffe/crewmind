"""Mistake reports (HUM-8): the platform opens one when the chairman marks a correction
as costly, when an audit sample fails, or when a commitment is breached. The CEO files
it; the platform computes what it cost; the prevention becomes a pinned lesson."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.decisions import items
from crewmind.domain.decisions.items import Kind
from crewmind.domain.decisions.model import ItemState
from crewmind.domain.execution import notices
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.models import DecisionItem, Event, LedgerLine, Project

HUM_8 = rules.register(
    Rule("HUM-8", "Only the CEO files a mistake report, once; a filed report is not edited.")
)
MISTAKE = "mistake report"
PART_MIN_CHARACTERS = 10

items.register(
    Kind(
        name=MISTAKE,
        filed_by="platform",
        actions=(),
        title=lambda f: f"Mistake report owed: {f['because']}",
        desk=False,
    )
)


async def tokens_of_runs(session: AsyncSession, run_ids: list[str]) -> int:
    if not run_ids:
        return 0
    found = await session.scalar(
        select(func.coalesce(func.sum(LedgerLine.counted), 0)).where(LedgerLine.run_id.in_(run_ids))
    )
    return int(found or 0)


async def tokens_of_task(session: AsyncSession, project_id: str, task_id: int) -> int:
    """The tokens of the runs that changed this task."""
    vias = await session.scalars(
        select(func.distinct(Event.via)).where(
            Event.project_id == project_id,
            Event.subject_kind == "task",
            Event.subject_id == str(task_id),
            Event.via.like("run:%"),
        )
    )
    return await tokens_of_runs(session, [via.removeprefix("run:") for via in vias])


async def tokens_since(session: AsyncSession, project_id: str, since: datetime) -> int:
    found = await session.scalar(
        select(func.coalesce(func.sum(LedgerLine.counted), 0)).where(
            LedgerLine.project_id == project_id, LedgerLine.at >= since
        )
    )
    return int(found or 0)


async def open_report(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    *,
    because: str,
    subject: tuple[str, str],
    cost_tokens: int,
    now: datetime,
) -> DecisionItem:
    """HUM-8: open a report the CEO now owes. The cost is the platform's number."""
    existing = await items.open_for(session, MISTAKE, subject)
    if existing is not None:
        return existing
    item = await items.file(
        session,
        settings,
        project,
        MISTAKE,
        filer=items.ITEMS_JOB,
        fields={"because": because, "cost_tokens": cost_tokens},
        recommendation=f"The CEO owes a mistake report: {because}.",
        if_declined="",
        subject=subject,
        now=now,
    )
    ceo = await ceo_of(session, project.id)
    notices.notify(
        session, project.id, ceo.id, "mistake report owed",
        f"You owe a mistake report (item {item.id}): {because}. It cost {cost_tokens:,} "
        "tokens. File what was wrong, the cause, the fix and the prevention with "
        "agent_file_mistake_report.",
        now, urgent=True,
    )  # fmt: skip
    return item


async def file_report(
    session: AsyncSession,
    item: DecisionItem,
    caller: Caller,
    parts: dict[str, str],
    now: datetime,
) -> None:
    """HUM-8: the CEO files what was wrong, the cause, the fix and the prevention. The
    prevention is saved as a pinned lesson. A filed report cannot be edited."""
    if item.kind != MISTAKE:
        raise Refusal("not_a_mistake_report", "That item is not a mistake report.", rule=HUM_8.id)
    short = [name for name, text in parts.items() if len(text.strip()) < PART_MIN_CHARACTERS]
    if short:
        raise Refusal(
            "report_incomplete",
            f"Say more about: {', '.join(short)}. Each part has at least "
            f"{PART_MIN_CHARACTERS} characters.",
            rule=HUM_8.id,
        )
    fields: dict[str, Any] = {**item.fields, **{k: v.strip() for k, v in parts.items()}}
    items.move(session, item, ItemState.FILED, caller, now)
    item.fields, item.outcome = fields, "filed"


async def lessons(session: AsyncSession, project_id: str) -> list[tuple[int, str]]:
    """MEM-1: the prevention of every filed mistake report, as (item id, lesson)."""
    rows = await session.scalars(
        select(DecisionItem)
        .where(
            DecisionItem.project_id == project_id,
            DecisionItem.kind == MISTAKE,
            DecisionItem.state == ItemState.FILED,
        )
        .order_by(DecisionItem.id)
    )
    return [(row.id, str(row.fields.get("prevention", ""))) for row in rows]
