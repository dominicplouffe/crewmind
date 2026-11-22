"""The CEO reserve (GOV-10): a slice of the budget the CEO may draw once, to finish work
that is nearly done. Every refusal carries the arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import notices
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import authority, estimates
from crewmind.domain.planning.authority import Actor
from crewmind.domain.planning.model import OPEN_SCOPE, RequirementState
from crewmind.domain.planning.readiness import PLANNING_JOB
from crewmind.domain.projects.model import ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Bet, Project, Requirement, ReserveDraw

GOV_10 = rules.register(
    Rule("GOV-10", "The CEO reserve is drawn once, in wrap-up, only when nearly done.")
)
RESERVE_CHANGED = event_type("reserve.changed", "A CEO reserve draw was asked, made or ended.")
REQUESTED, DRAWN, DENIED, CANCELLED = "requested", budget.RESERVE_DRAWN, "denied", "cancelled"
REASON_MIN_CHARACTERS = 10  # GOV-10: a draw is recorded with the CEO's reason
PLATFORM = "platform"


@dataclass(frozen=True)
class Eligibility:
    code: str | None
    tokens: int
    arithmetic: str

    @property
    def ok(self) -> bool:
        return self.code is None


async def _earlier(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> list[ReserveDraw]:
    """Draws that count against "once": per project, or per month for Operate."""
    wanted = select(ReserveDraw).where(
        ReserveDraw.project_id == project.id,
        ReserveDraw.state.in_([REQUESTED, DRAWN, CANCELLED]),
    )
    since = await budget.period_start(session, settings, project, now)
    if since is not None:
        wanted = wanted.where(ReserveDraw.at >= since)
    return list(await session.scalars(wanted.order_by(ReserveDraw.id)))


async def eligibility(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> Eligibility:
    """GOV-10: whether the reserve may be drawn now, with the numbers either way."""
    values = await settings.effective(session, authority.subject(project))
    size = int(values["budget.tokens"]) * int(values["budget.ceo_reserve"]) // 100
    state = await budget.state(session, settings, project, now)
    spend = f"{budget.arithmetic(state)}; the reserve is {size:,} tokens"
    if size == 0:
        return Eligibility("reserve_off", 0, "`budget.ceo_reserve` is 0, so there is no reserve.")
    if await _earlier(session, settings, project, now):
        period = "this month" if project.type == ProjectType.OPERATE else "in this project"
        return Eligibility(
            "reserve_already_drawn", size, f"The reserve was already asked for or drawn {period}."
        )
    if state.spent < state.wrapup_at:
        return Eligibility(
            "not_in_wrap_up",
            size,
            f"The reserve is drawn only after spend reaches wrap-up at {state.wrapup_at:,} "
            f"tokens ({spend}).",
        )
    if project.type == ProjectType.EXPLORE:
        active = await session.scalar(
            select(func.count())
            .select_from(Bet)
            .where(Bet.project_id == project.id, Bet.state == "active")
        )
        if not active:
            return Eligibility("nothing_to_finish", size, f"No bet is active ({spend}).")
        return Eligibility(
            None, size, f"{active} active bets get their findings; no new bet may open ({spend})."
        )
    counts = dict(
        (
            await session.execute(
                select(Requirement.state, func.count())
                .where(Requirement.project_id == project.id)
                .group_by(Requirement.state)
            )
        ).all()
    )
    met = int(counts.get(RequirementState.MET, 0))
    still_open = sum(int(counts.get(one, 0)) for one in OPEN_SCOPE)
    if project.type == ProjectType.OPERATE:
        if not still_open:
            return Eligibility("nothing_to_finish", size, f"No requirement is open ({spend}).")
        return Eligibility(
            None, size, f"{still_open} open requirements of this cycle are funded ({spend})."
        )
    accepted = met + still_open
    share = 100 * met // accepted if accepted else 0
    wanted = int(values["budget.reserve_min_done"])
    plan = await estimates.plan(session, project)
    done = (
        f"{met} of {accepted} accepted requirements are met ({share}%; "
        f"`budget.reserve_min_done` is {wanted}%)"
    )
    if not accepted or share < wanted:
        return Eligibility("not_nearly_done", size, f"{done}. {spend}.")
    if plan.tokens is None:
        return Eligibility(
            "plan_tokens_unknown", size, f"{done}, but plan tokens are {plan.tokens_text()}."
        )
    rest = f"{done}. The rest needs {plan.tokens_text()}; the reserve is {size:,} tokens"
    if plan.tokens > size:
        return Eligibility("rest_does_not_fit", size, f"{rest}, so it does not fit.")
    return Eligibility(None, size, f"{rest}, so it fits.")


def _record(session: AsyncSession, draw: ReserveDraw, actor: Actor | None, now: datetime) -> None:
    append_event(
        session,
        type=RESERVE_CHANGED,
        caller=actor.caller if actor else PLANNING_JOB,
        at=now,
        subject=("reserve_draw", str(draw.id)),
        project_id=draw.project_id,
        after={"state": draw.state, "tokens": draw.tokens},
        detail={"reason": draw.reason, "arithmetic": draw.arithmetic},
    )


async def _drawn(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    draw: ReserveDraw,
    now: datetime,
) -> None:
    """Announce a draw to the chairman at once, and lift the wall if it was holding."""
    who = "The platform" if draw.drawn_by == PLATFORM else "The CEO"
    await conversation.platform_line(
        session,
        project.id,
        f"{who} drew the CEO reserve of {draw.tokens:,} tokens: {draw.reason} "
        f"{draw.arithmetic} It finishes existing scope only. You can cancel the draw.",
        now,
        detail={"kind": "reserve drawn", "draw": draw.id},
    )
    await session.flush()
    await budget.follow_wall(session, settings, project, now)


async def draw(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    reason: str,
    now: datetime,
) -> ReserveDraw:
    """GOV-10: the CEO draws the whole reserve, or, where the chairman holds the verb,
    asks for it. Refused with the arithmetic unless the project is nearly done."""
    if len(reason.strip()) < REASON_MIN_CHARACTERS:
        raise Refusal(
            "reason_too_short",
            f"A draw is recorded with a reason of at least {REASON_MIN_CHARACTERS} characters.",
            rule=GOV_10.id,
        )
    found = await eligibility(session, settings, project, now)
    if not found.ok:
        assert found.code is not None
        raise Refusal(
            found.code,
            f"The reserve cannot be drawn. {found.arithmetic}",
            rule=GOV_10.id,
            hint="Beyond the reserve, ask the chairman for a higher budget.",
        )
    held_by_ceo = await authority.ceo_holds(session, settings, project, "reserve_draw")
    row = ReserveDraw(
        project_id=project.id,
        state=DRAWN if held_by_ceo else REQUESTED,
        tokens=found.tokens,
        reason=reason.strip(),
        arithmetic=found.arithmetic,
        drawn_by=actor.id,
        at=now,
    )
    session.add(row)
    await session.flush()
    _record(session, row, actor, now)
    if held_by_ceo:
        await _drawn(session, settings, project, row, now)
    else:
        await conversation.platform_line(
            session,
            project.id,
            f"The CEO asks to draw the CEO reserve of {row.tokens:,} tokens: {row.reason} "
            f"{row.arithmetic} Approve or deny it in the plan. Unanswered, it stays denied.",
            now,
            detail={"kind": "reserve asked", "draw": row.id},
        )
    return row


async def draw_at_wall(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> bool:
    """GOV-3, GOV-10: when the wall arrives while a draw is eligible, undrawn and the
    CEO's to make, the platform draws it rather than pausing a nearly finished project."""
    if not await authority.ceo_holds(session, settings, project, "reserve_draw"):
        return False
    found = await eligibility(session, settings, project, now)
    if not found.ok:
        return False
    row = ReserveDraw(
        project_id=project.id,
        state=DRAWN,
        tokens=found.tokens,
        reason="The budget wall arrived with the project nearly done.",
        arithmetic=found.arithmetic,
        drawn_by=PLATFORM,
        at=now,
    )
    session.add(row)
    await session.flush()
    _record(session, row, None, now)
    ceo = await ceo_of(session, project.id)
    notices.notify(
        session,
        project.id,
        ceo.id,
        "reserve drawn",
        f"The platform drew the CEO reserve of {row.tokens:,} tokens at the wall. "
        "It finishes existing scope only.",
        now,
    )
    await _drawn(session, settings, project, row, now)
    return True


