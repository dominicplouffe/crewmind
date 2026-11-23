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
from crewmind.domain.execution.context_pack import output_standard
from crewmind.domain.execution.model import CAP_WARNING_SHARE, RunKind
from crewmind.domain.models.service import (
    KIND_KEY,
    KIND_LOGIN,
    LLM_6,
    LLM_8,
    MOCK,
    SECRET_OWNER,
    lineup_of,
    paid_by_login_only,
    platform_credential,
    provider_of,
    record_auth_failure,
    record_success,
    record_transient_failure,
)
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.model import HOLDABLE, Hold
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from crewmind.gateway import outbound
from crewmind.gateway.litellm_provider import is_auth_error, is_transient_error
from crewmind.gateway.mock import MockProvider
from crewmind.gateway.protocol import (
    CompletionRequest,
    CompletionResponse,
    HarnessReport,
    ReportOutcome,
    TokenUsage,
    Turn,
)
from crewmind.gateway.registry import ModelClass, nearest_class, providers
from crewmind.live import StreamHub
from crewmind.storage.models import LedgerLine, ModelCredential, Project, Run, RunStep, Seat

MODEL_CALL = "model call"


GATEWAY_JOB = platform_job("gateway")


FOUNDER = "founder"


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
                if credential.kind == KIND_LOGIN:
                    raise Refusal(
                        "login_credential",
                        f"This run is paid by {credential.name}, the login of a command-line "
                        "agent. The gateway makes no model call with a login.",
                        rule=LLM_8.id,
                        hint="The agent calls its own provider and reports what it used.",
                    )
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
                    run_id=run_id,
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

    async def report(self, token: str | None, told: HarnessReport) -> ReportOutcome:
        """What a command-line agent says about its own model calls (LLM-8, LLM-9, GOV-6).

        Only a run paid by a login may report: every other run is metered here, on what
        the gateway itself saw, and a report from one is refused (P9). The usage is booked
        like any model call, the text is streamed to people watching a chat, a failure
        feeds the circuit breaker, and at the per-run cap the agent is told to stop."""
        now = self._clock()
        async with self._sessions() as session, session.begin():
            run = await runs.run_for_token(session, token)
            if run is None:
                raise unauthenticated()
            credential = (
                await session.get(ModelCredential, run.credential_id) if run.credential_id else None
            )
            if credential is None or credential.kind != KIND_LOGIN:
                raise Refusal(
                    "not_a_login_run",
                    "This run's model calls are metered at the gateway. Only a run on a "
                    "command-line agent's login reports its own usage.",
                    rule=LLM_8.id,
                    hint="Call the gateway for a model; it does the metering.",
                )
            project = await session.get(Project, run.project_id)
            seat = await session.get(Seat, run.seat_id)
            assert project is not None
            assert seat is not None
            run_id, credential_id = run.id, credential.id
            if told.login is not None:
                await self._secrets.put(
                    session,
                    (SECRET_OWNER, credential.id),
                    "key",
                    told.login.get_secret_value(),
                    now,
                )
            if told.usage is not None:
                if record_success(credential):
                    await conversation.platform_line(
                        session,
                        project.id,
                        f"The credential {credential.name} is working again.",
                        now,
                        detail={"kind": "breaker closed"},
                    )
                await budget.record(
                    session,
                    self._settings,
                    project,
                    Usage(**told.usage.model_dump()),
                    now,
                    run_id=run.id,
                    seat_id=run.seat_id,
                    credential_id=credential.id,
                    provider=run.provider or credential.provider,
                    model=run.model or "",
                )
                run.reached_model = True
            if told.usage is not None or told.text:
                session.add(
                    RunStep(
                        run_id=run.id,
                        kind=MODEL_CALL,
                        data={
                            "text": told.text,
                            "tool_calls": [],
                            "usage": (told.usage or TokenUsage()).model_dump(),
                            "reported_by": run.harness,
                        },
                        at=now,
                    )
                )
            if told.text and run.kind == RunKind.CHAT:
                self._hub.publish(
                    project.id,
                    {"type": "reply", "run_id": run.id, "seat": seat.name, "text": told.text},
                )
            await session.flush()
            used = await self._wake_tokens(session, run)
            cap = run.max_tokens
        if told.failure is not None:
            await self._failure(run_id, credential_id, told.failure)
        at_cap = cap is not None and used >= cap
        return ReportOutcome(
            run_tokens_used=used,
            run_tokens_cap=cap,
            stop=at_cap,
            reason=f"This run has used {used:,} tokens and its cap is {cap:,} (`run.max_tokens`)."
            if at_cap
            else "",
        )

    async def platform_call(self, project_id: str, purpose: str, system: str, prompt: str) -> str:
        """A model call the platform itself makes for a project: shortening an order,
        extracting memories (LLM-14, LLM-15, P3, P9).

        It runs on the fast class of the credential that pays the project, is metered to
        the project like any other call, carries the output standard, and is refused at the
        budget wall. No transaction is open while the provider is called."""
        now = self._clock()
        async with self._sessions() as session:
            project = await session.get(Project, project_id)
            assert project is not None
            if (await budget.state(session, self._settings, project, now)).at_wall:
                raise Refusal(
                    "at_budget_wall",
                    "The project is at its budget wall, so the platform makes no model calls.",
                    rule=budget.GOV_3.id,
                    hint="Raise the budget to continue.",
                )
            credential = await platform_credential(session, project, now)
            if credential is None and await paid_by_login_only(session, project.id):
                raise Refusal(
                    "platform_needs_a_key",
                    "This project is paid by the login of a command-line agent. The platform's "
                    "own model calls go through the server, which needs an API key.",
                    rule=LLM_6.id,
                    hint="Add an API-key credential as the project's fallback.",
                )
            provider = providers()[MOCK]
            model, key, base_url = f"mock-{ModelClass.FAST}", None, None
            if credential is not None:
                provider = provider_of(credential)
                lineup = await lineup_of(session, credential)
                actual = nearest_class(ModelClass.FAST, set(lineup))
                if actual is None:
                    raise Refusal(
                        "no_model",
                        f"The credential {credential.name} has no model the platform can use.",
                        rule=LLM_6.id,
                        hint="Refresh the credential's lineup.",
                    )
                model, base_url = lineup[actual], credential.base_url
                key = await self._secrets.reveal(session, (SECRET_OWNER, credential.id), "key")
            credential_id = credential.id if credential else None
        request = CompletionRequest(
            system=f"{system}\n\n# How to write\n\n{output_standard()}",
            messages=[Turn(role="user", content=prompt)],
        )
        if provider.name == MOCK:
            if not self.mock.has_script("platform", purpose):
                raise Refusal(
                    "no_platform_model",
                    "No model credential pays this project, so the platform makes no model "
                    "calls for it.",
                    rule=LLM_6.id,
                    hint="Add a credential and set it as the project's primary.",
                )
            response = await self.mock.complete(
                request, seat_name="platform", run_kind=purpose, calls_so_far=0
            )
        else:
            response = await outbound.call_model(
                provider, request, model=model, api_key=key, base_url=base_url, effort=None
            )
        async with self._sessions() as session, session.begin():
            project = await session.get(Project, project_id)
            assert project is not None
            await budget.record(
                session,
                self._settings,
                project,
                Usage(**response.usage.model_dump()),
                self._clock(),
                run_id=None,
                seat_id=None,
                credential_id=credential_id,
                provider=provider.name,
                model=model,
            )
        return response.text

    async def founder_call(
        self,
        request: CompletionRequest,
        *,
        purpose: str,
        calls_so_far: int = 0,
        on_delta: Callable[[str], None] | None = None,
    ) -> CompletionResponse:
        """A model call the Founder makes: drafting a project, or grading a goal (LLM-14,
        FND-2, P3, P9).

        It runs on the install's drafting credential (`founder.credential`) at
        `founder.model_class`. It is metered like every call, against the install and no
        project, so it counts against no project budget (INV-8)."""
        install = Subject(Scope.INSTALL, INSTALL_SUBJECT)
        async with self._sessions() as session:
            name = str(await self._settings.get(session, install, "founder.credential"))
            wanted = ModelClass(await self._settings.get(session, install, "founder.model_class"))
            credential = await session.scalar(
                select(ModelCredential).where(
                    ModelCredential.name == name, ModelCredential.state == "active"
                )
            )
            provider = providers()[MOCK]
            model, key, base_url = f"mock-{wanted}", None, None
            if credential is not None and credential.kind != KIND_KEY:
                raise Refusal(
                    "founder_needs_a_key",
                    f"The Founder is set to use {credential.name}, which is the login of a "
                    "command-line agent. The Founder calls its model through the server, "
                    "which needs an API key.",
                    rule=LLM_6.id,
                    hint="An admin sets the Founder's model in Settings, under Founder, to a "
                    "credential that is an API key.",
                )
            if credential is not None:
                provider = provider_of(credential)
                lineup = await lineup_of(session, credential)
                actual = nearest_class(wanted, set(lineup))
                if actual is None:
                    raise Refusal(
                        "no_model",
                        f"The credential {credential.name} has no model the Founder can use.",
                        rule=LLM_6.id,
                        hint="Refresh the credential's lineup.",
                    )
                model, base_url = lineup[actual], credential.base_url
                key = await self._secrets.reveal(session, (SECRET_OWNER, credential.id), "key")
            credential_id = credential.id if credential else None
        request = request.model_copy(
            update={"system": f"{request.system}\n\n# How to write\n\n{output_standard()}"}
        )
        if provider.name == MOCK:
            if not self.mock.has_script(FOUNDER, purpose):
                raise Refusal(
                    "no_founder_model",
                    "No model is set for the Founder on this install.",
                    rule=LLM_6.id,
                    hint="An admin sets the Founder's model in Settings, under Founder "
                    "(`founder.credential`).",
                )
            response = await self.mock.complete(
                request,
                seat_name=FOUNDER,
                run_kind=purpose,
                calls_so_far=calls_so_far,
                on_delta=on_delta,
            )
        else:
            response = await outbound.call_model(
                provider,
                request,
                model=model,
                api_key=key,
                base_url=base_url,
                effort=None,
                on_delta=on_delta,
            )
        usage = Usage(**response.usage.model_dump())
        async with self._sessions() as session, session.begin():
            session.add(
                LedgerLine(
                    project_id=None,
                    run_id=None,
                    seat_id=None,
                    credential_id=credential_id,
                    kind="founder",
                    unit="tokens",
                    provider=provider.name,
                    model=model,
                    input_tokens=usage.input,
                    output_tokens=usage.output,
                    cache_write_tokens=usage.cache_write,
                    cache_read_tokens=usage.cache_read,
                    counted=usage.counted,
                    at=self._clock(),
                )
            )
        return response

    async def _failed(self, run_id: str, credential_id: str | None, error: Exception) -> None:
        if is_auth_error(error):
            await self._failure(run_id, credential_id, "auth")
        elif is_transient_error(error):
            await self._failure(run_id, credential_id, "transient")

    async def _failure(self, run_id: str, credential_id: str | None, failure: str) -> None:
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
            if failure == "auth":
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
            elif record_transient_failure(credential, now):
                minutes = credential.breaker_cooloff_seconds // 60
                await conversation.platform_line(
                    session,
                    project.id,
                    f"The provider behind {credential.name} keeps failing. It is rested for "
                    f"{minutes} minutes; seats use the fallback credential if one is set.",
                    now,
                    detail={"kind": "breaker opened"},
                )
