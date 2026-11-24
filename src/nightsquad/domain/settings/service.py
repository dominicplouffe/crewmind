"""Reading and changing governed settings (GOV-1, Appendix A).

Values are versioned and append-only: the newest version of a setting is its value, and a
setting never written has its registry default. Code reads tunable numbers only from here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.settings.registry import (
    Scope,
    Setting,
    SettingsRegistry,
    SettingValue,
    SettingValueError,
    UnknownSettingError,
)
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import SettingValue as SettingRow

INSTALL_SUBJECT = "install"
REASON_MIN_LENGTH = 10  # GOV-1, a fixed rule

SETTING_CHANGED = event_type("setting.changed", "A setting got a new version (GOV-1).")
GOV_1 = rules.register(
    Rule("GOV-1", "Settings change only by the right person, with a reason, within their range.")
)

PRESET = "authority.preset"
PRESETS: dict[str, dict[str, str]] = {
    "autonomous": {
        "authority.accept_scope": "ceo",
        "authority.change_scope": "ceo",
        "authority.date": "ceo",
        "authority.verdict": "reviewer",
        "authority.credential_rescope": "ceo",
        "authority.reserve_draw": "ceo",
    },
    "supervised": {
        "authority.accept_scope": "chairman",
        "authority.change_scope": "chairman",
        "authority.date": "chairman",
        "authority.verdict": "chairman",
        "authority.credential_rescope": "chairman",
        "authority.reserve_draw": "chairman",
    },
}


def refuse(code: str, message: str, hint: str) -> Refusal:
    return Refusal(code, message, kind=RefusalKind.RULE, rule=GOV_1.id, hint=hint)


@dataclass(frozen=True)
class Subject:
    """Whose settings: a project (with its type), a person, or the install."""

    scope: Scope
    id: str
    project_type: str | None = None
    solo: bool = False

    def has(self, setting: Setting) -> bool:
        if setting.scope is not self.scope:
            return False
        return not setting.project_types or self.project_type in setting.project_types


Constraint = Callable[[Mapping[str, SettingValue], Subject], str | None]


async def project_subject(session: AsyncSession, project: Any) -> Subject:
    """The project as the subject of a settings change. It is solo when no lead or worker
    seat is active, the only case where independent read may be off (WRK-9)."""
    from nightsquad.storage.models import Seat

    doing_work = await session.scalar(
        select(Seat.id)
        .where(
            Seat.project_id == project.id,
            Seat.state == "active",
            Seat.kind.in_(["lead", "worker"]),
        )
        .limit(1)
    )
    return Subject(Scope.PROJECT, project.id, project.type, solo=doing_work is None)


def _warn_before_wrapup(values: Mapping[str, SettingValue], _: Subject) -> str | None:
    warn, wrapup = values.get("budget.warn_at"), values.get("budget.wrapup_at")
    if isinstance(warn, int) and isinstance(wrapup, int) and warn >= wrapup:
        return f"budget.warn_at ({warn}%) must be below budget.wrapup_at ({wrapup}%)."
    return None


def _independent_review(values: Mapping[str, SettingValue], subject: Subject) -> str | None:
    if values.get("review.independent") is False and not subject.solo:
        return "review.independent can be off only in a solo project (WRK-9)."
    return None


def _checked_by_range(_: Mapping[str, SettingValue], __: Subject) -> str | None:
    return None


CONSTRAINTS: dict[str, Constraint] = {
    "warn_before_wrapup": _warn_before_wrapup,
    "independent_review_off_only_solo": _independent_review,
    # The next two are enforced by each setting's own choices and project types.
    "verdict_never_ceo": _checked_by_range,
    "cycle_settings_operate_only": _checked_by_range,
}


class SettingsService:
    def __init__(self, registry: SettingsRegistry) -> None:
        self.registry = registry

    def default(self, setting: Setting, subject: Subject, values: Mapping[str, Any]) -> Any:
        if setting.default_by is not None:
            key = (
                subject.project_type
                if setting.default_by.setting == "project.type"
                else values.get(setting.default_by.setting)
            )
            if isinstance(key, str) and key in setting.default_by.values:
                return setting.default_by.values[key]
        return setting.default

    async def stored(self, session: AsyncSession, subject: Subject) -> dict[str, SettingRow]:
        """The newest stored version of each setting written for `subject`."""
        newest = (
            select(SettingRow.name, func.max(SettingRow.version).label("version"))
            .where(SettingRow.scope == subject.scope, SettingRow.subject_id == subject.id)
            .group_by(SettingRow.name)
            .subquery()
        )
        rows = await session.scalars(
            select(SettingRow)
            .join(
                newest,
                (SettingRow.name == newest.c.name) & (SettingRow.version == newest.c.version),
            )
            .where(SettingRow.scope == subject.scope, SettingRow.subject_id == subject.id)
        )
        return {row.name: row for row in rows}

    async def effective(self, session: AsyncSession, subject: Subject) -> dict[str, Any]:
        """Every setting that applies to `subject`, with its current value."""
        stored = await self.stored(session, subject)
        values: dict[str, Any] = {name: row.value for name, row in stored.items()}
        for setting in self.registry.settings.values():
            if subject.has(setting) and setting.name not in values:
                values[setting.name] = self.default(setting, subject, values)
        return {name: values[name] for name in self.registry.settings if name in values}

    async def get(self, session: AsyncSession, subject: Subject, name: str) -> Any:
        return (await self.effective(session, subject))[name]

    async def change(
        self,
        session: AsyncSession,
        subject: Subject,
        changes: Mapping[str, Any],
        *,
        reason: str | None,
        caller: Caller,
        now: datetime,
    ) -> dict[str, int]:
        """Apply a bundle of changes as a whole, or refuse it and change nothing (GOV-1).
        Returns the new version of each changed setting."""
        if not changes:
            raise refuse("no_changes", "No setting was named.", "Name at least one setting.")
        given = 0 if reason is None else len(reason.strip())
        if subject.scope is not Scope.PERSON and given < REASON_MIN_LENGTH:
            raise refuse(
                "reason_required",
                f"A setting change needs a reason of at least {REASON_MIN_LENGTH} "
                f"characters; this one has {given}.",
                "Say why the setting is changing.",
            )
        bundle = self._validated(subject, changes)
        before = await self.effective(session, subject)
        bundle = self._with_preset(bundle, before)
        after = {**before, **bundle}
        for constraint in self.registry.constraints:
            problem = CONSTRAINTS[constraint.id](after, subject)
            if problem is not None:
                raise refuse("constraint_broken", problem, "Change both settings together.")
        stored = await self.stored(session, subject)
        versions: dict[str, int] = {}
        for name, value in bundle.items():
            version = stored[name].version + 1 if name in stored else 1
            versions[name] = version
            session.add(
                SettingRow(
                    scope=subject.scope,
                    subject_id=subject.id,
                    name=name,
                    value=value,
                    version=version,
                    reason=reason,
                    actor_kind=caller.kind,
                    actor_id=caller.actor_id,
                    at=now,
                )
            )
            append_event(
                session,
                type=SETTING_CHANGED,
                caller=caller,
                at=now,
                subject=("setting", name),
                project_id=subject.id if subject.scope is Scope.PROJECT else None,
                before={"value": before.get(name)},
                after={"value": value},
                detail={
                    "scope": subject.scope,
                    "subject": subject.id,
                    "version": version,
                    "reason": reason,
                },
            )
        return versions

    def _validated(self, subject: Subject, changes: Mapping[str, Any]) -> dict[str, Any]:
        bundle: dict[str, Any] = {}
        for name, value in changes.items():
            try:
                setting = self.registry.get(name)
            except UnknownSettingError as error:
                raise refuse(
                    "unknown_setting", str(error), "Use a name from the registry."
                ) from None
            if not subject.has(setting):
                if setting.scope is not subject.scope:
                    problem = f"{name} is a {setting.scope} setting, not a {subject.scope} setting."
                else:
                    problem = (
                        f"{name} applies only to {', '.join(setting.project_types)} projects; "
                        f"this is a {subject.project_type} project."
                    )
                raise refuse("setting_not_applicable", problem, "Change it where it applies.")
            if name == PRESET and value == "custom":
                raise refuse(
                    "preset_custom",
                    "The custom preset is set automatically when a verb setting changes.",
                    "Change the authority verb settings instead.",
                )
            try:
                bundle[name] = setting.validate_value(value)
            except SettingValueError as error:
                raise refuse(
                    "value_out_of_range", str(error), "Use a value in the range."
                ) from None
        return bundle

    def _with_preset(self, bundle: dict[str, Any], before: Mapping[str, Any]) -> dict[str, Any]:
        """Choosing a preset writes all six verbs; changing a verb alone makes it custom."""
        verbs = PRESETS["autonomous"].keys()
        if PRESET in bundle:
            wanted = PRESETS[bundle[PRESET]]
            for verb in verbs:
                if verb in bundle and bundle[verb] != wanted[verb]:
                    raise refuse(
                        "preset_conflict",
                        f"{verb} = {bundle[verb]} disagrees with the {bundle[PRESET]} preset.",
                        "Choose the preset, or set the verbs, not both.",
                    )
            return {**bundle, **wanted}
        if any(verb in bundle for verb in verbs) and PRESET in before:
            resulting = {verb: bundle.get(verb, before[verb]) for verb in verbs}
            preset = next((name for name, v in PRESETS.items() if v == resulting), "custom")
            if preset != before[PRESET]:
                return {**bundle, PRESET: preset}
        return bundle
