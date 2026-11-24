"""The token budget, the ledger and the wall (GOV-2, GOV-3, GOV-9, LLM-9, INV-8, INV-9).

Spend counts non-cached tokens only: input not served from a cache, cache writes, and
output. Cache reads are recorded and shown but cost the budget nothing (ADR-0003).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import platform_job
from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.decisions import items
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.projects import lifecycle
from nightsquad.domain.projects.model import HOLDABLE, Hold, ProjectType
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject, project_subject
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import LedgerLine, Project, ReserveDraw

GOV_3 = rules.register(Rule("GOV-3", "The budget is the wall: at it, nothing new is leased."))
GOV_6 = rules.register(Rule("GOV-6", "A run cannot call a model past its per-run token cap."))

BUDGET_THRESHOLD = event_type("budget.threshold_reached", "Spend crossed a budget threshold.")
BUDGET_JOB = platform_job("gateway: budget")
WALL_JOB = platform_job("scheduler: budget wall")


@dataclass(frozen=True)
class Usage:
    """Tokens of one model call, by kind (LLM-9)."""

    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    @property
    def counted(self) -> int:
        """What the call costs the budget: everything but cache reads (GOV-2)."""
        return self.input + self.cache_write + self.output


@dataclass(frozen=True)
class BudgetState:
    spent: int
    wall: int
    warn_at: int
    wrapup_at: int
    reserve: int = 0
    """Tokens of a drawn CEO reserve, already counted in `wall` (GOV-3, GOV-10)."""

    @property
    def remaining(self) -> int:
        return max(self.wall - self.spent, 0)

    @property
    def at_wall(self) -> bool:
        return self.spent >= self.wall


def _subject(project: Project) -> Subject:
    return Subject(Scope.PROJECT, project.id, project.type)


async def period_start(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> datetime | None:
    """When the budget in force began: the start of this calendar month in the project's
    timezone for an Operate project, and never for the others (GOV-2)."""
    if project.type != ProjectType.OPERATE:
        return None
    zone = ZoneInfo(await settings.get(session, _subject(project), "project.timezone"))
    local = now.astimezone(zone)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def spent(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> int:
    """Tokens counted against the budget: all of them, or this calendar month's in the
    project's timezone for an Operate project (GOV-2)."""
    statement = select(func.coalesce(func.sum(LedgerLine.counted), 0)).where(
        LedgerLine.project_id == project.id, LedgerLine.unit == "tokens"
    )
    since = await period_start(session, settings, project, now)
    if since is not None:
        statement = statement.where(LedgerLine.at >= since)
    return int(await session.scalar(statement) or 0)


RESERVE_DRAWN = "drawn"


