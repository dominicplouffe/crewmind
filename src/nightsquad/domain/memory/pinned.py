"""Pinned memory: the exact records that are in every run of every agent they concern
(MEM-1, INV-25, P16).

Nothing here is summarised or searched. Each record is placed in the context pack word
for word, so an order, a decision or a correction said once is never missed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.execution.model import SeatKind
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject
from nightsquad.storage.models import (
    ClosedDecision,
    Correction,
    DecisionItem,
    PinnedNote,
    Project,
    Seat,
    StandingOrder,
)

CHARACTERS_PER_TOKEN = 4  # MEM-1: sizes are estimated at 4 characters per token

ORDER_ACTIVE, ORDER_RETIRED = "active", "retired"
DECISION_CLOSED = "closed"
CORRECTION_ACTIVE = "active"

OVER_SIZE = "pinned memory over size"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARACTERS_PER_TOKEN)


@dataclass(frozen=True)
class Pinned:
    """What is pinned for one agent, already in the words the context pack uses."""

    goal: str
    orders: list[StandingOrder]
    retired: list[StandingOrder]
    decisions: list[ClosedDecision]
    corrections: list[tuple[Correction, str]]
    notes: list[PinnedNote]
    lessons: list[tuple[int, str]] = field(default_factory=list[tuple[int, str]])

    @property
    def project_tokens(self) -> int:
        """The size of the project-wide records, against `memory.pinned_project_tokens`."""
        texts = [self.goal, *(o.text for o in self.orders)]
        texts += [f"{d.topic}: {d.ruling}" for d in self.decisions]
        return sum(estimate_tokens(text) for text in texts)

    @property
    def agent_tokens(self) -> int:
        """The size of this agent's own records, against `memory.pinned_agent_tokens`."""
        texts = [f"{c.question} {c.words}" for c, _ in self.corrections]
        texts += [n.text for n in self.notes]
        return sum(estimate_tokens(text) for text in texts)

    def render(self) -> str:
        """The pinned section of a context pack. Every record appears word for word."""
        parts = [
            "# Pinned memory\n\nThese records are exact. Follow them in every answer and "
            "every action.",
            f"## Goal\n\n{self.goal}",
        ]
        if self.orders:
            parts.append(
                "## Standing orders (the chairman's; follow every one)\n\n"
                + "\n".join(f"- [order {o.id}] {o.text}" for o in self.orders)
            )
        if self.retired:
            parts.append(
                "## Retired orders (no longer in force; do not follow them)\n\n"
                + "\n".join(f"- [order {o.id}, retired] {o.text}" for o in self.retired)
            )
        if self.decisions:
            parts.append(
                "## Closed decisions (settled; raise one again only with a reopen request "
                "that links newer evidence)\n\n"
                + "\n".join(f"- [decision {d.id}] {d.topic}: {d.ruling}" for d in self.decisions)
            )
        if self.lessons:
            parts.append(
                "## Lessons (from mistakes this project made; do not repeat them)\n\n"
                + "\n".join(f"- [lesson {number}] {text}" for number, text in self.lessons)
            )
        if self.corrections:
            parts.append(
                "## Corrections (the chairman said a reply was not what they asked; do not "
                "repeat the mistake)\n\n"
                + "\n".join(
                    f"- [correction {c.id}, about {who}] The question was: {c.question}\n"
                    f"  The chairman said: {c.words}"
                    for c, who in self.corrections
                )
            )
        if self.notes:
            parts.append(
                "## Your pinned notes\n\n"
                + "\n".join(f"- [note {n.id}] {n.text}" for n in self.notes)
            )
        return "\n\n".join(parts)


async def pinned_for(session: AsyncSession, project: Project, seat: Seat) -> Pinned:
    """MEM-1, INV-25: the goal, every active order and closed decision, the live corrections
    that concern this agent (the CEO sees every agent's), and the agent's own notes."""
    orders = list(
        await session.scalars(
            select(StandingOrder)
            .where(
                StandingOrder.project_id == project.id,
                StandingOrder.state.in_([ORDER_ACTIVE, ORDER_RETIRED]),
            )
            .order_by(StandingOrder.id)
        )
    )
    decisions = list(
        await session.scalars(
            select(ClosedDecision)
            .where(ClosedDecision.project_id == project.id, ClosedDecision.state == DECISION_CLOSED)
            .order_by(ClosedDecision.id)
        )
    )
    wanted = (
        select(Correction, Seat)
        .join(Seat, Seat.id == Correction.seat_id)
        .where(Correction.project_id == project.id, Correction.state == CORRECTION_ACTIVE)
    )
    if seat.kind != SeatKind.CEO:
        wanted = wanted.where(Correction.seat_id == seat.id)
    corrections = [
        (row, "you" if about.id == seat.id else about.name)
        for row, about in (await session.execute(wanted.order_by(Correction.id))).all()
    ]
    notes = list(
        await session.scalars(
            select(PinnedNote).where(PinnedNote.seat_id == seat.id).order_by(PinnedNote.id)
        )
    )
    lessons = await session.scalars(
        select(DecisionItem)
        .where(
            DecisionItem.project_id == project.id,
            DecisionItem.kind == "mistake report",
            DecisionItem.state == "filed",
        )
        .order_by(DecisionItem.id)
    )
    return Pinned(
        lessons=[(row.id, str(row.fields.get("prevention", ""))) for row in lessons],
        goal=project.goal,
        orders=[o for o in orders if o.state == ORDER_ACTIVE],
        retired=[o for o in orders if o.state == ORDER_RETIRED],
        decisions=decisions,
        corrections=corrections,
        notes=notes,
    )


async def caps(
    session: AsyncSession, settings: SettingsService, project: Project
) -> tuple[int, int]:
    """The project-wide cap and the per-agent cap, in tokens (MEM-1)."""
    subject = Subject(Scope.PROJECT, project.id, project.type)
    return (
        int(await settings.get(session, subject, "memory.pinned_project_tokens")),
        int(await settings.get(session, subject, "memory.pinned_agent_tokens")),
    )


async def note_if_over(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    seat: Seat,
    now: datetime,
) -> str | None:
    """MEM-1: a chairman's write is never refused by a size cap. When pinned memory is over
    its size, the chat says so once and names what to retire. Returns the note, if any."""
    pinned = await pinned_for(session, project, seat)
    project_cap, agent_cap = await caps(session, settings, project)
    over: list[str] = []
    if pinned.project_tokens > project_cap:
        over.append(
            f"The project's pinned memory is about {pinned.project_tokens:,} tokens; "
            f"`memory.pinned_project_tokens` is {project_cap:,}. Retire a standing order or "
            "reopen a decision you no longer need, or raise the setting."
        )
    if pinned.agent_tokens > agent_cap:
        over.append(
            f"{seat.name}'s pinned memory is about {pinned.agent_tokens:,} tokens; "
            f"`memory.pinned_agent_tokens` is {agent_cap:,}. Remove a correction you no "
            "longer need, or raise the setting."
        )
    if not over:
        return None
    note = "Pinned memory is over its size. Everything is still sent to every run. " + " ".join(
        over
    )
    await conversation.platform_line(session, project.id, note, now, detail={"kind": OVER_SIZE})
    return note
