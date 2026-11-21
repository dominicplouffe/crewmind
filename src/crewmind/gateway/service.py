"""The model gateway: every model call passes through here (P3, P9, LLM-1, LLM-9, GOV-6).

A harness calls it with its run token and holds no provider key. The gateway resolves what
the run was pinned to at lease, calls the provider, writes the ledger line and enforces
the per-run cap by refusing the next call past it.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.execute import Clock, unauthenticated
from crewmind.catalog.refusal import Refusal
from crewmind.domain.budget import service as budget
from crewmind.domain.budget.service import GOV_6, Usage
from crewmind.domain.execution import runs
from crewmind.domain.execution.model import CAP_WARNING_SHARE
from crewmind.domain.settings.service import SettingsService
from crewmind.gateway.protocol import CompletionRequest, CompletionResponse
from crewmind.storage.models import LedgerLine, Project, Run, RunStep, Seat

MODEL_CALL = "model call"


class Provider(Protocol):
    name: str

    async def complete(
        self, request: CompletionRequest, *, seat_name: str, run_kind: str, calls_so_far: int
    ) -> CompletionResponse: ...


class Gateway:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: SettingsService,
        clock: Clock,
        providers: dict[str, Any],
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._clock = clock
        self.providers = providers

    async def _wake_tokens(self, session: AsyncSession, run: Run) -> int:
        """Tokens counted so far across every attempt of this run's wake (GOV-6)."""
        attempts = select(Run.id).where(Run.wake_id == run.wake_id)
        return int(
            await session.scalar(
                select(func.coalesce(func.sum(LedgerLine.counted), 0)).where(
                    LedgerLine.run_id.in_(attempts)
                )
            )
            or 0
        )

    async def complete(self, token: str | None, request: CompletionRequest) -> CompletionResponse:
        async with self._sessions() as session:
            run = await runs.run_for_token(session, token)
            if run is None:
                raise unauthenticated()
            seat = await session.get(Seat, run.seat_id)
            assert seat is not None
            used = await self._wake_tokens(session, run)
            if run.max_tokens is not None and used >= run.max_tokens:
                raise Refusal(
                    "run_cap_reached",
                    f"This run has used {used:,} tokens and its cap is {run.max_tokens:,} "
                    "(`run.max_tokens`), counted across retries. No further model calls.",
                    rule=GOV_6.id,
                    hint="End the run. The cap lifts with the next wake.",
                )
            calls = await session.scalar(
                select(func.count())
                .select_from(RunStep)
                .where(RunStep.run_id == run.id, RunStep.kind == MODEL_CALL)
            )
            provider = self.providers[run.provider or "mock"]
            run_id, seat_name, run_kind = run.id, seat.name, run.kind
        response: CompletionResponse = await provider.complete(
            request, seat_name=seat_name, run_kind=run_kind, calls_so_far=calls or 0
        )
        now = self._clock()
        async with self._sessions() as session, session.begin():
            run = await session.get(Run, run_id)
            assert run is not None
            project = await session.get(Project, run.project_id)
            assert project is not None
            usage = Usage(**response.usage.model_dump())
            await budget.record(
                session,
                self._settings,
                project,
                usage,
                now,
                run_id=run.id,
                seat_id=run.seat_id,
                credential_id=run.credential_id,
                provider=run.provider or "mock",
                model=run.model or "mock-1",
            )
            run.reached_model = True
            session.add(
                RunStep(
                    run_id=run.id,
                    kind=MODEL_CALL,
                    data={
                        "text": response.text,
                        "tool_calls": [call.model_dump() for call in response.tool_calls],
                        "usage": response.usage.model_dump(),
                    },
                    at=now,
                )
            )
            total = used + usage.counted
            response.run_tokens_used = total
            response.run_tokens_cap = run.max_tokens
            if run.max_tokens is not None and total >= CAP_WARNING_SHARE * run.max_tokens:
                response.warning = (
                    f"This run has used {total:,} of its {run.max_tokens:,} token cap. Wrap up."
                )
        return response