budget.wall_hooks.append(draw_at_wall)


async def get(session: AsyncSession, project_id: str, draw_id: int) -> ReserveDraw:
    row = await session.get(ReserveDraw, draw_id)
    if row is None or row.project_id != project_id:
        raise Refusal("draw_not_found", "There is no such draw.", kind=RefusalKind.NOT_FOUND)
    return row


async def answer(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    row: ReserveDraw,
    approve: bool,
    now: datetime,
) -> None:
    """GOV-10: under supervised authority the chairman approves or denies a draw."""
    assert actor.is_chairman
    if row.state != REQUESTED:
        raise Refusal("draw_not_waiting", f"This draw is {row.state}, not waiting for an answer.")
    row.state, row.settled_at = (DRAWN if approve else DENIED), now
    _record(session, row, actor, now)
    ceo = await ceo_of(session, project.id)
    word = "approved" if approve else "denied"
    notices.notify(
        session, project.id, ceo.id, "reserve", f"The chairman {word} the reserve draw.", now,
        urgent=True,
    )  # fmt: skip
    if approve:
        await _drawn(session, settings, project, row, now)


async def cancel(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    row: ReserveDraw,
    now: datetime,
) -> None:
    """GOV-10: the chairman can cancel a draw at any time. If spend is already past the
    budget, the project then pauses."""
    assert actor.is_chairman
    if row.state != DRAWN:
        raise Refusal("draw_not_drawn", f"This draw is {row.state}; only a drawn one is cancelled.")
    row.state, row.settled_at = CANCELLED, now
    _record(session, row, actor, now)
    await session.flush()
    await budget.follow_wall(session, settings, project, now)


async def drawn_now(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> bool:
    return await budget.reserve_drawn(session, settings, project, now) > 0
