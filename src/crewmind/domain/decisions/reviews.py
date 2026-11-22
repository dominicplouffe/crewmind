"""Status reviews (HUM-9): built by the platform on a schedule at 0 tokens, with a frozen
snapshot of the numbers, the CEO's narrative if it wrote one, and six levers for the
chairman. A green review closes itself. Reviews never block work."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.budget import service as budget
from crewmind.domain.decisions import flags, items
from crewmind.domain.decisions.items import Kind
from crewmind.domain.decisions.model import ItemState
from crewmind.domain.execution import notices
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import authority, projection
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.events import append_event
from crewmind.storage.models import AuditSample, Commitment, DecisionItem, Project, Requirement

HUM_9 = rules.register(
    Rule("HUM-9", "A review's lever is the chairman's, with a reason; its numbers are frozen.")
)
REVIEW = "status review"
LEVERS = ("cut", "add", "reword", "move the date", "raise the budget", "accept the slip")
GREEN_CLOSES_AFTER = timedelta(hours=24)  # HUM-9
REASON_MIN_CHARACTERS = 10
NARRATIVE_MIN_CHARACTERS = 20
CYCLE_PERIODS = ("weekly", "monthly", "quarterly")

items.register(
    Kind(
        name=REVIEW,
        filed_by="platform",
        actions=("close",),
        default="close",
        title=lambda f: f"Status review {f['number']}: {'green' if f['green'] else 'needs a look'}",
        desk=False,
        positive=("close",),
    )
)


async def _reviews(session: AsyncSession, project_id: str) -> list[DecisionItem]:
    rows = await session.scalars(
        select(DecisionItem)
        .where(DecisionItem.project_id == project_id, DecisionItem.kind == REVIEW)
        .order_by(DecisionItem.id)
    )
    return list(rows)


async def snapshot(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    since: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    """The numbers as they are now. Once stored on a review they do not change."""
    counts = dict(
        (
            await session.execute(
                select(Requirement.state, func.count())
                .where(Requirement.project_id == project.id)
                .group_by(Requirement.state)
            )
        ).all()
    )
    state = await budget.state(session, settings, project, now)
    commitment = await session.scalar(
        select(Commitment)
        .where(Commitment.project_id == project.id)
        .order_by(Commitment.id.desc())
        .limit(1)
    )
    failed = (
        select(func.count())
        .select_from(AuditSample)
        .where(AuditSample.project_id == project.id, AuditSample.verdict == "failed")
    )
    if since is not None:
        failed = failed.where(AuditSample.considered_at >= since)
    pace = await projection.pace(session, settings, project, now)
    open_flags = [item.fields["flag"] for item in await flags.live(session, project.id)]
    return {
        "requirements": {str(name): int(count) for name, count in counts.items()},
        "spent": state.spent,
        "budget": state.wall,
        "in_wrap_up": state.spent >= state.wrapup_at,
        "commitment": commitment.state if commitment else None,
        "projection": pace.projection.text(),
        "failed_audits": int(await session.scalar(failed) or 0),
        "flags": open_flags,
    }


def is_green(numbers: dict[str, Any]) -> bool:
    """HUM-9: nothing at risk, no failed audit, within budget."""
    return (
        numbers["commitment"] not in ("at risk", "breached")
        and numbers["failed_audits"] == 0
        and not numbers["in_wrap_up"]
        and not numbers["flags"]
    )


async def build(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> DecisionItem:
    """HUM-9: build a review at 0 tokens, beside the previous review's levers. It is
    built even with an empty board or a spent budget."""
    earlier = await _reviews(session, project.id)
    previous = earlier[-1] if earlier else None
    numbers = await snapshot(
        session, settings, project, previous.opened_at if previous else None, now
    )
    green = is_green(numbers)
    item = await items.file(
        session,
        settings,
        project,
        REVIEW,
        filer=items.ITEMS_JOB,
        fields={
            "number": len(earlier) + 1,
            "green": green,
            "numbers": numbers,
            "previous_levers": previous.fields.get("levers", []) if previous else [],
            "previous_numbers": previous.fields.get("numbers") if previous else None,
            "narrative": None,
            "levers": [],
        },
        recommendation="Nothing needs you; it closes itself in 24 hours."
        if green
        else "Look at what is at risk and use a lever if one is needed.",
        if_declined="",
        window=GREEN_CLOSES_AFTER if green else None,
        default="close" if green else None,
        now=now,
    )
    ceo = await ceo_of(session, project.id)
    notices.notify(
        session, project.id, ceo.id, "status review",
        f"Status review {item.fields['number']} is built (item {item.id}). Add your "
        "narrative with agent_write_review_narrative: answer each item of the last plan.",
        now,
    )  # fmt: skip
    return item


async def build_if_due(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> DecisionItem | None:
    """Every `review.every` from the project's start; Operate projects with weekly or
    longer cycles are reviewed at the cycle roll instead."""
    if project.state not in ("running", "held", "paused"):
        return None
    values = await settings.effective(session, authority.subject(project))
    if project.type == "operate" and values.get("cycle.period") in CYCLE_PERIODS:
        return None
    earlier = await _reviews(session, project.id)
    last = earlier[-1].opened_at if earlier else await projection.started_at(session, project.id)
    every = timedelta(seconds=int(values["review.every"]))
    if last is None or now - last < every:
        return None
    return await build(session, settings, project, now)


async def write_narrative(
    session: AsyncSession, item: DecisionItem, caller: Caller, text: str, now: datetime
) -> None:
    """HUM-9: the CEO may add a narrative to an open review. The numbers stay frozen."""
    if item.kind != REVIEW or item.state != ItemState.OPEN:
        raise Refusal("no_open_review", "A narrative goes on an open status review.", rule=HUM_9.id)
    if len(text.strip()) < NARRATIVE_MIN_CHARACTERS:
        raise Refusal(
            "narrative_too_short",
            f"A narrative has at least {NARRATIVE_MIN_CHARACTERS} characters.",
            rule=HUM_9.id,
        )
    item.fields = {**item.fields, "narrative": text.strip()}
    append_event(
        session, type=items.ITEM_EDITED, caller=caller, at=now,
        subject=("item", str(item.id)), project_id=item.project_id, after={"narrative": True},
    )  # fmt: skip


async def use_lever(
    session: AsyncSession,
    item: DecisionItem,
    caller: Caller,
    lever: str,
    reason: str,
    now: datetime,
) -> None:
    """HUM-9: the chairman's six levers, each recorded with a reason. The lever records
    the decision; the change itself is made with its own operation."""
    if item.kind != REVIEW or item.state != ItemState.OPEN:
        raise Refusal("no_open_review", "A lever is used on an open status review.", rule=HUM_9.id)
    if lever not in LEVERS or len(reason.strip()) < REASON_MIN_CHARACTERS:
        raise Refusal(
            "lever_needs_a_reason",
            f"Use one of: {', '.join(LEVERS)}; with a reason of at least "
            f"{REASON_MIN_CHARACTERS} characters.",
            rule=HUM_9.id,
        )
    used = [*item.fields.get("levers", []), {"lever": lever, "reason": reason.strip()}]
    item.fields = {**item.fields, "levers": used}
    item.deadline = None
    append_event(
        session, type=items.ITEM_EDITED, caller=caller, at=now,
        subject=("item", str(item.id)), project_id=item.project_id,
        after={"lever": lever}, detail={"reason": reason.strip()},
    )  # fmt: skip
