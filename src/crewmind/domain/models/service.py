"""Model credentials, lineups, the quality dial, the seat check and who pays
(LLM-2 to LLM-7, LLM-11, LLM-12, section 7.18).

One resolver decides which credential pays a seat and what it runs on. Every lane uses
it, so chat and work runs never see different credentials (LLM-7).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.catalog.state_machine import NEW, StateMachine
from crewmind.domain.execution.model import LIVE_STATES, SeatKind
from crewmind.domain.execution.runs import Pinned, Wait
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import SettingsService, Subject
from crewmind.gateway.registry import (
    Effort,
    ModelClass,
    ProviderInfo,
    nearest_class,
    pick_lineup,
    providers,
)
from crewmind.storage.models import (
    Lineup,
    ModelCredential,
    Project,
    ProjectCredential,
    ProviderCeiling,
    Role,
    Run,
    Seat,
)

LLM_6 = rules.register(
    Rule("LLM-6", "A seat runs only if a credential pays it and it can do its job.")
)
LLM_2 = rules.register(Rule("LLM-2", "Model credentials are named, encrypted and never shown."))

SECRET_OWNER = "model_credential"
MOCK = "mock"
SEARCH_PROVIDERS = ("brave",)

# LLM-11, fixed rules.
BREAKER_FAILURES = 3
BREAKER_FIRST_COOLOFF = timedelta(minutes=5)
BREAKER_MAX_COOLOFF = timedelta(hours=1)
AUTH_FAILURES_BEFORE_PAUSE = 3


class CredentialState(StrEnum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    DELETED = "deleted"


class Breaker(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class Use(StrEnum):
    PRIMARY = "primary"
    FALLBACK = "fallback"
    SEAT = "seat"


CREDENTIAL_MACHINE = StateMachine(
    "model credential",
    "7.18-credential",
    [
        (NEW, CredentialState.ACTIVE),
        (CredentialState.ACTIVE, CredentialState.HIDDEN),
        (CredentialState.HIDDEN, CredentialState.ACTIVE),
        (CredentialState.ACTIVE, CredentialState.DELETED),
        (CredentialState.HIDDEN, CredentialState.DELETED),
    ],
)

BREAKER_MACHINE = StateMachine(
    "circuit breaker",
    "7.18-breaker",
    [
        (Breaker.CLOSED, Breaker.OPEN),
        (Breaker.OPEN, Breaker.HALF_OPEN),
        (Breaker.HALF_OPEN, Breaker.CLOSED),
        (Breaker.HALF_OPEN, Breaker.OPEN),
    ],
)

# LLM-3: the quality dial. (class, effort) for thinking seats and for doing seats.
QUALITY: dict[str, tuple[tuple[ModelClass, Effort], tuple[ModelClass, Effort]]] = {
    "fast": ((ModelClass.BALANCED, Effort.MEDIUM), (ModelClass.FAST, Effort.LOW)),
    "balanced": ((ModelClass.FRONTIER, Effort.HIGH), (ModelClass.BALANCED, Effort.MEDIUM)),
    "best": ((ModelClass.FRONTIER, Effort.MAX), (ModelClass.FRONTIER, Effort.HIGH)),
}
_ORDER = [ModelClass.FAST, ModelClass.BALANCED, ModelClass.FRONTIER]


def wanted(quality: str, seat: Seat, role: Role) -> tuple[ModelClass, Effort]:
    """What the quality dial asks for a seat (LLM-3). Thinking seats are the CEO, leads and
    reviewers. The dial never goes below the role's floor."""
    thinking = seat.kind in (SeatKind.CEO, SeatKind.REVIEWER) or seat.is_lead
    model_class, effort = QUALITY[quality][0 if thinking else 1]
    if role.min_class and _ORDER.index(ModelClass(role.min_class)) > _ORDER.index(model_class):
        model_class = ModelClass(role.min_class)
    if seat.override_class:
        model_class = ModelClass(seat.override_class)
    if seat.override_effort:
        effort = Effort(seat.override_effort)
    return model_class, effort


def provider_of(credential: ModelCredential) -> ProviderInfo:
    return providers()[credential.provider]


