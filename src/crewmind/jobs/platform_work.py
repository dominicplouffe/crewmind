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

from crewmind.catalog.execute import Clock
from crewmind.catalog.refusal import Refusal
from crewmind.domain.conversation.orders import MAX_CHARACTERS, OrderState, first_sentences
from crewmind.gateway.service import Gateway
from crewmind.storage.models import Message, StandingOrder

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=15)  # section 10: periodic jobs run every 15 s

SHORTEN = "shorten"
SHORTEN_SYSTEM = (
    "You turn a person's message into one standing order for a team of AI agents. Write "
    f"one sentence of at most {MAX_CHARACTERS} characters, in the person's own words where "
    "you can, that says exactly what must always or never be done. Add nothing they did "
    "not say. Answer with the sentence only."
)


class PlatformWorker:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], clock: Clock, gateway: Gateway
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._gateway = gateway

    async def tick(self) -> None:
        await self.shorten_orders()

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