async def reserve_drawn(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> int:
    """Tokens of the CEO reserve drawn for the budget in force (GOV-10)."""
    statement = select(func.coalesce(func.sum(ReserveDraw.tokens), 0)).where(
        ReserveDraw.project_id == project.id, ReserveDraw.state == RESERVE_DRAWN
    )
    since = await period_start(session, settings, project, now)
    if since is not None:
        statement = statement.where(ReserveDraw.at >= since)
    return int(await session.scalar(statement) or 0)


async def state(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> BudgetState:
    values = await settings.effective(session, _subject(project))
    base = int(values["budget.tokens"])
    reserve = await reserve_drawn(session, settings, project, now)
    return BudgetState(
        spent=await spent(session, settings, project, now),
        wall=base + reserve,
        warn_at=base * int(values["budget.warn_at"]) // 100,
        wrapup_at=base * int(values["budget.wrapup_at"]) // 100,
        reserve=reserve,
    )


async def record(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    usage: Usage,
    now: datetime,
    *,
    run_id: str | None,
    seat_id: str | None,
    credential_id: str | None,
    provider: str,
    model: str,
) -> BudgetState:
    """Write the ledger line for one model call, then act on any threshold it crossed.
    Every call is metered here, at the gateway, whatever becomes of the run (P9, INV-8)."""
    before = await state(session, settings, project, now)
    session.add(
        LedgerLine(
            project_id=project.id,
            run_id=run_id,
            seat_id=seat_id,
            credential_id=credential_id,
            kind="model",
            unit="tokens",
            provider=provider,
            model=model,
            input_tokens=usage.input,
            output_tokens=usage.output,
            cache_write_tokens=usage.cache_write,
            cache_read_tokens=usage.cache_read,
            counted=usage.counted,
            at=now,
        )
    )
    await session.flush()
    after = replace(before, spent=before.spent + usage.counted)
    await _crossed(session, settings, project, before, after, now)
    return after


def arithmetic(budget: BudgetState) -> str:
    """The numbers every budget message states (GOV-9)."""
    share = 100 * budget.spent // budget.wall if budget.wall else 100
    return f"{budget.spent:,} of {budget.wall:,} tokens used ({share}%)"


async def _crossed(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    before: BudgetState,
    after: BudgetState,
    now: datetime,
) -> None:
    ceo = await ceo_of(session, project.id)
    steps = (
        ("warning", after.warn_at, "Budget warning", "the project has passed its warning level"),
        ("wrap-up", after.wrapup_at, "Budget wrap-up", "the project is in wrap-up mode"),
    )
    for name, level, title, meaning in steps:
        if before.spent < level <= after.spent:
            text = f"{title}: {arithmetic(after)}; {meaning}."
            notices.notify(session, project.id, ceo.id, f"budget {name}", text, now, urgent=True)
            await conversation.platform_line(
                session, project.id, text, now, detail={"kind": f"budget {name}"}
            )
            if name == "wrap-up":
                await items.file(
                    session,
                    settings,
                    project,
                    CHECKPOINT.name,
                    filer=BUDGET_JOB,
                    fields={"spent": after.spent, "budget": after.wall},
                    recommendation="Raise the budget, or let the project land on what is left.",
                    if_declined="The project wraps up within the remaining budget.",
                    subject=("project", project.id),
                    now=now,
                )
            append_event(
                session,
                type=BUDGET_THRESHOLD,
                caller=BUDGET_JOB,
                at=now,
                subject=("project", project.id),
                project_id=project.id,
                after={"threshold": name, "spent": after.spent, "wall": after.wall},
            )
    if after.at_wall and not before.at_wall:
        await reach_wall(session, settings, project, after, now)


async def _checkpoint(done: items.Settling) -> None:
    """GOV-3: the chairman raises the budget, or lets the project land. Landing changes
    nothing: wrap-up mode already holds."""
    if done.outcome != RAISE:
        return
    amount = done.values.get("amount")
    current = int(await done.services.settings.get(done.session, _subject(done.project), TOKENS))
    if amount is None or int(amount) <= current:
        raise Refusal(
            "not_a_raise",
            f"`{TOKENS}` is {current:,}. Give a larger number as `amount`.",
            rule=GOV_3.id,
        )
    await done.services.settings.change(
        done.session,
        await project_subject(done.session, done.project),
        {TOKENS: int(amount)},
        reason=f"Budget checkpoint {done.item.id}: raised by the chairman.",
        caller=done.caller,
        now=done.now,
    )
    await done.session.flush()
    await follow_wall(done.session, done.services.settings, done.project, done.now)


RAISE, LAND, TOKENS = "raise the budget", "land", "budget.tokens"
CHECKPOINT = items.register(
    items.Kind(
        name="budget checkpoint",
        filed_by="platform",
        actions=(RAISE, LAND),
        default=LAND,
        window=timedelta(hours=24),
        title=lambda f: f"Budget checkpoint: {f['spent']:,} of {f['budget']:,} tokens used",
        apply=_checkpoint,
        positive=(RAISE,),
    )
)

wall_hooks: list[Any] = []
"""Called as `(session, settings, project, now)` when spend reaches the wall. One that
returns True has moved the wall above spend, so the project does not pause (GOV-10)."""


async def reach_wall(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    budget: BudgetState,
    now: datetime,
) -> None:
    """GOV-3: at the wall nothing new is leased and the project pauses, unless an eligible
    CEO reserve is drawn instead (GOV-10). In-flight runs finish within their per-run cap.
    The chairman is told where things stand."""
    if project.state not in HOLDABLE:
        return
    for hook in wall_hooks:
        if await hook(session, settings, project, now):
            return
    added = await lifecycle.add_hold(
        session,
        project,
        Hold.BUDGET_WALL,
        caller=BUDGET_JOB,
        now=now,
        note="The token budget is spent.",
        detail={"spent": budget.spent, "wall": budget.wall},
    )
    if not added:
        return
    ceo = await ceo_of(session, project.id)
    text = (
        f"Budget wall reached: {arithmetic(budget)}. The project is paused and nothing new "
        "will start. Runs already in flight finish within their own cap. It resumes when "
        "you raise the budget."
    )
    notices.notify(session, project.id, ceo.id, "budget wall", text, now, urgent=True)
    await conversation.platform_line(
        session, project.id, text, now, detail={"kind": "budget wall", "alarm": True}
    )


async def follow_wall(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """Keep the `budget_wall` hold in step with the numbers: lifted when the wall is above
    spend again (a budget raise, or the Operate monthly reset), added when it is not.
    Safe to run any number of times (BG-3)."""
    if project.state not in HOLDABLE:
        return
    budget = await state(session, settings, project, now)
    held = any(
        row.reason == Hold.BUDGET_WALL for row in await lifecycle.active_holds(session, project.id)
    )
    if held and not budget.at_wall:
        await lifecycle.lift_holds(
            session,
            project,
            frozenset({Hold.BUDGET_WALL}),
            caller=WALL_JOB,
            now=now,
            cause=f"the wall is above spend again: {arithmetic(budget)}",
        )
        await conversation.platform_line(
            session,
            project.id,
            f"The budget wall has lifted: {arithmetic(budget)}.",
            now,
            detail={"kind": "budget wall lifted"},
        )
    elif budget.at_wall and not held:
        await reach_wall(session, settings, project, budget, now)