async def credential_named(session: AsyncSession, name: str) -> ModelCredential:
    row = await session.scalar(
        select(ModelCredential).where(
            ModelCredential.name == name, ModelCredential.state != CredentialState.DELETED
        )
    )
    if row is None:
        raise Refusal(
            "credential_not_found",
            f"There is no credential named {name}.",
            kind=RefusalKind.NOT_FOUND,
            hint="List them with `crewmind credentials list`.",
        )
    return row


async def lineup_of(session: AsyncSession, credential: ModelCredential) -> dict[ModelClass, str]:
    rows = await session.scalars(select(Lineup).where(Lineup.credential_id == credential.id))
    lineup = {ModelClass(row.model_class): row.model for row in rows}
    return lineup or dict(provider_of(credential).default_lineup)


async def set_lineup(
    session: AsyncSession,
    credential: ModelCredential,
    models: list[str],
    now: datetime,
) -> dict[ModelClass, str]:
    """Pick the newest reachable model per class, keeping any admin override (LLM-4)."""
    picked = pick_lineup(provider_of(credential), models)
    existing = {
        ModelClass(row.model_class): row
        for row in await session.scalars(
            select(Lineup).where(Lineup.credential_id == credential.id)
        )
    }
    for model_class, model in picked.items():
        row = existing.get(model_class)
        if row is None:
            session.add(
                Lineup(
                    credential_id=credential.id,
                    model_class=model_class,
                    model=model,
                    source="auto",
                    updated_at=now,
                )
            )
        elif row.source == "auto":
            row.model, row.updated_at = model, now
    await session.flush()
    return await lineup_of(session, credential)


def breaker_allows(credential: ModelCredential, now: datetime) -> bool:
    """Whether calls may go to this credential: closed, or open with its cool-off over, in
    which case the next call is the half-open probe (LLM-11)."""
    if credential.breaker_state != Breaker.OPEN:
        return True
    assert credential.breaker_opened_at is not None
    return now >= credential.breaker_opened_at + timedelta(
        seconds=credential.breaker_cooloff_seconds
    )


async def _attached(
    session: AsyncSession, project_id: str
) -> dict[tuple[str, str], ModelCredential]:
    rows = await session.execute(
        select(ProjectCredential, ModelCredential)
        .join(ModelCredential, ModelCredential.id == ProjectCredential.credential_id)
        .where(
            ProjectCredential.project_id == project_id,
            ModelCredential.state == CredentialState.ACTIVE,
        )
    )
    return {(link.use, link.seat_id): credential for link, credential in rows.all()}


async def paying_credential(
    session: AsyncSession, project: Project, seat: Seat, now: datetime
) -> ModelCredential | None:
    """LLM-7: the seat's own credential, else the primary; the fallback while that one's
    breaker is open."""
    attached = await _attached(session, project.id)
    chosen = attached.get((Use.SEAT, seat.id)) or attached.get((Use.PRIMARY, ""))
    fallback = attached.get((Use.FALLBACK, ""))
    if chosen is not None and not breaker_allows(chosen, now) and fallback is not None:
        return fallback
    return chosen or fallback


