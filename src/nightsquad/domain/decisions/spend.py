"""Real-world spend (GOV-8, INV-10): the only thing budgeted in money. Off until the
chairman turns it on. The monthly cap counts committed purchases, and nothing overrides it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.decisions import asks, items
from nightsquad.domain.decisions.model import ItemState
from nightsquad.domain.planning import authority
from nightsquad.domain.settings.service import SettingsService
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import DecisionItem, Project, Purchase, Seat

GOV_8 = rules.register(
    Rule("GOV-8", "Real-world spend stays under its monthly cap and its approval threshold.")
)
INV_10 = rules.register(Rule("INV-10", "Committed real-world spend never exceeds the monthly cap."))
PURCHASE_CHANGED = event_type("purchase.changed", "A purchase was declared or settled (GOV-8).")
COMMITTED, BOUGHT, CANCELLED = "committed", "bought", "cancelled"
CENTS = 100
OFFER_AFTER = 3  # GOV-8: after 3 approvals in 90 days with no denial
OFFER_WINDOW = timedelta(days=90)


@dataclass(frozen=True)
class Limits:
    enabled: bool
    currency: str
    cap_cents: int
    approval_at_cents: int
    committed_cents: int
    month_start: datetime


def money(cents: int, currency: str) -> str:
    return f"{cents / CENTS:,.2f} {currency}"


async def limits(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> Limits:
    """The spend settings and what is committed this calendar month, in the project's
    timezone. A cancelled purchase no longer counts."""
    values = await settings.effective(session, authority.subject(project))
    zone = ZoneInfo(str(values["project.timezone"]))
    start = now.astimezone(zone).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    committed = await session.scalar(
        select(func.coalesce(func.sum(Purchase.amount_cents), 0)).where(
            Purchase.project_id == project.id,
            Purchase.state.in_([COMMITTED, BOUGHT]),
            Purchase.declared_at >= start,
        )
    )
    return Limits(
        enabled=bool(values["spend.enabled"]),
        currency=str(values["spend.currency"]),
        cap_cents=round(float(values["spend.monthly_cap"]) * CENTS),
        approval_at_cents=round(float(values["spend.approval_at"]) * CENTS),
        committed_cents=int(committed or 0),
        month_start=start,
    )


async def _covering_approval(
    session: AsyncSession, project: Project, cents: int
) -> DecisionItem | None:
    """An approved spend item that covers this amount and has not been used."""
    used = select(Purchase.approval_item_id).where(
        Purchase.project_id == project.id, Purchase.approval_item_id.is_not(None)
    )
    rows = await session.scalars(
        select(DecisionItem)
        .where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == asks.SPEND,
            DecisionItem.state == ItemState.DECIDED,
            DecisionItem.outcome == "approve",
            DecisionItem.id.not_in(used),
        )
        .order_by(DecisionItem.id)
    )
    for item in rows:
        if round(float(item.fields["amount"]) * CENTS) >= cents:
            return item
    return None


async def declare(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    seat: Seat,
    caller: Caller,
    *,
    what: str,
    amount: float,
    now: datetime,
) -> Purchase:
    """GOV-8, INV-10: an agent declares a purchase before making it. Past the monthly cap
    it is refused and no approval overrides that. At or above the threshold it needs an
    approved spend item covering the amount."""
    found = await limits(session, settings, project, now)
    if not found.enabled:
        raise Refusal(
            "spend_is_off",
            "Real-world spend is off for this project (`spend.enabled`).",
            rule=GOV_8.id,
            hint="Ask the chairman to turn it on.",
        )
    cents = round(amount * CENTS)
    if cents <= 0:
        raise Refusal("amount_not_positive", "A purchase has an amount above zero.", rule=GOV_8.id)
    after = found.committed_cents + cents
    if after > found.cap_cents:
        raise Refusal(
            "over_the_monthly_cap",
            f"This purchase of {money(cents, found.currency)} would bring this month's "
            f"committed spend to {money(after, found.currency)}; `spend.monthly_cap` is "
            f"{money(found.cap_cents, found.currency)}. No approval overrides the cap.",
            rule=INV_10.id,
            hint="Only the chairman can raise the cap.",
        )
    approval: DecisionItem | None = None
    if cents >= found.approval_at_cents:
        approval = await _covering_approval(session, project, cents)
        if approval is None:
            raise Refusal(
                "needs_spend_approval",
                f"A purchase of {money(cents, found.currency)} is at or above "
                f"`spend.approval_at` ({money(found.approval_at_cents, found.currency)}), so "
                "it needs an approved spend item covering the amount.",
                rule=GOV_8.id,
                hint="Ask with agent_request_approval (kind spend), with the figure's basis.",
            )
    row = Purchase(
        project_id=project.id,
        seat_id=seat.id,
        what=what.strip(),
        amount_cents=cents,
        state=COMMITTED,
        approval_item_id=approval.id if approval else None,
        declared_at=now,
    )
    session.add(row)
    await session.flush()
    _record(session, row, caller, now)
    return row


def _record(session: AsyncSession, row: Purchase, caller: Caller, now: datetime) -> None:
    append_event(
        session,
        type=PURCHASE_CHANGED,
        caller=caller,
        at=now,
        subject=("purchase", str(row.id)),
        project_id=row.project_id,
        after={"state": row.state, "amount_cents": row.amount_cents},
    )


async def finish(
    session: AsyncSession,
    project: Project,
    seat: Seat,
    caller: Caller,
    purchase_id: int,
    bought: bool,
    now: datetime,
) -> Purchase:
    """The declaring agent says the purchase was made, or cancels it. A cancelled one no
    longer counts against the cap."""
    row = await session.get(Purchase, purchase_id)
    if row is None or row.project_id != project.id:
        raise Refusal(
            "purchase_not_found", "There is no such purchase.", kind=RefusalKind.NOT_FOUND
        )
    if row.seat_id != seat.id or row.state != COMMITTED:
        raise Refusal(
            "not_your_open_purchase",
            "Only the seat that declared a purchase settles it, once.",
            rule=GOV_8.id,
        )
    row.state, row.settled_at = (BOUGHT if bought else CANCELLED), now
    _record(session, row, caller, now)
    return row


async def offer_higher_threshold(done: items.Settling) -> None:
    """GOV-8: after 3 approvals in 90 days with no denial the system offers to raise the
    threshold. It never raises it on its own."""
    if done.item.kind != asks.SPEND or done.outcome != "approve":
        return
    recent = list(
        await done.session.scalars(
            select(DecisionItem.outcome).where(
                DecisionItem.project_id == done.project.id,
                DecisionItem.kind == asks.SPEND,
                DecisionItem.closed_at.is_not(None),
                DecisionItem.closed_at >= done.now - OFFER_WINDOW,
            )
        )
    )
    approvals = sum(1 for outcome in recent if outcome == "approve")
    if approvals != OFFER_AFTER or any(outcome != "approve" for outcome in recent):
        return
    await conversation.platform_line(
        done.session,
        done.project.id,
        f"You approved {OFFER_AFTER} spend requests in 90 days and denied none. You can "
        "raise `spend.approval_at` in the settings so smaller purchases stop asking. "
        "Nothing changes unless you do.",
        done.now,
        detail={"kind": "spend threshold offer"},
    )


asks.approval_hooks.append(offer_higher_threshold)
