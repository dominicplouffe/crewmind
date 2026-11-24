"""Operations on model credentials, lineups and who pays (LLM-2 to LLM-7, LLM-10, LLM-12)."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import PERSON_AND_MCP, Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.execution import runs
from nightsquad.domain.models import service
from nightsquad.domain.models.service import (
    CREDENTIAL_MACHINE,
    LLM_2,
    LLM_6,
    SEARCH_PROVIDERS,
    SECRET_OWNER,
    CredentialState,
    Use,
)
from nightsquad.domain.projects.access import view_of
from nightsquad.domain.projects.operations import ProjectRef
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import Subject
from nightsquad.gateway import outbound
from nightsquad.gateway.protocol import CompletionRequest, Turn
from nightsquad.gateway.registry import Effort, ModelClass, providers
from nightsquad.services import services_of
from nightsquad.storage.events import event_type
from nightsquad.storage.models import (
    LedgerLine,
    Lineup,
    ModelCredential,
    ProjectCredential,
    ProviderCeiling,
    Role,
    Seat,
)

CREDENTIAL_ADDED = event_type("credential.added", "A model credential was added (LLM-2).")
CREDENTIAL_STATE = event_type("credential.state_changed", "A credential changed state (7.18).")
LINEUP_CHANGED = event_type("credential.lineup_changed", "A credential's lineup changed (LLM-4).")
PAYER_CHANGED = event_type("project.payer_changed", "Who pays in a project changed (LLM-7).")
CEILING_CHANGED = event_type("provider.ceiling_changed", "A provider ceiling changed (LLM-12).")
SMOKE_TESTED = event_type("credential.smoke_tested", "A credential made one test call.")
SEAT_OVERRIDDEN = event_type("seat.model_overridden", "A seat's model choice was overridden.")


class AddCredentialInput(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="A name to refer to it by.")
    provider: str = Field(description="A provider from `models providers`, or brave for search.")
    key: SecretStr = Field(
        description="The API key, or for a command-line agent its login: the token or the "
        "contents of its login file. It is encrypted and never shown again."
    )
    base_url: str | None = Field(
        default=None, description="The endpoint, where the provider needs one."
    )


class CredentialItem(BaseModel):
    name: str
    provider: str
    kind: str
    state: str
    breaker: str
    lineup: dict[str, str]
    owner_id: str


class CredentialList(BaseModel):
    items: list[CredentialItem]


class CredentialRef(BaseModel):
    name: str = Field(description="The credential's name.")


class OverrideLineupInput(CredentialRef):
    model_class: ModelClass = Field(description="fast, balanced or frontier.")
    model: str = Field(min_length=1, description="The exact model id to use for that class.")


class SmokeResult(BaseModel):
    ok: bool
    model: str
    detail: str
    tokens: int


class PayerInput(ProjectRef):
    credential: str = Field(description="The credential's name.")
    use: Literal["primary", "fallback"] = Field("primary", description="primary or fallback.")


class SeatModelInput(ProjectRef):
    seat: str = Field(description="The seat's name.")
    credential: str | None = Field(default=None, description="A credential to pay this seat.")
    model_class: ModelClass | None = Field(default=None, description="Override the class.")
    model: str | None = Field(default=None, description="Override with an exact model id.")
    effort: Effort | None = Field(default=None, description="Override the effort.")


class SeatModel(BaseModel):
    seat: str
    name: str = Field(description="The name the agent goes by (EXE-18).")
    kind: str
    asked_class: str
    effort: str
    paid_by: str | None = Field(description="The name of the credential that pays this seat.")
    provider: str | None
    model: str | None
    note: str | None = Field(description="A substitution, or why the seat cannot run.")


class ModelsView(BaseModel):
    quality: str
    seats: list[SeatModel]


class ProviderItem(BaseModel):
    name: str
    label: str
    needs_base_url: bool
    images: bool
    ceiling: int | None
    credential: str = Field(description="key, or login for a command-line agent (LLM-2).")
    login_hint: str = Field(description="What to paste as a login, in plain words.")


class ProviderList(BaseModel):
    items: list[ProviderItem]


class CeilingInput(BaseModel):
    provider: str = Field(description="The provider's name.")
    max_concurrent: int = Field(ge=1, le=1000, description="Runs allowed at once, install-wide.")


LOGIN_FILES = ("codex", "gemini_cli", "opencode")
"""Providers whose login is a file of JSON, pasted whole (LLM-2)."""


def _kind_of(payload: AddCredentialInput, is_search: bool) -> str:
    """The credential's kind, from its provider (LLM-2). A login pasted in the wrong shape
    is refused here, where the person can fix it, and not in an agent's first run."""
    if is_search:
        return "search"
    provider = providers()[payload.provider]
    if not provider.is_login:
        return service.KIND_KEY
    if payload.provider in LOGIN_FILES:
        try:
            pasted = json.loads(payload.key.get_secret_value())
        except ValueError:
            pasted = None
        if not isinstance(pasted, dict):
            raise Refusal(
                "login_not_readable",
                f"That is not the login file of {provider.label}: it is not a JSON object.",
                rule=LLM_2.id,
                hint=provider.login_hint,
            )
    return service.KIND_LOGIN


