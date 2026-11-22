"""Who may do what to the plan (section 3, PLN-1, P7).

The chairman holds every verb. The CEO holds a verb only when the project's
`authority.<verb>` setting is "ceo".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller, CallerKind
from crewmind.catalog.refusal import Refusal
from crewmind.domain.planning.rules import PLN_1
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import SettingsService, Subject
from crewmind.storage.models import Project, Requirement

CHAIRMAN, CEO = "chairman", "ceo"
Verb = Literal["accept_scope", "change_scope", "date", "reserve_draw"]


@dataclass(frozen=True)
class Actor:
    """Who is acting on the plan: the chairman (a person) or the CEO (a seat)."""

    kind: str
    id: str
    caller: Caller

    @property
    def is_chairman(self) -> bool:
        return self.kind == CHAIRMAN


def actor_of(caller: Caller) -> Actor:
    kind = CHAIRMAN if caller.kind is CallerKind.PERSON else CEO
    return Actor(kind, caller.actor_id, caller)


def subject(project: Project) -> Subject:
    return Subject(Scope.PROJECT, project.id, project.type)


async def ceo_holds(
    session: AsyncSession, settings: SettingsService, project: Project, verb: Verb
) -> bool:
    return await settings.get(session, subject(project), f"authority.{verb}") == CEO


async def require(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    verb: Verb,
    what: str,
) -> None:
    """Refuse the CEO a verb the project's settings give to the chairman."""
    if actor.is_chairman or await ceo_holds(session, settings, project, verb):
        return
    raise Refusal(
        "needs_the_chairman",
        f"In this project, {what} is the chairman's decision (`authority.{verb}` is chairman).",
        rule=PLN_1.id,
        hint="Ask the chairman in chat.",
    )


async def require_scope_change(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    requirement: Requirement,
    what: str,
) -> None:
    """PLN-1, P7: a chairman-authored requirement is changed by the chairman only; a
    CEO-authored one by whoever holds scope authority."""
    if actor.is_chairman:
        return
    if requirement.author_kind == CHAIRMAN:
        raise Refusal(
            "chairman_authored",
            f"Requirement {requirement.id} was written by the chairman, so only the chairman "
            f"may {what}.",
            rule=PLN_1.id,
            hint="Ask the chairman in chat.",
        )
    await require(session, settings, project, actor, "change_scope", f"to {what}")
