"""Raise requests (GOV-5): only the CEO asks for a higher budget or concurrency, with the
arithmetic and what happens if it is declined. A "yes" never lowers anything."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import service as conversation
from crewmind.domain.decisions import items
from crewmind.domain.execution import notices
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import authority, projection
from crewmind.domain.planning.authority import Actor
from crewmind.domain.settings.service import SettingsService, project_subject
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Project, RaiseRequest

GOV_5 = rules.register(
    Rule("GOV-5", "Only the CEO asks for a raise, with its arithmetic; a yes never lowers.")
)
RAISE_CHANGED = event_type("raise.changed", "A raise request was made or answered (GOV-5).")
PENDING, APPROVED, DECLINED = "pending", "approved", "declined"
SETTING = {"budget": "budget.tokens", "concurrency": "run.concurrency"}
IF_DECLINED_MIN_CHARACTERS = 10  # GOV-5: the request says what happens if it is declined
HALF = 2  # GOV-5: a budget raise is refused while less than half the budget is used


async def request(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    *,
    what: str,
    amount: int,
    if_declined: str,
    now: datetime,
) -> RaiseRequest:
    """GOV-5: the request carries its arithmetic. A budget raise is refused while less
    than half the budget is used and the projected spend fits within it."""
    name = SETTING[what]
    current = int(await settings.get(session, authority.subject(project), name))
    if amount <= current:
        raise Refusal(
            "not_a_raise",
            f"`{name}` is {current:,}; a raise asks for more than that.",
            rule=GOV_5.id,
        )
    if len(if_declined.strip()) < IF_DECLINED_MIN_CHARACTERS:
        raise Refusal(
            "say_what_happens_if_declined",
            "A raise request says what happens if it is declined.",
            rule=GOV_5.id,
        )
    pending = await session.scalar(
        select(RaiseRequest.id).where(
            RaiseRequest.project_id == project.id,
            RaiseRequest.what == what,
            RaiseRequest.state == PENDING,
        )
    )
    if pending is not None:
        raise Refusal(
            "raise_already_asked",
            f"A {what} raise is already waiting for the chairman's answer.",
            rule=GOV_5.id,
        )
    pace = await projection.pace(session, settings, project, now)
    if what == "budget":
        state = await budget.state(session, settings, project, now)
        need = (
            f"projected spend at completion is {pace.projected_spend:,} tokens"
            if pace.projected_spend is not None
            else f"plan tokens are {pace.plan.tokens_text()}"
        )
        arithmetic = f"{budget.arithmetic(state)}; {need}. Asked: {amount:,} tokens."
        fits = pace.projected_spend is None or pace.projected_spend <= state.wall
        if state.spent * HALF < state.wall and fits:
            raise Refusal(
                "raise_not_needed",
                f"Less than half the budget is used and the plan fits within it: {arithmetic}",
                rule=GOV_5.id,
                hint="Ask again when the numbers show the budget will not be enough.",
            )
    else:
        arithmetic = (
            f"`run.concurrency` is {current}; the projection is {pace.projection.text()}. "
            f"Asked: {amount}."
        )
    row = RaiseRequest(
        project_id=project.id,
        what=what,
        amount=amount,
        arithmetic=arithmetic,
        if_declined=if_declined.strip(),
        state=PENDING,
        at=now,
    )
    session.add(row)
    await session.flush()
    _record(session, row, actor, now)
    item = await items.file(
        session,
        settings,
        project,
        "approval: capacity",
        filer=actor.caller,
        fields={"request_id": row.id, "what": what, "amount": amount},
        recommendation=f"Raise the {what} to {amount:,}.",
        if_declined=row.if_declined,
        basis={"kind": "command", "ref": f"The platform's own arithmetic: {arithmetic}"},
        subject=("raise_request", str(row.id)),
        now=now,
        announce=False,
    )
    await conversation.platform_line(
        session,
        project.id,
        f"The CEO asks for a higher {what}: {arithmetic} If declined: {row.if_declined} "
        "Approve it, grant a different number, or decline it.",
        now,
        detail={"kind": "decision item", "item": item.id, "item_kind": item.kind},
    )
    return row


def _record(session: AsyncSession, row: RaiseRequest, actor: Actor, now: datetime) -> None:
    append_event(
        session,
        type=RAISE_CHANGED,
        caller=actor.caller,
        at=now,
        subject=("raise_request", str(row.id)),
        project_id=row.project_id,
        after={"state": row.state, "what": row.what, "amount": row.amount, "granted": row.granted},
        detail={"arithmetic": row.arithmetic},
    )


async def get(session: AsyncSession, project_id: str, request_id: int) -> RaiseRequest:
    row = await session.get(RaiseRequest, request_id)
    if row is None or row.project_id != project_id:
        raise Refusal("raise_not_found", "There is no such request.", kind=RefusalKind.NOT_FOUND)
    return row


async def answer(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    row: RaiseRequest,
    *,
    approve: bool,
    amount: int | None,
    now: datetime,
) -> None:
    """GOV-5: approving applies the change. The chairman may grant a different number,
    but a "yes" never lowers anything."""
    assert actor.is_chairman
    if row.state != PENDING:
        raise Refusal("raise_answered", f"This request is already {row.state}.")
    ceo = await ceo_of(session, project.id)
    row.answered_at = now
    if not approve:
        row.state = DECLINED
        _record(session, row, actor, now)
        await items.settle(
            session, "approval: capacity", ("raise_request", str(row.id)), "deny",
            actor.caller, now,
        )  # fmt: skip
        notices.notify(
            session, project.id, ceo.id, "raise declined",
            f"The chairman declined the {row.what} raise. You said that then: {row.if_declined}",
            now, urgent=True,
        )  # fmt: skip
        return
    name = SETTING[row.what]
    current = int(await settings.get(session, authority.subject(project), name))
    granted = amount if amount is not None else row.amount
    if granted <= current:
        raise Refusal(
            "a_yes_never_lowers",
            f"`{name}` is {current:,}. Approving a raise grants more than that; to grant "
            "nothing, decline it.",
            rule=GOV_5.id,
        )
    await settings.change(
        session,
        await project_subject(session, project),
        {name: granted},
        reason=f"Raise request {row.id} approved: {row.arithmetic}",
        caller=actor.caller,
        now=now,
    )
    row.state, row.granted = APPROVED, granted
    _record(session, row, actor, now)
    await items.settle(
        session, "approval: capacity", ("raise_request", str(row.id)), "approve",
        actor.caller, now,
    )  # fmt: skip
    notices.notify(
        session, project.id, ceo.id, "raise approved",
        f"The chairman approved the {row.what} raise: `{name}` is now {granted:,}.",
        now, urgent=True,
    )  # fmt: skip
    if row.what == "budget":
        await session.flush()
        await budget.follow_wall(session, settings, project, now)
