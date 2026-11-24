"""The one path every call takes, on every surface (IF-1.2, IF-3.2, NFR-10, NFR-11).

Authorize, resolve the project, honour the idempotency key, then run the handler and
write its events in one transaction. Surfaces only authenticate and translate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightsquad.catalog.caller import Authority, Caller, CallerKind
from nightsquad.catalog.operation import PROJECT_FIELD, Operation, Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.secret import one_time_secret_fields
from nightsquad.jobs.nudge import nudge
from nightsquad.storage.events import append_event
from nightsquad.storage.models import Event, IdempotencyKey

Clock = Callable[[], datetime]

ADMIN_ONLY = rules.register(
    Rule("IF-3.2", "Every operation declares who may call it, checked first.")
)
HOST_ONLY = rules.register(Rule("IF-4.2", "Host-local commands run only on the server's own host."))


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectAccess(Protocol):
    """Resolves the project an operation names, or refuses (INV-5, IF-3.3)."""

    async def resolve(
        self, session: AsyncSession, caller: Caller, project_id: str, authority: Authority
    ) -> Any: ...


@dataclass
class Context:
    """What a handler is given. Everything it writes joins one transaction (NFR-10)."""

    caller: Caller
    session: AsyncSession
    now: datetime
    operation: Operation
    sessions: async_sessionmaker[AsyncSession]
    services: Any = None
    project: Any = None
    executor: Any = None
    prepared: Any = None
    events: list[Event] = field(default_factory=list[Event])

    def record(
        self,
        type: str,
        *,
        subject: tuple[str, str],
        project_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Write an event for a state change, naming the caller as actor (INV-21)."""
        self.events.append(
            append_event(
                self.session,
                type=type,
                caller=self.caller,
                at=self.now,
                subject=subject,
                project_id=project_id,
                before=before,
                after=after,
                detail=detail,
            )
        )


def unauthenticated() -> Refusal:
    return Refusal(
        "unauthenticated",
        "Sign in first: this needs a signed-in person.",
        kind=RefusalKind.UNAUTHENTICATED,
        hint="Run `squad login`, or send a valid token.",
    )


def authorize(operation: Operation, caller: Caller) -> None:
    """Check what can be checked without the database (IF-3.2). Project roles are checked
    when the project is resolved."""
    authority = operation.authority
    if authority is Authority.ANYONE:
        return
    if authority is Authority.HOST_OPERATOR:
        if caller.kind is not CallerKind.HOST_OPERATOR:
            raise Refusal(
                "host_only",
                "This runs only on the server's own host.",
                kind=RefusalKind.FORBIDDEN,
                rule=HOST_ONLY.id,
                hint="Run it with the squad command on the server.",
            )
        return
    if authority.is_agent:
        if caller.kind is not CallerKind.AGENT:
            raise unauthenticated()
        if authority is Authority.AGENT_CEO and caller.seat_kind != "ceo":
            raise Refusal(
                "ceo_only",
                "Only the CEO may do this.",
                kind=RefusalKind.FORBIDDEN,
                rule=ADMIN_ONLY.id,
                hint="Suggest it to the CEO instead.",
            )
        return
    if caller.kind is not CallerKind.PERSON:
        raise unauthenticated()
    if authority is Authority.ADMIN and not caller.is_admin:
        raise Refusal(
            "admin_only",
            "This needs an instance admin.",
            kind=RefusalKind.FORBIDDEN,
            rule=ADMIN_ONLY.id,
            hint="Ask an admin to do it.",
        )


class Executor:
    """Carries out operations. Every surface calls `execute` and nothing else (IF-1.2)."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        access: ProjectAccess,
        *,
        services: Any = None,
        clock: Clock = utc_now,
    ) -> None:
        self.sessions = sessions
        self.services = services
        self.clock = clock
        self._access = access

    async def execute(
        self,
        operation: Operation,
        caller: Caller,
        payload: BaseModel,
        *,
        idempotency_key: str | None = None,
    ) -> BaseModel:
        authorize(operation, caller)
        prepared = (
            await operation.prepare(caller, payload, self.services) if operation.prepare else None
        )
        try:
            result = await self._execute(operation, caller, payload, idempotency_key, prepared)
            if operation.reversibility is not Reversibility.READ:
                nudge.ping()
            return result
        except Refusal as refusal:
            if refusal.afterwards is not None:
                async with self.sessions() as session, session.begin():
                    await refusal.afterwards(session)
            raise

    async def _execute(
        self,
        operation: Operation,
        caller: Caller,
        payload: BaseModel,
        idempotency_key: str | None,
        prepared: Any = None,
    ) -> BaseModel:
        async with self.sessions() as session, session.begin():
            context = Context(
                caller=caller,
                session=session,
                now=self.clock(),
                operation=operation,
                sessions=self.sessions,
                services=self.services,
                executor=self,
                prepared=prepared,
            )
            if operation.authority.names_a_project:
                context.project = await self._access.resolve(
                    session, caller, getattr(payload, PROJECT_FIELD), operation.authority
                )
            remember = (
                idempotency_key is not None
                and caller.person_id is not None
                and operation.reversibility is not Reversibility.READ
                and not one_time_secret_fields(operation.output)
            )
            if remember:
                stored = await self._stored_result(session, caller, operation, idempotency_key)
                if stored is not None:
                    return operation.output.model_validate(stored)
            result = await operation.handler(context, payload)
            if remember:
                assert caller.person_id is not None
                assert idempotency_key is not None
                session.add(
                    IdempotencyKey(
                        person_id=caller.person_id,
                        operation=operation.name,
                        key=idempotency_key,
                        result=result.model_dump(mode="json"),
                        at=context.now,
                    )
                )
            return result

    async def call(self, context: Context, operation: Operation, payload: BaseModel) -> BaseModel:
        """Carry out another operation inside the current call and its transaction, as the
        same caller, with that operation's own authority check. This is how a chat slash
        command runs the operation it names (IF-1.2)."""
        authorize(operation, context.caller)
        prepared = (
            await operation.prepare(context.caller, payload, self.services)
            if operation.prepare
            else None
        )
        nested = Context(
            caller=context.caller,
            session=context.session,
            now=context.now,
            operation=operation,
            sessions=context.sessions,
            services=context.services,
            executor=self,
            prepared=prepared,
        )
        if operation.authority.names_a_project:
            nested.project = await self._access.resolve(
                context.session,
                context.caller,
                getattr(payload, PROJECT_FIELD),
                operation.authority,
            )
        return await operation.handler(nested, payload)

    async def _stored_result(
        self, session: AsyncSession, caller: Caller, operation: Operation, key: str | None
    ) -> dict[str, Any] | None:
        row = await session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.person_id == caller.person_id,
                IdempotencyKey.operation == operation.name,
                IdempotencyKey.key == key,
            )
        )
        return None if row is None else row.result
