"""Requirement acceptance (PLN-10): the platform moves a requirement to checking, and
writes it met on a passing command test or a passing verdict. Nobody else writes met."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller
from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.decisions import items
from nightsquad.domain.execution import notices, roster
from nightsquad.domain.execution.model import SeatKind, SeatState
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.planning import authority, estimates
from nightsquad.domain.planning.model import RequirementState, RequirementTest
from nightsquad.domain.planning.readiness import PLANNING_JOB, move
from nightsquad.domain.planning.rules import PLN_10
from nightsquad.domain.settings.service import SettingsService
from nightsquad.domain.work.model import OPEN_STATES, TaskState
from nightsquad.storage.models import ArtifactVersion, Project, Requirement, Seat, Task

R = RequirementState
ESCALATE_AFTER = 3  # PLN-10: escalation to the CEO once after 3 failures
NOTE_MIN_CHARACTERS = 10  # PLN-10: a rejection needs a note
PASSED, FAILED = "passed", "failed"
HANDED_OVER = "to a reviewer"
"""A requirement whose verdict passed from the chairman to a reviewer seat (HUM-2)."""
REVIEWER, CHAIRMAN = "reviewer", "chairman"


async def work_changed(session: AsyncSession, requirement: Requirement) -> bool:
    """PLN-10: every task under it is closed, at least one is done, and since the last
    ruling a task under it reached done or a file in the project changed."""
    open_tasks = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.requirement_id == requirement.id, Task.state.in_(OPEN_STATES))
    )
    if open_tasks:
        return False
    newest = await session.scalar(
        select(func.max(Task.closed_at)).where(
            Task.requirement_id == requirement.id, Task.state == TaskState.DONE
        )
    )
    if newest is None:
        return False
    if requirement.ruled_at is None or newest > requirement.ruled_at:
        return True
    snapshot = await session.scalar(
        select(func.max(ArtifactVersion.created_at)).where(
            ArtifactVersion.project_id == requirement.project_id
        )
    )
    return snapshot is not None and snapshot > requirement.ruled_at


async def verdict_holder(session: AsyncSession, settings: SettingsService, project: Project) -> str:
    """Who gives the verdict on an observable test: a reviewer seat or the chairman."""
    value = await settings.get(session, authority.subject(project), "authority.verdict")
    return CHAIRMAN if value == CHAIRMAN else REVIEWER


async def _ask_for_verdict(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    requirement: Requirement,
    now: datetime,
) -> None:
    ask = (
        f"Requirement {requirement.id} is ready for a verdict: {requirement.text}\n"
        f"It is met when: {requirement.success_test}"
    )
    if await verdict_holder(session, settings, project) == REVIEWER:
        await roster.ensure_reviewer(session, project, now)
        reviewer = await session.scalar(
            select(Seat)
            .where(
                Seat.project_id == project.id,
                Seat.kind == SeatKind.REVIEWER,
                Seat.state == SeatState.ACTIVE,
            )
            .order_by(Seat.created_at, Seat.name)
            .limit(1)
        )
        assert reviewer is not None
        notices.notify(
            session,
            project.id,
            reviewer.id,
            "verdict needed",
            f"{ask}\nLook at the work, then give your verdict with agent_rule_requirement "
            f"(requirement_id={requirement.id}).",
            now,
            urgent=True,
        )
        return
    item = await items.file(
        session,
        settings,
        project,
        "verdict",
        filer=PLANNING_JOB,
        fields={"requirement_id": requirement.id, "success_test": requirement.success_test},
        recommendation="Look at the work and pass or reject the requirement.",
        if_declined="A rejection sends it back to in progress, with your note.",
        subject=("requirement", str(requirement.id)),
        now=now,
        announce=False,
    )
    await conversation.platform_line(
        session,
        project.id,
        f"{ask}\nPass or reject it. Unanswered for 72 hours, it goes to a reviewer seat.",
        now,
        detail={"kind": "decision item", "item": item.id, "item_kind": item.kind},
    )


async def hand_to_reviewer(
    session: AsyncSession, project: Project, requirement: Requirement, now: datetime
) -> None:
    """HUM-2: a verdict the chairman did not give by its deadline passes to an independent
    reviewer seat."""
    await roster.ensure_reviewer(session, project, now)
    reviewer = await session.scalar(
        select(Seat)
        .where(
            Seat.project_id == project.id,
            Seat.kind == SeatKind.REVIEWER,
            Seat.state == SeatState.ACTIVE,
        )
        .order_by(Seat.created_at, Seat.name)
        .limit(1)
    )
    assert reviewer is not None
    requirement.ruling = HANDED_OVER
    notices.notify(
        session,
        project.id,
        reviewer.id,
        "verdict needed",
        f"The chairman did not rule on requirement {requirement.id} in time, so the "
        f"verdict is yours: {requirement.text}\nIt is met when: {requirement.success_test}\n"
        f"Give it with agent_rule_requirement (requirement_id={requirement.id}).",
        now,
        urgent=True,
    )


async def start_checking(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> list[Requirement]:
    """Move every in-progress requirement whose work is finished and has changed to
    checking. An observable one asks for its verdict. Returns those moved."""
    rows = await session.scalars(
        select(Requirement)
        .where(Requirement.project_id == project.id, Requirement.state == R.IN_PROGRESS)
        .order_by(Requirement.id)
    )
    moved: list[Requirement] = []
    for requirement in rows:
        if requirement.test_kind == RequirementTest.METRIC:
            continue
        if not await work_changed(session, requirement):
            continue
        move(session, requirement, R.CHECKING, PLANNING_JOB, now)
        requirement.ruling = None
        if requirement.test_kind == RequirementTest.OBSERVABLE:
            await _ask_for_verdict(session, settings, project, requirement, now)
        moved.append(requirement)
    return moved


async def settle(
    session: AsyncSession,
    project: Project,
    requirement: Requirement,
    passed: bool,
    note: str | None,
    now: datetime,
    *,
    by: Caller,
) -> None:
    """Write the ruling on a requirement in checking. `by` is recorded as who ruled; the
    state change itself is always the platform's (PLN-10)."""
    requirement.ruled_at = now
    requirement.ruling = PASSED if passed else FAILED
    requirement.ruling_note = note
    ceo = await ceo_of(session, project.id)
    detail: dict[str, object] = {"ruled_by": by.actor_id, "ruling": requirement.ruling}
    if passed:
        requirement.met_at = now
        requirement.actual_runs = await estimates.runs_spent(session, requirement)
        requirement.actual_tokens = await estimates.tokens_spent(session, requirement)
        move(session, requirement, R.MET, PLANNING_JOB, now, detail)
        await conversation.platform_line(
            session,
            project.id,
            f"Requirement {requirement.id} is met: {requirement.text}",
            now,
            detail={"kind": "requirement met", "requirement": requirement.id},
        )
        notices.notify(
            session,
            project.id,
            ceo.id,
            "requirement met",
            f"Requirement {requirement.id} is met: {requirement.text}",
            now,
            urgent=True,
        )
        for hook in met_hooks:
            await hook(session, project, requirement, now)
        return
    requirement.failures += 1
    move(session, requirement, R.IN_PROGRESS, PLANNING_JOB, now, detail)
    body = (
        f"Requirement {requirement.id} is not met ({requirement.failures} "
        f"failure{'s' if requirement.failures != 1 else ''}): {note or 'the test failed'}\n"
        "It is checked again when more work under it is done."
    )
    escalate = requirement.failures >= ESCALATE_AFTER and not requirement.escalated
    if escalate:
        requirement.escalated = True
        body += (
            f"\nIt has now failed {requirement.failures} times. Change the approach, the "
            "requirement or its test."
        )
        await conversation.platform_line(
            session,
            project.id,
            f"Requirement {requirement.id} has failed its test {requirement.failures} "
            "times. The CEO has been told to change course.",
            now,
            detail={"kind": "requirement failing", "requirement": requirement.id},
        )
    notices.notify(session, project.id, ceo.id, "requirement not met", body, now, urgent=True)


