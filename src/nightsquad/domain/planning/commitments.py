"""Commitments and target dates (PLN-6 to PLN-9, section 7.6).

A commitment's date is only ever the platform's projection or a date the chairman chose.
No agent writes a date: the CEO's request has no date field.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.decisions import items, mistakes
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.integrations import push
from nightsquad.domain.planning import authority, projection, requirements
from nightsquad.domain.planning.authority import Actor
from nightsquad.domain.planning.model import (
    COMMITMENT_MACHINE,
    LIVE_COMMITMENT,
    OPEN_SCOPE,
    CommitmentState,
    RequirementState,
)
from nightsquad.domain.planning.readiness import PLANNING_JOB
from nightsquad.domain.projects.model import ProjectType
from nightsquad.domain.settings.service import SettingsService
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import Commitment, Project, Requirement, SettingValue, TargetDate

PLN_6 = rules.register(
    Rule("PLN-6", "A commitment's date is the projection or the chairman's, never an agent's.")
)
PLN_8 = rules.register(
    Rule("PLN-8", "While a commitment is at risk or breached, the CEO proposes no new scope.")
)
COMMITMENT_CHANGED = event_type("commitment.state_changed", "A commitment changed state (7.6).")
TARGET_SET = event_type("target_date.set", "The chairman set or cleared a target date (PLN-9).")
C = CommitmentState
HOUR = 3600.0
DAYS_FROM_HOURS = 48  # a gap is worded in days from two days up
REASON_MIN_CHARACTERS = 10  # 7.6: a decline carries a reason


def _move(
    session: AsyncSession,
    commitment: Commitment,
    target: CommitmentState,
    actor: Actor | None,
    now: datetime,
    detail: dict[str, object] | None = None,
) -> None:
    """The one place a commitment changes state (7.6)."""
    before = commitment.state
    if before != target:
        COMMITMENT_MACHINE.check(before, target)
    commitment.state = target
    append_event(
        session,
        type=COMMITMENT_CHANGED,
        caller=actor.caller if actor else PLANNING_JOB,
        at=now,
        subject=("commitment", str(commitment.id)),
        project_id=commitment.project_id,
        before={"state": before},
        after={"state": target, "date": commitment.date.isoformat() if commitment.date else None},
        detail=detail,
    )


async def current(session: AsyncSession, project_id: str) -> Commitment | None:
    """The project's proposed or live commitment. There is at most one (PLN-6)."""
    return await session.scalar(
        select(Commitment)
        .where(
            Commitment.project_id == project_id,
            Commitment.state.in_([C.PROPOSED, *LIVE_COMMITMENT]),
        )
        .order_by(Commitment.id.desc())
        .limit(1)
    )


async def latest(session: AsyncSession, project_id: str) -> Commitment | None:
    return await session.scalar(
        select(Commitment)
        .where(Commitment.project_id == project_id)
        .order_by(Commitment.id.desc())
        .limit(1)
    )


def span_text(earlier: datetime, later: datetime) -> str:
    """The time between two moments, in hours under two days and in days from there."""
    hours = abs((later - earlier).total_seconds()) / HOUR
    return f"{hours:.1f} hours" if hours < DAYS_FROM_HOURS else f"{hours / 24:.1f} days"


def gap_text(date: datetime, projected: datetime | None) -> str:
    """A date beside the platform's projection and the gap between them (PLN-9)."""
    day = date.strftime("%d %b %Y %H:%M UTC")
    if projected is None:
        return f"{day}; the projection is unknown"
    if projected == date:
        where = "the same"
    else:
        where = f"{span_text(date, projected)} {'later' if projected > date else 'earlier'}"
    return f"{day}; the projection is {projected.strftime('%d %b %Y %H:%M UTC')}, {where}"