def _refuse_login(row: ModelCredential, action: str) -> None:
    """LLM-8: the gateway makes no call with a login, so it cannot list its models or
    test it. The command-line agent holds it, inside the sandbox."""
    if row.kind == service.KIND_LOGIN:
        raise Refusal(
            "login_credential",
            f"{row.name} is the login of a command-line agent, so the server cannot {action} "
            "with it. Its first run shows whether it works.",
            rule=LLM_2.id,
            hint="To choose its models, override the lineup.",
        )


def _store(context: Context) -> SecretStore:
    return SecretStore(services_of(context).master_key_file)


async def _item(context: Context, row: ModelCredential) -> CredentialItem:
    paying = row.kind in service.PAYING_KINDS
    lineup = await service.lineup_of(context.session, row) if paying else {}
    return CredentialItem(
        name=row.name,
        provider=row.provider,
        kind=row.kind,
        state=row.state,
        breaker=row.breaker_state,
        lineup={model_class.value: model for model_class, model in lineup.items()},
        owner_id=row.owner_id,
    )


async def _mine(context: Context, name: str) -> ModelCredential:
    """A credential the caller may manage: their own, or any for an admin."""
    row = await service.credential_named(context.session, name)
    if row.owner_id != context.caller.actor_id and not context.caller.is_admin:
        raise Refusal(
            "credential_not_found",
            f"There is no credential named {name}.",
            kind=RefusalKind.NOT_FOUND,
            hint="List them with `squad credentials list`.",
        )
    return row