met_hooks: list[Any] = []
"""Called as `(session, project, requirement, now)` when a requirement is met."""


async def rule(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    requirement: Requirement,
    *,
    passed: bool,
    note: str | None,
    by: Caller,
    holder: str,
    now: datetime,
) -> None:
    """PLN-10, P5: a verdict on an observable requirement, from whoever holds verdict
    authority. The chairman may always rule. A rejection needs a note."""
    if requirement.state != R.CHECKING or requirement.test_kind != RequirementTest.OBSERVABLE:
        raise Refusal(
            "no_verdict_wanted",
            f"Requirement {requirement.id} is {requirement.state}. A verdict is given only "
            "on an observable requirement in checking.",
            rule=PLN_10.id,
        )
    handed_over = requirement.ruling == HANDED_OVER
    if (
        holder != CHAIRMAN
        and not handed_over
        and await verdict_holder(session, settings, project) != holder
    ):
        raise Refusal(
            "verdict_is_the_chairmans",
            "In this project the chairman gives the verdict on requirements "
            "(`authority.verdict` is chairman).",
            rule=PLN_10.id,
        )
    if not passed and len((note or "").strip()) < NOTE_MIN_CHARACTERS:
        raise Refusal(
            "rejection_needs_a_note",
            f"A rejection needs a note of at least {NOTE_MIN_CHARACTERS} characters saying "
            "what is missing.",
            rule=PLN_10.id,
        )
    await items.settle(
        session, "verdict", ("requirement", str(requirement.id)),
        "pass" if passed else "reject", by, now,
    )  # fmt: skip
    await settle(session, project, requirement, passed, (note or "").strip() or None, now, by=by)