async def propose(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    now: datetime,
) -> Commitment:
    """PLN-6: the CEO proposes a commitment once a projection exists, one at a time. The
    request has no date: the date is the projection."""
    if project.type != ProjectType.DELIVER:
        raise Refusal(
            "commitments_are_for_deliver", "Only a Deliver project has a commitment.",
            rule=PLN_6.id,
        )  # fmt: skip
    if await current(session, project.id) is not None:
        raise Refusal(
            "commitment_exists",
            "This project already has a commitment. There is only one at a time.",
            rule=PLN_6.id,
        )
    pace = await projection.pace(session, settings, project, now)
    if pace.projection.at is None or pace.projection.kind == projection.NOTHING_LEFT:
        raise Refusal(
            "no_projection",
            f"There is no projection to commit to yet: {pace.projection.text()}.",
            rule=PLN_6.id,
            hint="Estimate the open scope first.",
        )
    commitment = Commitment(
        project_id=project.id,
        state="(new)",
        projected=pace.projection.at,
        scope=[],
        resets=0,
        proposed_at=now,
    )
    session.add(commitment)
    await session.flush()
    _move(session, commitment, C.PROPOSED, actor, now, {"projection": pace.projection.text()})
    if not await authority.ceo_holds(session, settings, project, "date"):
        item = await items.file(
            session,
            settings,
            project,
            "proposed commitment",
            filer=actor.caller,
            fields={
                "commitment_id": commitment.id,
                "projected": pace.projection.at.strftime("%d %b %Y %H:%M UTC"),
            },
            recommendation="Accept the commitment at the platform's projection.",
            if_declined="The project carries on with no commitment.",
            subject=("commitment", str(commitment.id)),
            now=now,
            announce=False,
        )
        await conversation.platform_line(
            session,
            project.id,
            f"The CEO proposes a commitment at the projection: {pace.projection.text()}. "
            "Accept it, choose a later date, or decline it in the plan.",
            now,
            detail={"kind": "decision item", "item": item.id, "item_kind": item.kind},
        )
    return commitment


async def _scope_now(session: AsyncSession, project_id: str) -> list[int]:
    rows = await session.scalars(
        select(Requirement.id)
        .where(
            Requirement.project_id == project_id,
            Requirement.state.in_([*OPEN_SCOPE, RequirementState.MET]),
        )
        .order_by(Requirement.id)
    )
    return [int(row) for row in rows]


async def accept(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    now: datetime,
    *,
    date: datetime | None = None,
) -> Commitment:
    """PLN-6: whoever holds date authority accepts, at the projection as it is now. The
    chairman may choose a later date. Accepting fixes the settings version and the scope."""
    await authority.require(session, settings, project, actor, "date", "accepting a date")
    commitment = await current(session, project.id)
    if commitment is None or commitment.state != C.PROPOSED:
        raise Refusal("no_proposed_commitment", "No commitment is waiting to be accepted.")
    pace = await projection.pace(session, settings, project, now)
    projected = pace.projection.at
    if projected is None:
        raise Refusal(
            "no_projection",
            f"There is no projection to commit to: {pace.projection.text()}.",
            rule=PLN_6.id,
        )
    if date is not None and (not actor.is_chairman or date < projected):
        raise Refusal(
            "date_before_projection",
            f"A commitment's date is the projection or a later date the chairman chooses. "
            f"You gave {gap_text(date, projected)}.",
            rule=PLN_6.id,
        )
    commitment.date = date or projected
    commitment.projected = projected
    commitment.scope = await _scope_now(session, project.id)
    commitment.settings_version = int(
        await session.scalar(
            select(func.coalesce(func.max(SettingValue.id), 0)).where(
                SettingValue.subject_id == project.id
            )
        )
        or 0
    )
    commitment.settled_at = now
    _move(session, commitment, C.ACCEPTED, actor, now, {"chosen": date is not None})
    await items.settle(
        session, "proposed commitment", ("commitment", str(commitment.id)), "accept",
        actor.caller, now,
    )  # fmt: skip
    await _tell_ceo(
        session,
        project,
        f"The commitment is accepted: {gap_text(commitment.date, projected)}.",
        now,
    )
    return commitment


