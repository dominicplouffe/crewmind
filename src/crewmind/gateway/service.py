"""The model gateway: every model call passes through here (P3, P9, LLM-1, LLM-9, GOV-6).

A harness calls it with its run token and holds no provider key. The gateway resolves what
the run was pinned to at lease, calls the provider, writes the ledger line and enforces
the per-run cap by refusing the next call past it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.caller import platform_job
from crewmind.catalog.execute import Clock, unauthenticated
from crewmind.catalog.refusal import Refusal
from crewmind.domain.budget import service as budget
from crewmind.domain.budget.service import GOV_6, Usage
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import runs
from crewmind.domain.execution.model import CAP_WARNING_SHARE, RunKind
from crewmind.domain.models.service import (
    MOCK,
    SECRET_OWNER,
    record_auth_failure,
    record_success,
    record_transient_failure,
)
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.model import HOLDABLE, Hold
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.service import SettingsService
from crewmind.gateway import outbound
from crewmind.gateway.litellm_provider import is_auth_error, is_transient_error
from crewmind.gateway.mock import MockProvider
from crewmind.gateway.protocol import CompletionRequest, CompletionResponse
from crewmind.gateway.registry import providers
from crewmind.live import StreamHub
from crewmind.storage.models import LedgerLine, ModelCredential, Project, Run, RunStep, Seat

MODEL_CALL = "model call"


GATEWAY_JOB = platform_job("gateway")


class Gateway:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: SettingsService,
        clock: Clock,
        mock: MockProvider,
        key_file: Path,
        hub: StreamHub | None = None,
    ) -> None:
        self._hub = hub or StreamHub()
        self._sessions = sessions
        self._settings = settings
        self._clock = clock
        self.mock = mock
        self._secrets = SecretStore(key_file)

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
            run_id, seat_name, run_kind = run.id, seat.name, run.kind
            project_id = run.project_id
            model, effort, credential_id = run.model or "", run.effort, run.credential_id
            key: str | None = None
            base_url: str | None = None
            provider = providers()[run.provider or MOCK]
            if credential_id is not None:
                credential = await session.get(ModelCredential, credential_id)
                assert credential is not None
                base_url = credential.base_url
                key = await self._secrets.reveal(session, (SECRET_OWNER, credential.id), "key")
        on_delta: Callable[[str], None] | None = None
        if run_kind == RunKind.CHAT:
            # A chat reply is streamed to the people watching, word by word (IF-3.6, CHAT-3).
            def publish(text: str) -> None:
                self._hub.publish(
                    project_id, {"type": "reply", "run_id": run_id, "seat": seat_name, "text": text}
                )

            on_delta = publish
        try:
            if provider.name == MOCK:
                response = await self.mock.complete(
                    request,
                    seat_name=seat_name,
                    run_kind=run_kind,
                    calls_so_far=calls or 0,
                    on_delta=on_delta,
                )
            else:
                response = await outbound.call_model(
                    provider,
                    request,
                    model=model,
                    api_key=key,
                    base_url=base_url,
                    effort=effort,
                    on_delta=on_delta,
                )
        except Exception as error:
            await self._failed(run_id, credential_id, error)
            raise
        now = self._clock()
        async with self._sessions() as session, session.begin():
            run = await session.get(Run, run_id)
            assert run is not None
            project = await session.get(Project, run.project_id)
            assert project is not None
            if credential_id is not None:
                credential = await session.get(ModelCredential, credential_id)
                assert credential is not None
                if record_success(credential):
                    await conversation.platform_line(
                        session,
                        project.id,
                        f"The credential {credential.name} is working again.",
                        now,
                        detail={"kind": "breaker closed"},
                    )
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
                provider=provider.name,
                model=model or "mock",
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

    async def _failed(self, run_id: str, credential_id: str | None, error: Exception) -> None:
        """Account for a provider failure: transient ones feed the circuit breaker, and
        authentication failures count toward pausing the project (LLM-11, PRJ-2)."""
        if credential_id is None:
            return
        now = self._clock()
        async with self._sessions() as session, session.begin():
            credential = await session.get(ModelCredential, credential_id)
            run = await session.get(Run, run_id)
            assert credential is not None
            assert run is not None
            project = await session.get(Project, run.project_id)
            assert project is not None
            if is_auth_error(error):
                if record_auth_failure(credential) and project.state in HOLDABLE:
                    await lifecycle.add_hold(
                        session,
                        project,
                        Hold.AUTH_FAILURES,
                        caller=GATEWAY_JOB,
                        now=now,
                        note=f"{credential.name} failed to authenticate 3 times in a row.",
                    )
                    await conversation.platform_line(
                        session,
                        project.id,
                        f"The project is paused: the credential {credential.name} failed to "
                        "authenticate 3 times in a row. Fix the key, then resume.",
                        now,
                        detail={"kind": "credential dead", "alarm": True},
                    )
            elif is_transient_error(error) and record_transient_failure(credential, now):
                minutes = credential.breaker_cooloff_seconds // 60
                await conversation.platform_line(
                    session,
                    project.id,
                    f"The provider behind {credential.name} keeps failing. It is rested for "
                    f"{minutes} minutes; seats use the fallback credential if one is set.",
                    now,
                    detail={"kind": "breaker opened"},
                )
