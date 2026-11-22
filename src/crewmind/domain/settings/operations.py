"""Reading and changing settings, by scope (GOV-1, Appendix A)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.pagination import PageRequest, fetch_page
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.domain.settings.registry import Scope, SettingType
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.services import services_of
from crewmind.storage.models import Seat, SettingValue

Changes = dict[str, int | float | bool | str]


class SettingItem(BaseModel):
    name: str
    value: Any
    version: int = Field(description="0 means the registry default, never changed.")
    allowed: str
    unit: str | None = Field(
        default=None, description="What the value counts: seconds, bytes, tokens or percent."
    )


UNITS = {
    SettingType.DURATION: "seconds",
    SettingType.BYTES: "bytes",
    SettingType.TOKENS: "tokens",
    SettingType.PERCENT: "percent",
}


class SettingsView(BaseModel):
    scope: str
    items: list[SettingItem]


class ChangeMineInput(BaseModel):
    changes: Changes = Field(description="Setting names and their new values.")


class ChangeInstallInput(ChangeMineInput):
    reason: str = Field(description="Why, in at least 10 characters.")


class ChangeProjectInput(ProjectRef, ChangeInstallInput):
    pass


class HistoryInput(ProjectRef, PageRequest):
    pass


class HistoryItem(BaseModel):
    name: str
    value: Any
    version: int
    reason: str | None
    changed_by: str
    at: datetime


class History(BaseModel):
    items: list[HistoryItem]
    next: str | None = None


class Definition(BaseModel):
    name: str
    scope: str
    default: str
    allowed: str
    used_by: list[str]


class Registry(BaseModel):
    version: str
    settings: list[Definition]
    constraints: list[str]


async def _project_subject(context: Context) -> Subject:
    """The project as a settings subject. It is solo when no lead or worker seat is active,
    which is the only case where independent read may be turned off (WRK-9)."""
    project = view_of(context).project
    doing_work = await context.session.scalar(
        select(Seat.id)
        .where(
            Seat.project_id == project.id,
            Seat.state == "active",
            Seat.kind.in_(["lead", "worker"]),
        )
        .limit(1)
    )
    return Subject(Scope.PROJECT, project.id, project.type, solo=doing_work is None)


async def _view(context: Context, subject: Subject) -> SettingsView:
    services = services_of(context)
    values = await services.settings.effective(context.session, subject)
    stored = await services.settings.stored(context.session, subject)
    return SettingsView(
        scope=subject.scope,
        items=[
            SettingItem(
                name=name,
                value=value,
                version=stored[name].version if name in stored else 0,
                allowed=services.registry.settings[name].spec_range,
                unit=UNITS.get(services.registry.settings[name].type),
            )
            for name, value in values.items()
        ],
    )


async def _change(
    context: Context, subject: Subject, changes: Changes, reason: str | None
) -> SettingsView:
    await services_of(context).settings.change(
        context.session, subject, changes, reason=reason, caller=context.caller, now=context.now
    )
    await context.session.flush()
    return await _view(context, subject)


@operation(
    "settings.show_project",
    summary="Show a project's settings and their current values.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_project(context: Context, payload: ProjectRef) -> SettingsView:
    return await _view(context, await _project_subject(context))


@operation(
    "settings.change_project",
    summary="Change project settings, with a reason. The bundle applies as a whole or not at all.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def change_project(context: Context, payload: ChangeProjectInput) -> SettingsView:
    """GOV-1: only the chairman or a co-chair, with a reason of 10 or more characters."""
    return await _change(context, await _project_subject(context), payload.changes, payload.reason)


@operation(
    "settings.history_project",
    summary="Show every version of a project's settings, with who changed it and why.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def history_project(context: Context, payload: HistoryInput) -> History:
    rows, cursor = await fetch_page(
        context.session,
        select(SettingValue).where(
            SettingValue.scope == Scope.PROJECT, SettingValue.subject_id == payload.project_id
        ),
        payload,
        key=SettingValue.id,
        at=SettingValue.at,
    )
    return History(
        items=[
            HistoryItem(
                name=row.name,
                value=row.value,
                version=row.version,
                reason=row.reason,
                changed_by=row.actor_id,
                at=row.at,
            )
            for row in rows
        ],
        next=cursor,
    )


@operation(
    "settings.show_mine",
    summary="Show your own preferences.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def show_mine(context: Context, payload: Empty) -> SettingsView:
    return await _view(context, Subject(Scope.PERSON, context.caller.actor_id))


@operation(
    "settings.change_mine",
    summary="Change your own preferences. No reason is needed.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def change_mine(context: Context, payload: ChangeMineInput) -> SettingsView:
    """GOV-1: each person changes their own preferences; every change is audited."""
    subject = Subject(Scope.PERSON, context.caller.actor_id)
    return await _change(context, subject, payload.changes, None)


@operation(
    "settings.show_install",
    summary="Show the install's settings.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.READ,
)
async def show_install(context: Context, payload: Empty) -> SettingsView:
    return await _view(context, Subject(Scope.INSTALL, INSTALL_SUBJECT))


@operation(
    "settings.change_install",
    summary="Change install settings, with a reason.",
    authority=Authority.ADMIN,
    reversibility=Reversibility.REVERSIBLE,
)
async def change_install(context: Context, payload: ChangeInstallInput) -> SettingsView:
    """GOV-1: only an admin, with a reason of 10 or more characters."""
    subject = Subject(Scope.INSTALL, INSTALL_SUBJECT)
    return await _change(context, subject, payload.changes, payload.reason)


@operation(
    "settings.registry",
    summary="List every setting that exists, with its default and allowed range.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def registry(context: Context, payload: Empty) -> Registry:
    source = services_of(context).registry
    return Registry(
        version=source.version,
        settings=[
            Definition(
                name=setting.name,
                scope=setting.scope,
                default=setting.spec_default,
                allowed=setting.spec_range,
                used_by=list(setting.used_by),
            )
            for setting in source.settings.values()
        ],
        constraints=[constraint.spec for constraint in source.constraints],
    )