@operation(
    "credentials.add",
    summary="Add a model credential (an API key), or the install's web search key.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def add_credential(context: Context, payload: AddCredentialInput) -> CredentialItem:
    """LLM-2, INT-8, ACC-6: stored encrypted, listed by name only. The search service key
    is install-wide, so only an admin adds it."""
    is_search = payload.provider in SEARCH_PROVIDERS
    if not is_search and payload.provider not in providers():
        known = ", ".join([*providers(), *SEARCH_PROVIDERS])
        raise Refusal(
            "provider_unknown",
            f"{payload.provider} is not a known provider. Known: {known}.",
            rule=LLM_2.id,
            hint="Use an OpenAI-compatible endpoint with provider openai_compatible.",
        )
    if is_search and not context.caller.is_admin:
        raise Refusal(
            "admin_only", "Only an admin sets the install's search service.", rule=LLM_2.id
        )
    if not is_search and providers()[payload.provider].needs_base_url and not payload.base_url:
        raise Refusal(
            "base_url_required",
            f"{providers()[payload.provider].label} needs its endpoint address.",
            rule=LLM_2.id,
            hint="Give --base-url.",
        )
    taken = await context.session.scalar(
        select(ModelCredential.id).where(ModelCredential.name == payload.name)
    )
    if taken:
        raise Refusal(
            "credential_exists", f"A credential named {payload.name} exists.", rule=LLM_2.id
        )
    CREDENTIAL_MACHINE.check("(new)", CredentialState.ACTIVE)
    row = ModelCredential(
        name=payload.name,
        provider=payload.provider,
        kind=_kind_of(payload, is_search),
        base_url=payload.base_url,
        owner_id=context.caller.actor_id,
        state=CredentialState.ACTIVE,
        created_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    await _store(context).put(
        context.session, (SECRET_OWNER, row.id), "key", payload.key.get_secret_value(), context.now
    )
    context.record(
        CREDENTIAL_ADDED,
        subject=("credential", row.name),
        after={"state": CredentialState.ACTIVE, "provider": row.provider, "kind": row.kind},
    )
    return await _item(context, row)


@operation(
    "credentials.list",
    summary="List your credentials by name. Values are never shown.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def list_credentials(context: Context, payload: Empty) -> CredentialList:
    statement = select(ModelCredential).where(ModelCredential.state != CredentialState.DELETED)
    if not context.caller.is_admin:
        statement = statement.where(ModelCredential.owner_id == context.caller.actor_id)
    rows = await context.session.scalars(statement.order_by(ModelCredential.name))
    return CredentialList(items=[await _item(context, row) for row in rows])


async def _set_state(context: Context, name: str, target: CredentialState) -> CredentialItem:
    row = await _mine(context, name)
    CREDENTIAL_MACHINE.check(row.state, target)
    before = row.state
    row.state = target
    if target is CredentialState.DELETED:
        row.name = f"{row.name} (deleted {row.id[:8]})"
    context.record(
        CREDENTIAL_STATE,
        subject=("credential", name),
        before={"state": before},
        after={"state": target},
    )
    return await _item(context, row)


@operation(
    "credentials.hide",
    summary="Hide a credential without deleting it. Seats it paid for stop running.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def hide_credential(context: Context, payload: CredentialRef) -> CredentialItem:
    return await _set_state(context, payload.name, CredentialState.HIDDEN)


@operation(
    "credentials.show",
    summary="Make a hidden credential active again.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def show_credential(context: Context, payload: CredentialRef) -> CredentialItem:
    return await _set_state(context, payload.name, CredentialState.ACTIVE)


@operation(
    "credentials.delete",
    summary="Delete a credential for good.",
    authority=Authority.PERSON,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def delete_credential(context: Context, payload: CredentialRef) -> CredentialItem:
    return await _set_state(context, payload.name, CredentialState.DELETED)


@operation(
    "credentials.refresh_lineup",
    summary="Re-read the models a credential can reach and pick the newest per class.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def refresh_lineup(context: Context, payload: CredentialRef) -> CredentialItem:
    """LLM-4: lineups are picked automatically from the models the credential can reach."""
    row = await _mine(context, payload.name)
    _refuse_login(row, "read its model list")
    key = await _store(context).reveal(context.session, (SECRET_OWNER, row.id), "key")
    models = await outbound.list_models(service.provider_of(row), key, row.base_url)
    lineup = await service.set_lineup(context.session, row, models, context.now)
    context.record(
        LINEUP_CHANGED,
        subject=("credential", row.name),
        after={model_class.value: model for model_class, model in lineup.items()},
        detail={"source": "auto", "models_seen": len(models)},
    )
    return await _item(context, row)


@operation(
    "credentials.override_lineup",
    summary="Pin the model a credential uses for one class.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def override_lineup(context: Context, payload: OverrideLineupInput) -> CredentialItem:
    """LLM-4: an admin may override a lineup. An override survives the daily refresh."""
    row = await service.credential_named(context.session, payload.name)
    existing = await context.session.scalar(
        select(Lineup).where(
            Lineup.credential_id == row.id, Lineup.model_class == payload.model_class
        )
    )
    if existing is None:
        context.session.add(
            Lineup(
                credential_id=row.id,
                model_class=payload.model_class,
                model=payload.model,
                source="override",
                updated_at=context.now,
            )
        )
    else:
        existing.model, existing.source, existing.updated_at = (
            payload.model,
            "override",
            context.now,
        )
    await context.session.flush()
    context.record(
        LINEUP_CHANGED,
        subject=("credential", row.name),
        after={payload.model_class.value: payload.model},
        detail={"source": "override"},
    )
    return await _item(context, row)


@operation(
    "credentials.smoke",
    summary="Make one tiny real call with a credential, to see that it works. It is metered.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def smoke(context: Context, payload: CredentialRef) -> SmokeResult:
    """LLM-10: one tiny real call, metered on the install's ledger."""
    row = await _mine(context, payload.name)
    _refuse_login(row, "make a test call")
    provider = service.provider_of(row)
    lineup = await service.lineup_of(context.session, row)
    if not lineup:
        raise Refusal(
            "no_model",
            f"{row.name} has no model yet.",
            rule=LLM_6.id,
            hint="Run `credentials refresh-lineup`, or override the lineup.",
        )
    model = lineup.get(ModelClass.FAST) or next(iter(lineup.values()))
    key = await _store(context).reveal(context.session, (SECRET_OWNER, row.id), "key")
    request = CompletionRequest(
        system="Reply with the single word: ok", messages=[Turn(role="user", content="ok?")]
    )
    try:
        answer = await outbound.call_model(
            provider, request, model=model, api_key=key, base_url=row.base_url, effort=None
        )
    except Exception as error:
        return SmokeResult(
            ok=False, model=model, detail=f"{type(error).__name__}: {error}"[:300], tokens=0
        )
    usage = answer.usage
    counted = usage.input + usage.cache_write + usage.output
    context.session.add(
        LedgerLine(
            project_id=None,
            run_id=None,
            seat_id=None,
            credential_id=row.id,
            kind="smoke",
            unit="tokens",
            provider=provider.name,
            model=model,
            input_tokens=usage.input,
            output_tokens=usage.output,
            cache_write_tokens=usage.cache_write,
            cache_read_tokens=usage.cache_read,
            counted=counted,
            at=context.now,
        )
    )
    context.record(
        SMOKE_TESTED, subject=("credential", row.name), detail={"model": model, "tokens": counted}
    )
    return SmokeResult(ok=True, model=model, detail=answer.text[:100], tokens=counted)


@operation(
    "models.set_payer",
    summary="Choose the credential that pays a project's seats, or its fallback.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_payer(context: Context, payload: PayerInput) -> ModelsView:
    """LLM-7: one primary credential, and an optional fallback."""
    credential = await _mine(context, payload.credential)
    await _link(context, payload.project_id, credential, Use(payload.use), "")
    return await _models(context)


async def _link(
    context: Context, project_id: str, credential: ModelCredential, use: Use, seat_id: str
) -> None:
    existing = await context.session.scalar(
        select(ProjectCredential).where(
            ProjectCredential.project_id == project_id,
            ProjectCredential.use == use,
            ProjectCredential.seat_id == seat_id,
        )
    )
    if existing is None:
        context.session.add(
            ProjectCredential(
                project_id=project_id, credential_id=credential.id, use=use, seat_id=seat_id
            )
        )
    else:
        existing.credential_id = credential.id
    await context.session.flush()
    context.record(
        PAYER_CHANGED,
        subject=("credential", credential.name),
        project_id=project_id,
        after={"use": use, "seat": seat_id or None},
    )


@operation(
    "models.set_seat",
    summary="Advanced: pay one seat with another credential, or override its model or effort.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_seat(context: Context, payload: SeatModelInput) -> ModelsView:
    """LLM-3, LLM-7: Advanced lets a single seat be overridden. It applies at the seat's
    next run."""
    seat = await context.session.scalar(
        select(Seat).where(Seat.project_id == payload.project_id, Seat.name == payload.seat)
    )
    if seat is None:
        raise Refusal(
            "seat_not_found", f"There is no seat named {payload.seat}.", kind=RefusalKind.NOT_FOUND
        )
    if payload.credential is not None:
        credential = await _mine(context, payload.credential)
        await _link(context, payload.project_id, credential, Use.SEAT, seat.id)
    seat.override_class = payload.model_class
    seat.override_model = payload.model
    seat.override_effort = payload.effort
    context.record(
        SEAT_OVERRIDDEN,
        subject=("seat", seat.name),
        project_id=payload.project_id,
        after={"class": payload.model_class, "model": payload.model, "effort": payload.effort},
    )
    return await _models(context)


async def _models(context: Context) -> ModelsView:
    project = view_of(context).project
    services = services_of(context)
    quality = await services.settings.get(
        context.session, Subject(Scope.PROJECT, project.id, project.type), "quality"
    )
    seats = await context.session.scalars(
        select(Seat).where(Seat.project_id == project.id).order_by(Seat.created_at, Seat.name)
    )
    items: list[SeatModel] = []
    for seat in seats:
        role = await context.session.get(Role, seat.role_id)
        assert role is not None
        asked, effort = service.wanted(quality, seat, role)
        credential = await service.paying_credential(context.session, project, seat, context.now)
        note: str | None
        provider = model = None
        try:
            pinned = await runs.seat_resolver(context.session, project, seat)
            provider, model, note = pinned.provider, pinned.model, seat.substitution
        except Refusal as refusal:
            note = f"Cannot run: {refusal.envelope.message}"
        except runs.Wait as wait:
            note = f"Waiting: {wait}."
        items.append(
            SeatModel(
                seat=seat.name,
                name=seat.display_name,
                kind=seat.kind,
                asked_class=asked,
                effort=effort,
                paid_by=credential.name if credential else None,
                provider=provider,
                model=model,
                note=note,
            )
        )
    return ModelsView(quality=quality, seats=items)


@operation(
    "models.show",
    summary="Show what each seat runs on: who pays, the model, and any substitution.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_models(context: Context, payload: ProjectRef) -> ModelsView:
    """LLM-4, P12: a substitution is always shown, never hidden."""
    return await _models(context)


@operation(
    "models.providers",
    summary="List the providers nightsquad can use, with any concurrency ceiling.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def list_providers(context: Context, payload: Empty) -> ProviderList:
    ceilings = {
        row.provider: row.max_concurrent
        for row in await context.session.scalars(select(ProviderCeiling))
    }
    return ProviderList(
        items=[
            ProviderItem(
                name=info.name,
                label=info.label,
                needs_base_url=info.needs_base_url,
                images=info.images,
                ceiling=ceilings.get(info.name),
                credential=info.credential,
                login_hint=info.login_hint,
            )
            for info in providers().values()
        ]
    )


@operation(
    "models.set_ceiling",
    summary="Limit how many runs may use one provider at once, across the install.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def set_ceiling(context: Context, payload: CeilingInput) -> ProviderList:
    """LLM-12: an install-wide ceiling keeps projects that share a key under its limits."""
    if payload.provider not in providers():
        raise Refusal(
            "provider_unknown", f"{payload.provider} is not a known provider.", rule=LLM_2.id
        )
    row = await context.session.get(ProviderCeiling, payload.provider)
    before = row.max_concurrent if row else None
    if row is None:
        context.session.add(
            ProviderCeiling(provider=payload.provider, max_concurrent=payload.max_concurrent)
        )
    else:
        row.max_concurrent = payload.max_concurrent
    await context.session.flush()
    context.record(
        CEILING_CHANGED,
        subject=("provider", payload.provider),
        before={"max_concurrent": before},
        after={"max_concurrent": payload.max_concurrent},
    )
    return await list_providers(context, Empty())
