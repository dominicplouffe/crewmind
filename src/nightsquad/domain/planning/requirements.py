"""Requirements: the scope of a project and who may change it (PLN-1, PLN-2, PLN-3, 7.2).

The chairman and the CEO call the same functions; `authority` decides who may.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.budget import service as budget
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.decisions import items
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.planning import authority, estimates, graph, readiness
from nightsquad.domain.planning.authority import CEO, CHAIRMAN, Actor
from nightsquad.domain.planning.model import OPEN_SCOPE, RequirementState, RequirementTest
from nightsquad.domain.planning.readiness import move
from nightsquad.domain.planning.rules import INV_19, PLN_1, PLN_3
from nightsquad.domain.projects.model import ProjectState, ProjectType
from nightsquad.domain.settings.service import SettingsService
from nightsquad.domain.work import tasks
from nightsquad.domain.work.model import OPEN_STATES, TaskState
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import Project, Requirement, RequirementDependency, Task

R = RequirementState
REQUIREMENT_EDITED = event_type(
    "requirement.edited", "A requirement's text, estimate, stage or dependencies changed."
)
REASON_MIN_CHARACTERS = 10  # 7.2: a decline or a cut carries a reason
CLOSED_PROJECT = (
    ProjectState.STOPPED,
    ProjectState.COMPLETED,
    ProjectState.DELETING,
    ProjectState.DELETED,
)


@dataclass(frozen=True)
class NewRequirement:
    text: str
    test_kind: RequirementTest
    success_test: str
    test_files: dict[str, str]
    estimate_runs: int | None
    stage: int
    depends_on: list[int]
    recurring: bool = False
    metric: dict[str, Any] | None = None


def _reason(reason: str) -> None:
    if len(reason.strip()) < REASON_MIN_CHARACTERS:
        raise Refusal(
            "reason_too_short",
            f"Give a reason of at least {REASON_MIN_CHARACTERS} characters.",
            rule=PLN_1.id,
        )


def check_open(project: Project) -> None:
    if project.state in CLOSED_PROJECT:
        raise Refusal(
            "project_closed", f"The project is {project.state}; its plan no longer changes."
        )


async def dependency_graph(session: AsyncSession, project_id: str) -> dict[int, set[int]]:
    found: dict[int, set[int]] = {}
    rows = await session.execute(
        select(RequirementDependency.requirement_id, RequirementDependency.depends_on).where(
            RequirementDependency.project_id == project_id
        )
    )
    for requirement_id, depends_on in rows.all():
        found.setdefault(int(requirement_id), set()).add(int(depends_on))
    return found


async def _add_dependencies(
    session: AsyncSession, requirement: Requirement, depends_on: list[int]
) -> None:
    """INV-19: an edge that would close a loop is refused, and the loop is named."""
    known = await dependency_graph(session, requirement.project_id)
    for other in dict.fromkeys(depends_on):
        await readiness.get(session, requirement.project_id, other)
        if other in known.get(requirement.id, set()):
            continue
        loop = graph.loop_if_added(known, requirement.id, other)
        if loop is not None:
            named = " -> ".join(str(one) for one in loop)
            raise Refusal(
                "dependency_loop",
                f"Requirement {requirement.id} cannot depend on {other}: that closes the "
                f"loop {named}.",
                rule=INV_19.id,
                hint="Drop one of the dependencies in the loop.",
            )
        session.add(
            RequirementDependency(
                project_id=requirement.project_id,
                requirement_id=requirement.id,
                depends_on=other,
            )
        )
        known.setdefault(requirement.id, set()).add(other)
    await session.flush()


async def _create(
    session: AsyncSession,
    project: Project,
    actor: Actor,
    new: NewRequirement,
    state: RequirementState,
    now: datetime,
) -> Requirement:
    requirement = Requirement(
        project_id=project.id,
        text=new.text.strip(),
        author_kind=actor.kind,
        author_id=actor.id,
        state="(new)",
        test_kind=new.test_kind,
        success_test=new.success_test,
        test_files=new.test_files,
        estimate_runs=new.estimate_runs,
        stage=new.stage,
        recurring=new.recurring,
        metric=new.metric,
        failures=0,
        escalated=False,
        created_at=now,
        accepted_at=now if state == R.ACCEPTED else None,
    )
    session.add(requirement)
    await session.flush()
    move(session, requirement, state, actor.caller, now, {"author": actor.kind})
    await _add_dependencies(session, requirement, new.depends_on)
    return requirement


async def _check_new_scope(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """GOV-3, PLN-8: the CEO takes on no new scope in wrap-up mode or while a commitment
    is at risk or breached. Proposing and reopening both count."""
    wrapup = await readiness.in_wrapup(session, settings, project, now)
    if wrapup is not None:
        raise Refusal(
            "wrap_up_mode",
            f"The project is in wrap-up mode ({budget.arithmetic(wrapup)}), so new scope "
            "is refused.",
            rule=budget.GOV_3.id,
            hint="Land what is in progress, or ask the chairman to raise the budget.",
        )
    for check in proposal_checks:
        await check(session, settings, project, now)


async def propose(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    new: NewRequirement,
    now: datetime,
) -> Requirement:
    """PLN-1, GOV-3: the CEO proposes scope. A proposal is not scope until accepted."""
    if project.type == ProjectType.EXPLORE:
        raise Refusal(
            "explore_has_bets",
            "An Explore project has bets, not requirements.",
            rule=PLN_1.id,
            hint="Open a bet instead.",
        )
    await _check_new_scope(session, settings, project, now)
    requirement = await _create(session, project, actor, new, R.PROPOSED, now)
    if not await authority.ceo_holds(session, settings, project, "accept_scope"):
        item = await items.file(
            session,
            settings,
            project,
            "proposed scope",
            filer=actor.caller,
            fields={
                "requirement_id": requirement.id,
                "estimate_runs": requirement.estimate_runs,
                "text": requirement.text,
            },
            recommendation=f"Accept requirement {requirement.id} into scope.",
            if_declined="The requirement is declined and no work is created for it.",
            subject=("requirement", str(requirement.id)),
            now=now,
            announce=False,
        )
        await conversation.platform_line(
            session,
            project.id,
            f"The CEO proposes requirement {requirement.id}: {requirement.text} "
            f"(estimate {requirement.estimate_runs} runs). Accept or decline it in the plan.",
            now,
            detail={"kind": "decision item", "item": item.id, "item_kind": item.kind},
        )
    return requirement


proposal_checks: list[Any] = []
"""More reasons to refuse a CEO proposal, each `(session, settings, project, now)`. The
scope freeze (PLN-8) registers here."""
scope_hooks: list[Any] = []
"""Called as `(session, settings, project, now)` after accepted scope changes, so that
what depends on it (the commitment, readiness to complete) follows at once."""


async def scope_changed(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    await session.flush()
    for hook in scope_hooks:
        await hook(session, settings, project, now)


async def add(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    new: NewRequirement,
    now: datetime,
) -> Requirement:
    """PLN-1: the chairman adds scope directly; it is accepted at once. The CEO is told."""
    assert actor.is_chairman
    check_open(project)
    if project.type == ProjectType.EXPLORE:
        raise Refusal(
            "explore_has_bets",
            "An Explore project has bets, not requirements. Its tasks serve bets.",
            rule=PLN_1.id,
            hint="Tell the CEO which bet to open, in the chat.",
        )
    requirement = await _create(session, project, actor, new, R.ACCEPTED, now)
    ceo = await ceo_of(session, project.id)
    estimate = (
        f"estimate {new.estimate_runs} runs"
        if new.estimate_runs is not None
        else "no estimate yet: estimate it with agent_change_requirement before creating work"
    )
    notices.notify(
        session,
        project.id,
        ceo.id,
        "scope added",
        f"The chairman added requirement {requirement.id}: {requirement.text} ({estimate}).",
        now,
        urgent=True,
    )
    await scope_changed(session, settings, project, now)
    return requirement


async def accept(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    requirement: Requirement,
    now: datetime,
    *,
    anyway: bool = False,
) -> estimates.Fit:
    """PLN-1, PLN-3: accept a proposal when the plan still fits the budget. The chairman
    may accept anyway; the CEO may not."""
    check_open(project)
    await authority.require(session, settings, project, actor, "accept_scope", "accepting scope")
    if requirement.state != R.PROPOSED:
        raise Refusal(
            "not_proposed",
            f"Requirement {requirement.id} is {requirement.state}, not proposed.",
            rule=PLN_1.id,
        )
    fit = await estimates.fits_budget(
        session, settings, project, now, including=requirement.estimate_runs or 0
    )
    if not fit.fits and not (actor.is_chairman and anyway):
        raise Refusal(
            "does_not_fit_budget",
            f"Requirement {requirement.id} does not fit the budget. {fit.arithmetic}",
            rule=PLN_3.id,
            hint="Accept it anyway, or raise the budget."
            if actor.is_chairman
            else "Cut or shrink other scope, or ask the chairman to raise the budget.",
        )
    requirement.accepted_at = now
    move(session, requirement, R.ACCEPTED, actor.caller, now, {"fits": fit.fits})
    await items.settle(
        session, "proposed scope", ("requirement", str(requirement.id)), "accept", actor.caller, now
    )
    if actor.is_chairman:
        ceo = await ceo_of(session, project.id)
        notices.notify(
            session,
            project.id,
            ceo.id,
            "scope accepted",
            f"The chairman accepted requirement {requirement.id}: {requirement.text}",
            now,
            urgent=True,
        )
    await scope_changed(session, settings, project, now)
    return fit


async def decline(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    requirement: Requirement,
    reason: str,
    now: datetime,
) -> None:
    """7.2: decline a proposal, with a reason."""
    await authority.require(session, settings, project, actor, "accept_scope", "declining scope")
    _reason(reason)
    requirement.reason = reason.strip()
    move(session, requirement, R.DECLINED, actor.caller, now, {"reason": reason.strip()})
    await items.settle(
        session,
        "proposed scope",
        ("requirement", str(requirement.id)),
        "decline",
        actor.caller,
        now,
    )
    if actor.is_chairman:
        ceo = await ceo_of(session, project.id)
        notices.notify(
            session,
            project.id,
            ceo.id,
            "scope declined",
            f"The chairman declined requirement {requirement.id}: {reason.strip()}",
            now,
        )


async def kill_open_tasks(
    session: AsyncSession, requirement: Requirement, actor: Actor, now: datetime, why: str
) -> int:
    """7.2, INV-18: no open task remains under a cut requirement."""
    rows = list(
        await session.scalars(
            select(Task)
            .where(Task.requirement_id == requirement.id, Task.state.in_(OPEN_STATES))
            .order_by(Task.id)
        )
    )
    for task in rows:
        task.reason = why
        tasks.move(session, task, TaskState.KILLED, actor.caller, now, {"why": why})
    return len(rows)


async def cut(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    requirement: Requirement,
    reason: str,
    now: datetime,
) -> int:
    """PLN-1, 7.2: cut accepted scope, with a reason. Its open tasks are killed. Returns
    how many were."""
    check_open(project)
    await authority.require_scope_change(session, settings, project, actor, requirement, "cut it")
    _reason(reason)
    requirement.reason = reason.strip()
    move(session, requirement, R.CUT, actor.caller, now, {"reason": reason.strip()})
    killed = await kill_open_tasks(
        session, requirement, actor, now, f"Requirement {requirement.id} was cut."
    )
    await scope_changed(session, settings, project, now)
    return killed


async def reopen(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    requirement: Requirement,
    now: datetime,
) -> None:
    """PLN-1, 7.2: reopen a met or cut requirement. The chairman may reopen any; the CEO a
    CEO-authored one, with scope authority."""
    check_open(project)
    await authority.require_scope_change(
        session, settings, project, actor, requirement, "reopen it"
    )
    if requirement.state not in (R.MET, R.CUT):
        raise Refusal(
            "not_met_or_cut",
            f"Requirement {requirement.id} is {requirement.state}. Only a met or cut "
            "requirement is reopened.",
            rule=PLN_1.id,
        )
    if not actor.is_chairman:
        await _check_new_scope(session, settings, project, now)
        fit = await estimates.fits_budget(
            session, settings, project, now, including=requirement.estimate_runs or 0
        )
        if not fit.fits:
            raise Refusal(
                "does_not_fit_budget",
                f"Reopening requirement {requirement.id} does not fit the budget. {fit.arithmetic}",
                rule=PLN_3.id,
                hint="Ask the chairman to reopen it or to raise the budget.",
            )
    requirement.failures, requirement.escalated, requirement.met_at = 0, False, None
    move(session, requirement, R.ACCEPTED, actor.caller, now, {"reopened": True})
    await scope_changed(session, settings, project, now)


@dataclass(frozen=True)
class Change:
    text: str | None = None
    success_test: str | None = None
    estimate_runs: int | None = None
    stage: int | None = None
    depends_on: list[int] | None = None


async def change(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    requirement: Requirement,
    wanted: Change,
    now: datetime,
) -> None:
    """PLN-1, P7: reword, re-estimate, restage or re-link a requirement. A CEO-authored
    one needs scope authority; a chairman-authored one is the chairman's, except that the
    CEO gives the first estimate when the chairman gave none."""
    check_open(project)
    if requirement.state not in (R.PROPOSED, *OPEN_SCOPE):
        raise Refusal(
            "requirement_settled",
            f"Requirement {requirement.id} is {requirement.state}; reopen it to change it.",
            rule=PLN_1.id,
        )
    first_estimate = (
        requirement.estimate_runs is None
        and wanted.estimate_runs is not None
        and wanted == Change(estimate_runs=wanted.estimate_runs)
    )
    own_proposal = (
        requirement.state == R.PROPOSED and requirement.author_kind == CEO and actor.kind == CEO
    )
    if not (first_estimate or own_proposal):
        await authority.require_scope_change(
            session, settings, project, actor, requirement, "change it"
        )
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for name in ("text", "success_test", "estimate_runs", "stage"):
        value = getattr(wanted, name)
        if value is not None and value != getattr(requirement, name):
            before[name], after[name] = getattr(requirement, name), value
            setattr(requirement, name, value)
    if wanted.depends_on is not None:
        known = await dependency_graph(session, project.id)
        had = sorted(known.get(requirement.id, set()))
        for row in await session.scalars(
            select(RequirementDependency).where(
                RequirementDependency.requirement_id == requirement.id,
                RequirementDependency.depends_on.not_in(wanted.depends_on),
            )
        ):
            await session.delete(row)
        await session.flush()
        await _add_dependencies(session, requirement, wanted.depends_on)
        if had != sorted(set(wanted.depends_on)):
            before["depends_on"], after["depends_on"] = had, sorted(set(wanted.depends_on))
    if after:
        append_event(
            session,
            type=REQUIREMENT_EDITED,
            caller=actor.caller,
            at=now,
            subject=("requirement", str(requirement.id)),
            project_id=project.id,
            before=before,
            after=after,
        )
        await scope_changed(session, settings, project, now)


__all__ = ["CEO", "CHAIRMAN", "Change", "NewRequirement"]
