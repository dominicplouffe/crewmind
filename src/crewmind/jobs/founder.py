"""The Founder's worker: it takes the turns the Founder owes, and carries quick mode
through to a started project (FND-1, FND-12, BG-3)."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog import catalog
from crewmind.catalog.execute import Clock, Executor
from crewmind.catalog.refusal import Refusal
from crewmind.domain.founder import drafting as state
from crewmind.domain.founder import model as m
from crewmind.domain.founder.model import DRAFTING_MACHINE, D
from crewmind.domain.founder.turn import FounderTurn, caller_of
from crewmind.gateway.protocol import ToolCall
from crewmind.gateway.service import Gateway
from crewmind.jobs.nudge import nudge, pause
from crewmind.live import StreamHub
from crewmind.services import Services
from crewmind.storage.models import Drafting, Person

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=15)  # section 10: periodic jobs run every 15 s
REHEARSE = "rehearse_spec"


class FounderWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        clock: Clock,
        gateway: Gateway,
        services: Services,
        executor: Executor,
        hub: StreamHub | None = None,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._executor = executor
        self._hub = hub
        self._turn = FounderTurn(sessions, clock, gateway, services, executor)

    async def tick(self) -> int:
        """Take every owed turn. Returns how many were taken."""
        async with self._sessions() as session:
            due = list(
                await session.scalars(
                    select(Drafting.id)
                    .where(
                        Drafting.kind == m.FOUNDER,
                        Drafting.state == D.DRAFTING,
                        Drafting.turn == m.DUE,
                    )
                    .order_by(Drafting.updated_at)
                )
            )
        for drafting_id in due:
            await self._turn.take(drafting_id, self._publisher(drafting_id))
            await self._finish_quick(drafting_id)
        return len(due)

    def _publisher(self, drafting_id: str):
        """FND-1: each turn streams, word by word, to whoever is watching."""
        if self._hub is None:
            return None
        hub = self._hub

        def publish(text: str) -> None:
            hub.publish(f"drafting:{drafting_id}", {"text": text})

        return publish

    async def _finish_quick(self, drafting_id: str) -> None:
        """FND-12: once a quick draft exists, rehearse it, then create and start the
        project in one transaction. Any failure leaves nothing created."""
        async with self._sessions() as session:
            drafting = await session.get(Drafting, drafting_id)
            assert drafting is not None
            if not drafting.quick or drafting.state != D.DRAFTING or drafting.turn != m.IDLE:
                return
            person = await session.get(Person, drafting.person_id)
            assert person is not None
            has_draft = drafting.draft is not None
        reason: str | None = None
        if not has_draft:
            reason = "The Founder did not produce a draft."
        else:
            rehearsed = await self._turn.run_tool(
                drafting_id, ToolCall(id="quick", name=REHEARSE, arguments={})
            )
            if "refused" in rehearsed:
                reason = str(rehearsed["refused"]["message"])
            else:
                create = catalog.get("founder.create")
                try:
                    await self._executor.execute(
                        create, caller_of(person), create.input(drafting_id=drafting_id)
                    )
                except Refusal as refusal:
                    reason = refusal.envelope.message
        if reason is None:
            return
        async with self._sessions() as session, session.begin():
            drafting = await session.get(Drafting, drafting_id)
            assert drafting is not None
            DRAFTING_MACHINE.check(D.DRAFTING, D.CREATING)
            DRAFTING_MACHINE.check(D.CREATING, D.FAILED)
            drafting.state, drafting.failure = D.FAILED, reason
            state.say(
                session,
                drafting,
                m.PLATFORM,
                f"Quick mode failed and nothing was created: {reason}",
                self._clock(),
                {"kind": "failure"},
            )

    async def run(self) -> None:
        waiter = nudge.waiter()
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("founder: a pass failed")
            await pause(waiter, TICK)