async def decline(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    reason: str,
    now: datetime,
) -> Commitment:
    """7.6: decline a proposed commitment, with a reason."""
    await authority.require(session, settings, project, actor, "date", "declining a date")
    commitment = await current(session, project.id)
    if commitment is None:
        raise Refusal("no_proposed_commitment", "No commitment is waiting to be answered.")
    if len(reason.strip()) < REASON_MIN_CHARACTERS:
        raise Refusal(
            "reason_too_short",
            f"Give a reason of at least {REASON_MIN_CHARACTERS} characters.",
            rule=PLN_6.id,
        )
    commitment.reason, commitment.settled_at = reason.strip(), now
    _move(session, commitment, C.DECLINED, actor, now, {"reason": reason.strip()})
    await items.settle(
        session, "proposed commitment", ("commitment", str(commitment.id)), "decline",
        actor.caller, now,
    )  # fmt: skip
    await _tell_ceo(session, project, f"The commitment was declined: {reason.strip()}", now)
    return commitment


async def _tell_ceo(session: AsyncSession, project: Project, body: str, now: datetime) -> None:
    ceo = await ceo_of(session, project.id)
    notices.notify(session, project.id, ceo.id, "commitment", body, now, urgent=True)


def state_for(
    *, scope_open: int, scope_met: int, date: datetime, projected: datetime | None, now: datetime
) -> CommitmentState:
    """PLN-7: met when all scope is met; breached when the date passed with scope open; at
    risk when the projection is later than the date; otherwise accepted."""
    if scope_open == 0 and scope_met > 0:
        return C.MET
    if now > date:
        return C.BREACHED
    if projected is not None and projected > date:
        return C.AT_RISK
    return C.ACCEPTED


