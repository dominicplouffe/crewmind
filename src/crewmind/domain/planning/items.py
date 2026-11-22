"""The planning kinds of decision item (HUM-2): proposed scope, proposed commitment,
verdict, reserve draw, capacity and delivery sign-off. Each says what its outcomes do."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from crewmind.catalog.caller import Caller
from crewmind.domain.decisions import items
from crewmind.domain.decisions.items import Kind, Settling
from crewmind.domain.planning import (
    acceptance,
    commitments,
    completion,
    raises,
    readiness,
    requirements,
    reserve,
)
from crewmind.domain.planning.authority import CHAIRMAN, Actor
from crewmind.storage.models import RaiseRequest, ReserveDraw

HOURS_72 = timedelta(hours=72)  # HUM-2
HOURS_24 = timedelta(hours=24)  # HUM-2
NOT_ACCEPTED = "Not accepted by its deadline."


def chairman(caller: Caller) -> Actor:
    """The chairman, or the platform applying the chairman's declared default."""
    return Actor(CHAIRMAN, caller.actor_id, caller)


async def _scope(done: Settling) -> None:
    requirement = await readiness.get(
        done.session, done.project.id, int(done.item.fields["requirement_id"])
    )
    actor = chairman(done.caller)
    if done.outcome in ("accept", "accept anyway"):
        await requirements.accept(
            done.session, done.services.settings, done.project, actor, requirement, done.now,
            anyway=done.outcome == "accept anyway",
        )  # fmt: skip
    elif requirement.state == "proposed":
        await requirements.decline(
            done.session, done.services.settings, done.project, actor, requirement,
            done.note or NOT_ACCEPTED, done.now,
        )  # fmt: skip


SCOPE = items.register(
    Kind(
        name="proposed scope",
        filed_by="ceo",
        actions=("accept", "accept anyway", "decline"),
        default="decline",
        window=HOURS_72,
        title=lambda f: (
            f"Proposed scope: requirement {f['requirement_id']}, {f['estimate_runs']} runs"
        ),
        apply=_scope,
        verb="accept_scope",
        positive=("accept", "accept anyway"),
    )
)


async def _commitment(done: Settling) -> None:
    actor = chairman(done.caller)
    current = await commitments.current(done.session, done.project.id)
    if current is None or current.state != "proposed":
        return
    if done.outcome == "accept":
        await commitments.accept(
            done.session, done.services.settings, done.project, actor, done.now,
            date=done.values.get("date"),
        )  # fmt: skip
    else:
        await commitments.decline(
            done.session, done.services.settings, done.project, actor,
            done.note or NOT_ACCEPTED, done.now,
        )  # fmt: skip


COMMITMENT = items.register(
    Kind(
        name="proposed commitment",
        filed_by="ceo",
        actions=("accept", "decline"),
        default="decline",
        window=HOURS_72,
        title=lambda f: f"Proposed commitment at the projection, {f['projected']}",
        apply=_commitment,
        verb="date",
        positive=("accept",),
    )
)


async def _verdict(done: Settling) -> None:
    requirement = await readiness.get(
        done.session, done.project.id, int(done.item.fields["requirement_id"])
    )
    if requirement.state != "checking":
        return
    if done.outcome == "to a reviewer":
        await acceptance.hand_to_reviewer(done.session, done.project, requirement, done.now)
        return
    await acceptance.rule(
        done.session, done.services.settings, done.project, requirement,
        passed=done.outcome == "pass", note=done.note, by=done.caller,
        holder=acceptance.CHAIRMAN, now=done.now,
    )  # fmt: skip


VERDICT = items.register(
    Kind(
        name="verdict",
        filed_by="platform",
        actions=("pass", "reject"),
        default="to a reviewer",
        window=HOURS_72,
        title=lambda f: f"Verdict wanted on requirement {f['requirement_id']}",
        apply=_verdict,
    )
)


async def _reserve(done: Settling) -> None:
    row = await done.session.get(ReserveDraw, int(done.item.fields["draw_id"]))
    if row is None or row.state != reserve.REQUESTED:
        return
    await reserve.answer(
        done.session, done.services.settings, done.project, chairman(done.caller), row,
        done.outcome == "approve", done.now,
    )  # fmt: skip


RESERVE = items.register(
    Kind(
        name="reserve draw",
        filed_by="ceo",
        actions=("approve", "deny"),
        default="deny",
        window=HOURS_24,
        title=lambda f: f"Reserve draw of {f['tokens']:,} tokens",
        apply=_reserve,
        verb="reserve_draw",
        positive=("approve",),
    )
)


async def _capacity(done: Settling) -> None:
    row = await done.session.get(RaiseRequest, int(done.item.fields["request_id"]))
    if row is None or row.state != raises.PENDING:
        return
    await raises.answer(
        done.session, done.services.settings, done.project, chairman(done.caller), row,
        approve=done.outcome == "approve", amount=done.values.get("amount"), now=done.now,
    )  # fmt: skip


CAPACITY = items.register(
    Kind(
        name="approval: capacity",
        filed_by="ceo",
        actions=("approve", "deny"),
        default="deny",
        window="approval.window",
        title=lambda f: f"Raise the {f['what']} to {f['amount']:,}",
        apply=_capacity,
        extendable=True,
        figures=("amount",),
        positive=("approve",),
    )
)


async def _sign_off(done: Settling) -> None:
    if done.project.state != "ready":
        return
    why = "nobody changed scope after it was ready" if done.by_platform else "signed off"
    await completion.complete(
        done.session, done.services.settings, done.project, done.caller, done.now, why=why
    )


SIGN_OFF = items.register(
    Kind(
        name="delivery sign-off",
        filed_by="platform",
        actions=("sign off",),
        default="sign off",
        window="completion.auto_after",
        title=lambda f: "The project is ready for your sign-off",
        apply=_sign_off,
        positive=("sign off",),
    )
)


def subject(kind: str, key: Any) -> tuple[str, str]:
    return (kind, str(key))
