"""Work the platform does with its own model calls, outside any agent run (LLM-14, BG-3).

Each task reads what is due in one transaction, calls the model with no transaction open,
and writes the result in another. Every call is metered to its project by the gateway.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightsquad.catalog.execute import Clock
from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.conversation.orders import MAX_CHARACTERS, OrderState, first_sentences
from nightsquad.domain.execution.model import RunKind, RunState
from nightsquad.domain.memory import recall
from nightsquad.domain.memory.engine import MemoryEngine
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from nightsquad.gateway.service import Gateway
from nightsquad.storage.models import Message, Project, Run, Seat, StandingOrder

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=15)  # section 10: periodic jobs run every 15 s

SHORTEN = "shorten"
EXTRACT = "extract"
SHORTEN_SYSTEM = (
    "You turn a person's message into one standing order for a team of AI agents. Write "
    f"one sentence of at most {MAX_CHARACTERS} characters, in the person's own words where "
    "you can, that says exactly what must always or never be done. Add nothing they did "
    "not say. Answer with the sentence only."
)


class PlatformWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        clock: Clock,
        gateway: Gateway,
        settings: SettingsService,
        memory: MemoryEngine,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._gateway = gateway
        self._settings = settings
        self._memory = memory

    async def tick(self) -> None:
        await self.shorten_orders()
        await self.extract_memories()

    async def _due_for_extraction(self) -> list[tuple[str, list[str]]]:
        """MEM-4: every finished work run, and each project's finished chat runs once
        `memory.chat_extract_every` of them have gathered. Returns projects and run ids."""
        async with self._sessions() as session:
            every = int(
                await self._settings.get(
                    session, Subject(Scope.INSTALL, INSTALL_SUBJECT), "memory.chat_extract_every"
                )
            )
            rows = await session.execute(
                select(Run.project_id, Run.id, Run.kind)
                .where(Run.state == RunState.FINISHED, Run.memory_extracted.is_(False))
                .order_by(Run.queued_at)
            )
            work: dict[str, list[str]] = {}
            chat: dict[str, list[str]] = {}
            for project_id, run_id, kind in rows.all():
                (work if kind == RunKind.WORK else chat).setdefault(project_id, []).append(run_id)
        due = [(project_id, [run_id]) for project_id, runs in work.items() for run_id in runs]
        due += [(project_id, runs) for project_id, runs in chat.items() if len(runs) >= every]
        return due

    async def extract_memories(self) -> int:
        """MEM-4, MEM-7, P9: durable facts are extracted from what finished runs said, with
        a fast model call metered to the project. Returns how many facts were stored."""
        stored = 0
        for project_id, run_ids in await self._due_for_extraction():
            async with self._sessions() as session:
                project = await session.get(Project, project_id)
                assert project is not None
                messages: list[dict[str, str]] = []
                untrusted, source = False, ""
                for run_id in run_ids:
                    run = await session.get(Run, run_id)
                    assert run is not None
                    seat = await session.get(Seat, run.seat_id)
                    words = await recall.words_of(session, run)
                    messages += words.messages
                    untrusted = untrusted or words.untrusted
                    source = recall.source_of(run, seat.name if seat else "an agent", self._clock())
            keep = True
            if messages:

                async def model(system: str, prompt: str, project_id: str = project_id) -> str:
                    return await self._gateway.platform_call(project_id, EXTRACT, system, prompt)

                try:
                    ids = await self._memory.extract(
                        recall.project_scope(project_id),
                        messages,
                        recall.metadata(project_id, source, untrusted=untrusted),
                        model,
                    )
                    async with self._sessions() as session:
                        await recall.keep_example_labels(session, self._memory, project, ids)
                    stored += len(ids)
                except Refusal as refusal:
                    # At the budget wall nothing is extracted now and the runs stay due.
                    # With no model to call, there is nothing to wait for.
                    keep = refusal.envelope.code != "at_budget_wall"
                    logger.info("no extraction for %s: %s", project_id, refusal.envelope.code)
                except Exception as error:
                    logger.warning(
                        "extraction failed for %s (%s)", project_id, type(error).__name__
                    )
            if keep:
                async with self._sessions() as session, session.begin():
                    for run_id in run_ids:
                        run = await session.get(Run, run_id)
                        if run is not None:
                            run.memory_extracted = True
        return stored

    async def shorten_orders(self) -> int:
        """MSG-4: a pinned message too long for one order gets a proposed sentence from a
        fast model. The chairman still confirms or edits it. Tried once per order."""
        async with self._sessions() as session:
            rows = await session.execute(
                select(StandingOrder.id, StandingOrder.project_id, Message.body)
                .join(Message, Message.id == StandingOrder.message_id)
                .where(StandingOrder.shorten, StandingOrder.state == OrderState.PROPOSED)
            )
            due = list(rows.all())
        done = 0
        for order_id, project_id, body in due:
            text: str | None = None
            try:
                answer = await self._gateway.platform_call(
                    project_id, SHORTEN, SHORTEN_SYSTEM, body
                )
                text = first_sentences(" ".join(answer.split()))
            except Refusal as refusal:
                logger.info("order %s was not shortened: %s", order_id, refusal.envelope.code)
            except Exception as error:
                logger.warning("order %s was not shortened (%s)", order_id, type(error).__name__)
            async with self._sessions() as session, session.begin():
                row = await session.get(StandingOrder, order_id)
                if row is None or row.state != OrderState.PROPOSED:
                    continue
                row.shorten = False
                if text:
                    row.text = text
                    done += 1
        return done

    async def run(self) -> None:
        """Tick for ever. A failed pass is logged and the next one still runs (NFR-9)."""
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("platform worker: tick failed")
            await asyncio.sleep(TICK.total_seconds())