async def reproject(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> Commitment | None:
    """PLN-7: on every tick, and at once when scope or the date changes, put the live
    commitment in the state the numbers give. Every transition is disclosed to the CEO;
    the chairman gets an alarm on breached and a chat line on at risk and on met."""
    commitment = await current(session, project.id)
    if commitment is None or commitment.state == C.PROPOSED or commitment.date is None:
        return commitment
    pace = await projection.pace(session, settings, project, now)
    counts = dict(
        (
            await session.execute(
                select(Requirement.state, func.count())
                .where(Requirement.project_id == project.id)
                .group_by(Requirement.state)
            )
        ).all()
    )
    target = state_for(
        scope_open=sum(int(counts.get(state, 0)) for state in OPEN_SCOPE),
        scope_met=int(counts.get(RequirementState.MET, 0)),
        date=commitment.date,
        projected=pace.projection.at,
        now=now,
    )
    commitment.projected = pace.projection.at
    if target == commitment.state:
        return commitment
    _move(session, commitment, target, None, now, {"projection": pace.projection.text()})
    where = gap_text(commitment.date, pace.projection.at)
    if target == C.MET:
        commitment.settled_at = now
        text = f"The commitment is met: all scope was met by {where.split(';')[0]}."
    elif target == C.BREACHED:
        text = f"The commitment is breached: the date passed with scope still open ({where})."
        await push.raise_alarm(session, project, text, now)
        await mistakes.open_report(
            session,
            settings,
            project,
            because="the commitment was breached",
            subject=("commitment", str(commitment.id)),
            cost_tokens=await mistakes.tokens_since(
                session, project.id, commitment.settled_at or commitment.proposed_at
            ),
            now=now,
        )
    elif target == C.AT_RISK:
        text = (
            f"The commitment is at risk: {where}. New CEO scope is frozen. Move the date, "
            "cut scope, or let the CEO reset it to the projection."
        )
    else:
        text = f"The commitment is back on track: {where}."
    await _tell_ceo(session, project, text, now)
    await conversation.platform_line(
        session,
        project.id,
        text,
        now,
        detail={"kind": f"commitment {target}", "alarm": target == C.BREACHED},
    )
    return commitment


async def reset(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    now: datetime,
) -> Commitment:
    """PLN-6: the date is reset only to the current projection, only while at risk or
    breached. Each reset shows the running count."""
    await authority.require(session, settings, project, actor, "date", "resetting the date")
    commitment = await current(session, project.id)
    if commitment is None or commitment.state not in (C.AT_RISK, C.BREACHED):
        raise Refusal(
            "commitment_not_at_risk",
            "A commitment is reset only while it is at risk or breached.",
            rule=PLN_6.id,
        )
    pace = await projection.pace(session, settings, project, now)
    if pace.projection.at is None:
        raise Refusal(
            "no_projection", f"There is no projection to reset to: {pace.projection.text()}.",
            rule=PLN_6.id,
        )  # fmt: skip
    before = commitment.date
    date = pace.projection.at
    commitment.date = commitment.projected = date
    commitment.resets += 1
    _move(session, commitment, C.ACCEPTED, actor, now, {"resets": commitment.resets})
    assert before is not None
    await conversation.platform_line(
        session,
        project.id,
        f"The commitment's date was reset to the projection, "
        f"{date.strftime('%d %b %Y %H:%M UTC')} (it was "
        f"{before.strftime('%d %b %Y %H:%M UTC')}). This is reset number {commitment.resets}.",
        now,
        detail={"kind": "commitment reset", "resets": commitment.resets},
    )
    return commitment


async def move_date(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    date: datetime,
    now: datetime,
) -> Commitment:
    """PLN-8, R-58: the chairman moves the date; the commitment is accepted again and is
    re-projected at once."""
    assert actor.is_chairman
    commitment = await current(session, project.id)
    if commitment is None or commitment.state == C.PROPOSED:
        raise Refusal("no_live_commitment", "There is no accepted commitment to move.")
    if date <= now:
        raise Refusal("date_in_the_past", "Move the date to a time in the future.", rule=PLN_6.id)
    commitment.date = date
    _move(session, commitment, C.ACCEPTED, actor, now, {"moved": True})
    await _tell_ceo(
        session,
        project,
        f"The chairman moved the commitment's date: {gap_text(date, commitment.projected)}.",
        now,
    )
    return await reproject(session, settings, project, now) or commitment


async def freeze_check(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """PLN-8: while a commitment is at risk or breached, new CEO proposals are refused
    with the arithmetic. Existing work continues."""
    commitment = await current(session, project.id)
    if commitment is None or commitment.state not in (C.AT_RISK, C.BREACHED):
        return
    assert commitment.date is not None
    raise Refusal(
        "scope_frozen",
        f"The commitment is {commitment.state}: its date is "
        f"{gap_text(commitment.date, commitment.projected)}. New scope is frozen until it "
        "is back on track.",
        rule=PLN_8.id,
        hint="Cut scope, reset the date to the projection, or ask the chairman to move it.",
    )


requirements.proposal_checks.append(freeze_check)
requirements.scope_hooks.append(reproject)


async def target(session: AsyncSession, project_id: str) -> TargetDate | None:
    return await session.scalar(select(TargetDate).where(TargetDate.project_id == project_id))


async def set_target(
    session: AsyncSession,
    project: Project,
    actor: Actor,
    date: datetime | None,
    source: str,
    now: datetime,
) -> TargetDate | None:
    """PLN-9: a chairman target date is stored with its source. It is not a commitment and
    is never shown without the projection beside it."""
    assert actor.is_chairman
    row = await target(session, project.id)
    if row is not None:
        await session.delete(row)
        await session.flush()
    if date is not None:
        row = TargetDate(project_id=project.id, date=date, source=source.strip(), set_at=now)
        session.add(row)
    append_event(
        session,
        type=TARGET_SET,
        caller=actor.caller,
        at=now,
        subject=("project", project.id),
        project_id=project.id,
        after={"date": date.isoformat() if date else None, "source": source.strip()},
    )
    return row if date is not None else None
