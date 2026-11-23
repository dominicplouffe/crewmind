"""An interview's state and its rules: the ledger, the questions, readiness (FND-3 to
FND-5, FND-11, FND-15). Nothing here calls a model."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from importlib import resources
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.founder import model as m
from crewmind.domain.founder import tree
from crewmind.domain.founder.model import D
from crewmind.storage.models import (
    Drafting,
    DraftingMessage,
    DraftingQuestion,
    GrillItem,
    LedgerEntry,
    ModelCredential,
)

DOCTRINE_FILES = ("design-doctrine.md", "goal-grammar.md")
ITEM = "item:"
YES = frozenset({"", "y", "yes", "ok", "okay"})


def doctrine_text() -> str:
    """The one copy of the doctrine and the goal grammar (FND, LIB-6)."""
    root = resources.files("crewmind.content").joinpath("doctrine")
    return "\n\n".join(root.joinpath(name).read_text(encoding="utf-8") for name in DOCTRINE_FILES)


def doctrine_fingerprint() -> str:
    """FND-14: what a project records of the doctrine it was drafted under."""
    return hashlib.sha256(doctrine_text().encode()).hexdigest()


def fingerprint(draft: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(draft, sort_keys=True, default=str).encode()).hexdigest()


async def get(session: AsyncSession, drafting_id: str, person_id: str) -> Drafting:
    """A person's own interview. Another person's is not found (INV-5)."""
    row = await session.get(Drafting, drafting_id)
    if row is None or row.person_id != person_id:
        raise Refusal(
            "drafting_not_found",
            "There is no such drafting conversation.",
            kind=RefusalKind.NOT_FOUND,
            hint="List yours with `crewmind founder list`.",
        )
    return row


def say(
    session: AsyncSession,
    drafting: Drafting,
    author: str,
    body: str,
    now: datetime,
    detail: dict[str, Any] | None = None,
) -> DraftingMessage:
    line = DraftingMessage(drafting_id=drafting.id, author=author, body=body, detail=detail, at=now)
    session.add(line)
    drafting.updated_at = now
    return line


async def credentials_of(session: AsyncSession, person_id: str) -> list[str]:
    rows = await session.scalars(
        select(ModelCredential.name)
        .where(
            ModelCredential.owner_id == person_id,
            ModelCredential.state == "active",
            ModelCredential.kind.in_(("model", "subscription")),
        )
        .order_by(ModelCredential.name)
    )
    return list(rows)


async def ledger(session: AsyncSession, drafting_id: str) -> list[LedgerEntry]:
    rows = await session.scalars(
        select(LedgerEntry).where(LedgerEntry.drafting_id == drafting_id).order_by(LedgerEntry.id)
    )
    return list(rows)


async def settled(session: AsyncSession, drafting_id: str) -> set[str]:
    return {entry.settles for entry in await ledger(session, drafting_id)}


async def settle(
    session: AsyncSession,
    drafting: Drafting,
    settles: str,
    value: str,
    source: str,
    now: datetime,
    passage: str | None = None,
) -> LedgerEntry:
    """Write one decision into the ledger. The chairman's own words and answers outrank
    an assumption, which never replaces them (FND-5)."""
    entry = await session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.drafting_id == drafting.id, LedgerEntry.settles == settles
        )
    )
    if entry is None:
        entry = LedgerEntry(drafting_id=drafting.id, settles=settles, at=now)
        session.add(entry)
    elif source == m.ASSUMPTION and entry.source != m.ASSUMPTION:
        return entry
    entry.value, entry.source, entry.passage, entry.at = value, source, passage, now
    await session.flush()
    return entry


async def open_question(session: AsyncSession, drafting_id: str) -> list[DraftingQuestion]:
    rows = await session.scalars(
        select(DraftingQuestion)
        .where(DraftingQuestion.drafting_id == drafting_id, DraftingQuestion.state == m.OPEN)
        .order_by(DraftingQuestion.id)
    )
    return list(rows)


async def open_items(session: AsyncSession, drafting_id: str) -> list[GrillItem]:
    rows = await session.scalars(
        select(GrillItem)
        .where(GrillItem.drafting_id == drafting_id, GrillItem.state == m.ITEM_OPEN)
        .order_by(GrillItem.id)
    )
    return list(rows)


async def items_extracted(session: AsyncSession, drafting_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(GrillItem).where(GrillItem.drafting_id == drafting_id)
        )
        or 0
    )


def said_by_the_chairman(lines: list[DraftingMessage], drafting: Drafting) -> str:
    """Everything the chairman has written, and the document, as one text to quote from."""
    words = [line.body for line in lines if line.author == m.PERSON]
    return " ".join(" ".join([*words, drafting.document or ""]).split()).lower()


async def lines(session: AsyncSession, drafting_id: str) -> list[DraftingMessage]:
    rows = await session.scalars(
        select(DraftingMessage)
        .where(DraftingMessage.drafting_id == drafting_id)
        .order_by(DraftingMessage.id)
    )
    return list(rows)


def answer_of(question: DraftingQuestion, answer: str) -> tuple[str, int | None]:
    """What the chairman chose: Enter or "yes" takes the recommendation, a letter picks
    an option, and anything else is their own words (FND-3, IF-4.6)."""
    text = answer.strip()
    options = [str(option) for option in question.options]
    if text.lower() in YES:
        if question.recommended is None:
            raise Refusal(
                "nothing_recommended",
                "This question has no recommended answer, so it needs your choice.",
                rule=m.FND_3.id,
                hint="Answer with a letter, or in your own words.",
            )
        return options[question.recommended], question.recommended
    if len(text) == 1 and text.isalpha() and ord(text.lower()) - ord("a") < len(options):
        index = ord(text.lower()) - ord("a")
        return options[index], index
    for index, option in enumerate(options):
        if option.strip().lower() == text.lower():
            return option, index
    return text, None


async def answer(
    session: AsyncSession, drafting: Drafting, question_id: int, text: str, now: datetime
) -> DraftingQuestion:
    question = await session.get(DraftingQuestion, question_id)
    if question is None or question.drafting_id != drafting.id or question.state != m.OPEN:
        raise Refusal(
            "question_not_open",
            f"Question {question_id} is not waiting for an answer.",
            kind=RefusalKind.NOT_FOUND,
            rule=m.FND_3.id,
        )
    value, chosen = answer_of(question, text)
    question.state, question.answer, question.answered_at = m.ANSWERED, value, now
    await _resolve(session, drafting, question, value, chosen, m.ANSWER, now)
    say(session, drafting, m.PERSON, value, now, {"kind": "answer", "question": question.id})
    drafting.turn = m.DUE
    return question


async def _resolve(
    session: AsyncSession,
    drafting: Drafting,
    question: DraftingQuestion,
    value: str,
    chosen: int | None,
    source: str,
    now: datetime,
) -> None:
    passage = None
    if question.settles.startswith(ITEM):
        item = await session.get(GrillItem, int(question.settles.removeprefix(ITEM)))
        assert item is not None
        item.state, passage = m.ITEM_RESOLVED, item.passage
        if item.problem == "example_or_real" and chosen is not None:
            item.is_example = "example" in str(question.options[chosen]).lower()
    await settle(session, drafting, question.settles, value, source, now, passage)


async def accept_the_rest(session: AsyncSession, drafting: Drafting, now: datetime) -> int:
    """FND-15: "use your recommendations for the rest". Every open question takes its
    recommendation, and every decision still unasked takes the draft's value, each
    recorded as an assumption. Returns how many were recorded."""
    recorded = 0
    for question in await open_question(session, drafting.id):
        if question.recommended is None:
            continue
        value = str(question.options[question.recommended])
        question.state, question.answer, question.answered_at = m.ANSWERED, value, now
        await _resolve(session, drafting, question, value, question.recommended, m.ASSUMPTION, now)
        recorded += 1
    for item in await open_items(session, drafting.id):
        item.state = m.ITEM_RESOLVED
        await settle(
            session,
            drafting,
            f"{ITEM}{item.id}",
            item.note or "Taken as the Founder recommends.",
            m.ASSUMPTION,
            now,
            item.passage,
        )
        recorded += 1
    recommended: dict[str, Any] = (drafting.draft or {}).get("decisions", {})
    done = await settled(session, drafting.id)
    for decision in tree.unsettled(done):
        value = recommended.get(decision.key)
        if value:
            await settle(session, drafting, decision.key, str(value), m.ASSUMPTION, now)
            recorded += 1
    drafting.rest_accepted = True
    drafting.turn = m.DUE
    return recorded


async def not_ready_because(session: AsyncSession, drafting: Drafting) -> list[str]:
    """What still stands between this draft and a project (FND-5, FND-6, FND-11, FND-15).
    Empty when the chairman may confirm the ledger."""
    missing: list[str] = []
    if await open_items(session, drafting.id):
        missing.append("Passages of the document are still unresolved.")
    waiting = await open_question(session, drafting.id)
    if waiting:
        missing.append(f"{len(waiting)} question(s) are waiting for an answer.")
    if drafting.draft is None:
        missing.append("There is no draft yet.")
        return missing
    unsettled = tree.unsettled(await settled(session, drafting.id))
    if unsettled:
        missing.append("Not yet decided: " + "; ".join(d.what for d in unsettled) + ".")
    grade: dict[str, Any] = drafting.grade or {}
    if not grade.get("ready"):
        missing.append(str(grade.get("summary") or "The goal has not been graded."))
    if drafting.rehearsed_draft != fingerprint(drafting.draft):
        missing.append("This draft has not been rehearsed.")
    elif not (drafting.rehearsal or {}).get("ok"):
        missing.append(
            "The rehearsal did not reach a first close: "
            + str((drafting.rehearsal or {}).get("verdict", ""))
        )
    return missing


def new(person_id: str, kind: str, now: datetime, *, quick: bool = False) -> Drafting:
    m.DRAFTING_MACHINE.check(m.NEW, D.DRAFTING)
    return Drafting(
        kind=kind,
        person_id=person_id,
        project_id=None,
        state=D.DRAFTING,
        quick=quick,
        doctrine=doctrine_fingerprint(),
        turn=m.DUE,
        created_at=now,
        updated_at=now,
    )