class SeatResolver:
    """The one function that validates a seat and pins what it runs on, at hire, edit,
    start and lease (LLM-6, LLM-7, EXE-6)."""

    def __init__(
        self, settings: SettingsService, clock: Callable[[], datetime], *, mock_default: bool
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._mock_default = mock_default

    async def __call__(self, session: AsyncSession, project: Project, seat: Seat) -> Pinned:
        now = self._clock()
        role = await session.get(Role, seat.role_id)
        assert role is not None
        subject = Subject(Scope.PROJECT, project.id, project.type)
        quality = await self._settings.get(session, subject, "quality")
        model_class, effort = wanted(quality, seat, role)
        credential = await paying_credential(session, project, seat, now)
        if credential is None:
            if self._mock_default:
                return Pinned(MOCK, f"mock-{model_class}", None, "loop", effort)
            raise Refusal(
                "no_credential",
                "no credential on the project pays for this seat.",
                rule=LLM_6.id,
                hint="Add a credential and set it as the project's primary.",
            )
        provider = provider_of(credential)
        if not breaker_allows(credential, now):
            raise Wait(f"the credential {credential.name} is cooling off")
        if role.needs_vision and not provider.images:
            raise Refusal(
                "no_vision_model",
                f"the role {role.name} needs vision and {provider.label} has no vision model.",
                rule=LLM_6.id,
                hint="Pay this seat with a credential whose provider reads images.",
            )
        if role.needs_web and not provider.native_search and not await search_credential(session):
            raise Refusal(
                "no_web_search",
                f"the role {role.name} needs the web and no search service is configured.",
                rule=LLM_6.id,
                hint="An admin can add a search credential (INT-8).",
            )
        seat.substitution = None
        if seat.override_model:
            return Pinned(provider.name, seat.override_model, credential.id, "loop", effort)
        lineup = await lineup_of(session, credential)
        actual = nearest_class(model_class, set(lineup))
        if actual is None:
            raise Refusal(
                "no_model",
                f"the credential {credential.name} has no model in any class.",
                rule=LLM_6.id,
                hint="Refresh the credential's lineup, or override it.",
            )
        if actual is not model_class:
            seat.substitution = (
                f"{model_class.value.capitalize()} class asked for, running on a "
                f"{actual.value} model: no {model_class.value} model on {credential.name}."
            )
        return Pinned(
            provider.name, lineup[actual], credential.id, provider.default_harness, effort
        )


async def search_credential(session: AsyncSession) -> ModelCredential | None:
    """The install's one search service credential, if any (INT-8)."""
    return await session.scalar(
        select(ModelCredential).where(
            ModelCredential.kind == "search", ModelCredential.state == CredentialState.ACTIVE
        )
    )


async def provider_is_saturated(session: AsyncSession, provider: str) -> bool:
    """LLM-12: whether the provider is at its install-wide concurrency ceiling."""
    ceiling = await session.get(ProviderCeiling, provider)
    if ceiling is None:
        return False
    live = await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(Run.provider == provider, Run.state.in_(LIVE_STATES))
    )
    return (live or 0) >= ceiling.max_concurrent


def record_success(credential: ModelCredential) -> bool:
    """A call succeeded. Returns True when this closed the breaker (LLM-11)."""
    credential.auth_failures = 0
    credential.breaker_failures = 0
    if credential.breaker_state == Breaker.CLOSED:
        return False
    if credential.breaker_state == Breaker.OPEN:
        BREAKER_MACHINE.check(Breaker.OPEN, Breaker.HALF_OPEN)
    BREAKER_MACHINE.check(Breaker.HALF_OPEN, Breaker.CLOSED)
    credential.breaker_state = Breaker.CLOSED
    credential.breaker_cooloff_seconds = 0
    credential.breaker_opened_at = None
    return True


def record_transient_failure(credential: ModelCredential, now: datetime) -> bool:
    """A transient provider failure. Returns True when this opened the breaker: after 3 in
    a row, or when the half-open probe fails. The cool-off starts at 5 minutes and doubles
    up to 1 hour (LLM-11)."""
    if credential.breaker_state == Breaker.OPEN:
        BREAKER_MACHINE.check(Breaker.OPEN, Breaker.HALF_OPEN)
        BREAKER_MACHINE.check(Breaker.HALF_OPEN, Breaker.OPEN)
        doubled = timedelta(seconds=credential.breaker_cooloff_seconds) * 2
        credential.breaker_cooloff_seconds = int(min(doubled, BREAKER_MAX_COOLOFF).total_seconds())
        credential.breaker_opened_at = now
        return True
    credential.breaker_failures += 1
    if credential.breaker_failures < BREAKER_FAILURES:
        return False
    BREAKER_MACHINE.check(Breaker.CLOSED, Breaker.OPEN)
    credential.breaker_state = Breaker.OPEN
    credential.breaker_cooloff_seconds = int(BREAKER_FIRST_COOLOFF.total_seconds())
    credential.breaker_opened_at = now
    return True


def record_auth_failure(credential: ModelCredential) -> bool:
    """An authentication failure. It does not trip the breaker; 3 in a row pause the project
    (LLM-11, PRJ-2). Returns True at the third."""
    credential.auth_failures += 1
    return credential.auth_failures >= AUTH_FAILURES_BEFORE_PAUSE
