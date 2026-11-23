"""What agents do with tasks through the agent API (IF-6.3, WRK-1 to WRK-9, WRK-14).

Every rule is in `tasks`, `checks` and `reviews`; these are the operations over them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.domain.execution import notices
from crewmind.domain.execution.agent import AgentView, agent_of
from crewmind.domain.execution.agent_operations import work_run_only
from crewmind.domain.execution.model import SeatKind
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import readiness
from crewmind.domain.work import checks, reviews, tasks
from crewmind.domain.work.model import NOT_YET_CHECKED, OPEN_STATES, Audience, TaskState, TestKind
from crewmind.domain.work.tasks import T
from crewmind.runner.check_sandbox import CHECK_SECONDS_LIMIT
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import Review, Seat, Suggestion, Task, TaskAttempt

AGENT = frozenset({Principal.AGENT_RUN})
SUGGESTED = event_type("suggestion.made", "An agent suggested work to the CEO (WRK-2).")


class TaskInput(BaseModel):
    title: str = Field(min_length=4, max_length=300, description="What the task is, in a line.")
    goal: str = Field(min_length=10, max_length=10_000, description="What must be achieved.")
    success_test: str = Field(
        max_length=4000,
        description="A command that exits 0 when the work is done, or what a reviewer will see.",
    )
    test_kind: TestKind = Field(description="command (the platform runs it) or observable.")
    test_files: list[str] = Field(
        default_factory=list[str],
        description="For a command test: the workspace files the command uses. They are pinned.",
    )
    outside_evidence: bool = Field(
        default=False, description="Whether it produces outside evidence."
    )
    audience: Audience = Field(default=Audience.TEAM, description="team, chairman or outside.")
    serves: str | None = Field(default=None, max_length=500, description="What it serves.")
    not_before: datetime | None = Field(default=None, description="Do not start before this.")


class CreateInput(TaskInput):
    requirement_id: int | None = Field(
        default=None,
        description="The accepted requirement this task serves (Deliver and Operate).",
    )
    bet_id: int | None = Field(
        default=None, description="The active bet this task serves (Explore)."
    )
    team: str | None = Field(
        default=None, description="The team whose lead claims it. Leave out in a solo project."
    )


class SubtaskInput(TaskInput):
    parent_id: int = Field(description="The task you have claimed that this is part of.")
    assignee: str = Field(description="A member of your team, by its seat name or its name.")


class TaskRef(BaseModel):
    task_id: int = Field(description="The task's id.")


class CompleteInput(TaskRef):
    evidence: str = Field(
        max_length=10_000,
        description="What shows it is done. Quote the output; 'Done' is not evidence.",
    )


class ReasonInput(TaskRef):
    reason: str = Field(max_length=2000, description="Why, in at least 10 characters.")


class ReviewInput(TaskRef):
    ok: bool = Field(description="Whether the work meets its success test.")
    notes: str = Field(max_length=4000, description="What you checked and found, 10+ characters.")


class SuggestInput(BaseModel):
    text: str = Field(min_length=10, max_length=2000, description="The work you suggest, and why.")


class TaskItem(BaseModel):
    id: int
    parent_id: int | None
    requirement_id: int | None
    bet_id: int | None
    title: str
    goal: str
    success_test: str
    test_kind: str
    state: str
    label: str = Field(description="verified, reviewed, self-reported, or not yet checked.")
    team: str | None
    claimant: str | None
    failures: int
    reason: str | None
    check_output: str | None


class Board(BaseModel):
    yours: list[TaskItem] = Field(description="What you hold or are reviewing.")
    claimable: list[TaskItem] = Field(description="Ready tasks you may claim now.")
    open: list[TaskItem] = Field(description="Every open task in the project.")
    suggestions: list[str] = Field(description="For the CEO: suggestions waiting for planning.")


async def item(context: Context, task: Task) -> TaskItem:
    from crewmind.storage.models import Team

    team = await context.session.get(Team, task.team_id) if task.team_id else None
    claimant = await context.session.get(Seat, task.claimant_id) if task.claimant_id else None
    return TaskItem(
        id=task.id,
        parent_id=task.parent_id,
        requirement_id=task.requirement_id,
        bet_id=task.bet_id,
        title=task.title,
        goal=task.goal,
        success_test=task.success_test,
        test_kind=task.test_kind,
        state=task.state,
        label=task.label or NOT_YET_CHECKED,
        team=team.name if team else None,
        claimant=claimant.name if claimant else None,
        failures=task.failures,
        reason=task.reason,
        check_output=task.check_output,
    )


async def _prepare(caller: Any, payload: TaskInput, services: Any) -> checks.Pinned | None:
    """WRK-5: before the database is touched, pin the test files and run the check once on
    the current workspace."""
    if payload.test_kind != TestKind.COMMAND:
        return None
    workspace = Path(services.data_dir) / "workspaces" / str(caller.project_id)
    return await checks.pin_and_run(
        services.checks, workspace, payload.success_test, payload.test_files, CHECK_SECONDS_LIMIT
    )


def _check_command(context: Context, payload: TaskInput) -> tuple[dict[str, str], str | None]:
    """WRK-5, WRK-7: refuse a command test that cannot fail, that already passes, whose
    files are missing, or that this host must not run. Returns the pinned files and the
    test's fingerprint."""
    if payload.test_kind != TestKind.COMMAND:
        return {}, None
    services = services_of(context)
    pinned: checks.Pinned = context.prepared
    if checks.unsafe_host(services.checks, services.allow_agent_checks_unisolated):
        raise Refusal(
            "checks_not_allowed_here",
            "This host runs agents unisolated and holds a container-runtime socket, so a "
            "command test an agent wrote is not run on it.",
            rule=checks.WRK_7.id,
            hint="Use an observable test, or ask the operator to allow agent checks.",
        )
    if checks.cannot_fail(payload.success_test) or not payload.success_test.strip():
        raise Refusal(
            "test_cannot_fail",
            "This command passes whatever the work is, so it tests nothing.",
            rule=checks.WRK_5.id,
            hint="Give a command that fails now and will pass when the work is done.",
        )
    if pinned.missing:
        raise Refusal(
            "test_files_missing",
            f"These test files are not in the workspace: {', '.join(pinned.missing)}.",
            rule=checks.WRK_5.id,
            hint="Write the test files first, then create the task.",
        )
    if pinned.first_run is not None and pinned.first_run.passed:
        raise Refusal(
            "test_passes_before_work",
            "This test passes before any work. A test must fail first, or passing it later "
            "proves nothing.",
            rule=checks.WRK_5.id,
            hint="Write a test that fails now and will pass when the work is done.",
        )
    return checks.stored(pinned, services.blobs), checks.fingerprint(
        payload.success_test, pinned.hashes
    )


async def _create(context: Context, view: AgentView, payload: TaskInput, **placed: Any) -> TaskItem:
    test_files, fingerprint = _check_command(context, payload)
    parent: Task | None = placed.pop("parent", None)
    requirement_id, bet_id = await readiness.check_task_scope(
        context.session,
        services_of(context).settings,
        view.project,
        requirement_id=placed.pop("requirement_id", None),
        bet_id=placed.pop("bet_id", None),
        parent=parent,
        now=context.now,
    )
    await tasks.check_creation(
        context.session,
        services_of(context).settings,
        view.project,
        parent=parent,
        success_test=payload.success_test,
        not_before=payload.not_before,
        outside_evidence=payload.outside_evidence,
        test_fingerprint=fingerprint,
        now=context.now,
    )
    task = tasks.new_task(
        project_id=view.project.id,
        parent_id=parent.id if parent else None,
        author_id=view.seat.id,
        title=payload.title.strip(),
        goal=payload.goal,
        test_kind=payload.test_kind,
        success_test=payload.success_test,
        test_files=test_files,
        test_fingerprint=fingerprint,
        outside_evidence=payload.outside_evidence,
        audience=payload.audience,
        serves=payload.serves,
        requirement_id=requirement_id,
        bet_id=bet_id,
        not_before=payload.not_before,
        created_at=context.now,
        **placed,
    )
    context.session.add(task)
    await context.session.flush()
    context.record(
        tasks.TASK_CHANGED,
        subject=("task", str(task.id)),
        project_id=view.project.id,
        after={"state": T.READY, "title": task.title, "test": task.test_kind},
    )
    await tasks.notify_claimable(context.session, task, context.now)
    return await item(context, task)


@operation(
    "agent.create_task",
    summary="Create a top-level task for a team. Its test must fail now and pass when done.",
    authority=Authority.AGENT_CEO,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
    prepare=_prepare,
)
async def create_task(context: Context, payload: CreateInput) -> TaskItem:
    """WRK-1, WRK-2, WRK-3, WRK-5: only the CEO creates top-level tasks, with no assignee;
    the team's lead claims them."""
    view = await agent_of(context)
    work_run_only(view)
    team_id: str | None = None
    if payload.team is not None:
        team_id = (await tasks.team_named(context.session, view.project.id, payload.team)).id
    elif not await tasks.is_solo(context.session, view.project.id):
        raise Refusal(
            "task_needs_a_team",
            "Name the team whose lead will claim this task.",
            rule=tasks.WRK_2.id,
            hint="Give `team`. Only a project with no team leaves it out.",
        )
    return await _create(
        context,
        view,
        payload,
        team_id=team_id,
        requirement_id=payload.requirement_id,
        bet_id=payload.bet_id,
    )


@operation(
    "agent.create_subtask",
    summary="Split a task you have claimed: create a subtask for a member of your team.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
    prepare=_prepare,
)
async def create_subtask(context: Context, payload: SubtaskInput) -> TaskItem:
    """WRK-2: only a team's lead creates subtasks, under a parent it has claimed, for a
    member of its own team, one level deep."""
    view = await agent_of(context)
    work_run_only(view)
    parent = await tasks.get(context.session, view.project.id, payload.parent_id)
    mine = parent.claimant_id == view.seat.id and parent.state == T.CLAIMED
    if not (view.seat.is_lead and mine) or parent.parent_id is not None:
        raise Refusal(
            "not_your_task_to_split",
            "Only a team's lead creates subtasks, under a top-level task it has claimed.",
            rule=tasks.WRK_2.id,
            hint="Claim the task first, or suggest the work to the CEO.",
        )
    assignee = await context.session.scalar(
        select(Seat).where(
            Seat.project_id == view.project.id,
            or_(Seat.name == payload.assignee, Seat.display_name == payload.assignee),
            Seat.team_id == view.seat.team_id,
            Seat.state == "active",
        )
    )
    if assignee is None:
        raise Refusal(
            "assignee_not_in_your_team",
            f"{payload.assignee} is not an active member of your team.",
            rule=tasks.WRK_2.id,
            hint="Assign the subtask to a member of your own team.",
        )
    return await _create(
        context, view, payload, parent=parent, team_id=view.seat.team_id, assignee_id=assignee.id
    )


@operation(
    "agent.claim_task",
    summary="Claim a ready task that is yours to do. You hold one task at a time.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def claim_task(context: Context, payload: TaskRef) -> TaskItem:
    """WRK-4, INV-3."""
    view = await agent_of(context)
    work_run_only(view)
    task = await tasks.get(context.session, view.project.id, payload.task_id)
    await tasks.check_claim(context.session, task, view.seat, context.now)
    task.claimant_id, task.claimed_at, task.reserved_for = view.seat.id, context.now, None
    tasks.move(context.session, task, T.CLAIMED, context.caller, context.now)
    await readiness.task_claimed(context.session, task, context.now)
    return await item(context, task)


@operation(
    "agent.complete_task",
    summary="Say a task you hold is done, with evidence. A check or a reviewer then decides.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def complete_task(context: Context, payload: CompleteInput) -> TaskItem:
    """WRK-6, INV-2, INV-3, P5: only the claimant completes, only with evidence, and only
    once no subtask is open. Completion never closes a task that someone else can check:
    a command test goes to the platform's check and an observable one to review."""
    view = await agent_of(context)
    work_run_only(view)
    task = await tasks.get(context.session, view.project.id, payload.task_id)
    if task.claimant_id != view.seat.id or task.state != T.CLAIMED:
        raise Refusal(
            "not_your_task",
            f"Only the agent holding task {task.id} can complete it.",
            rule=tasks.WRK_6.id,
            hint="Complete a task you have claimed.",
        )
    if tasks.non_blank(payload.evidence) < tasks.COMPLETION_MIN_CHARACTERS:
        raise Refusal(
            "evidence_too_thin",
            "'Done' is not evidence. Quote the output.",
            rule=tasks.WRK_6.id,
            hint="Say what you ran or produced and what it showed.",
        )
    if await tasks.open_tasks(context.session, view.project.id, task.id):
        raise Refusal(
            "subtasks_open",
            f"Task {task.id} still has open subtasks.",
            rule=tasks.WRK_6.id,
            hint="Wait for them to close, or kill the ones no longer needed.",
        )
    task.completion_evidence = payload.evidence
    context.session.add(
        TaskAttempt(
            task_id=task.id, seat_id=view.seat.id, evidence=payload.evidence, at=context.now
        )
    )
    await context.session.flush()
    await tasks.keep_recent_attempts(context.session, task)
    if tasks.needs_check(task):
        tasks.move(context.session, task, T.CHECKING, context.caller, context.now)
    else:
        await reviews.request(
            context.session,
            services_of(context).settings,
            view.project,
            task,
            context.caller,
            context.now,
        )
    return await item(context, task)


@operation(
    "agent.block_task",
    summary="Say a task you hold cannot be finished, and why. The CEO re-plans.",
    authority=Authority.AGENT,
    reversibility=Reversibility.IRREVERSIBLE,
    principals=AGENT,
)
async def block_task(context: Context, payload: ReasonInput) -> TaskItem:
    """WRK-14: only the claimant blocks, with a reason. There is no unblock."""
    view = await agent_of(context)
    work_run_only(view)
    task = await tasks.get(context.session, view.project.id, payload.task_id)
    if task.claimant_id != view.seat.id or task.state != T.CLAIMED:
        raise Refusal(
            "not_your_task",
            f"Only the agent holding task {task.id} can block it.",
            rule=tasks.WRK_14.id,
            hint="Block a task you have claimed.",
        )
    _reason(payload.reason)
    task.reason, task.claimant_id = payload.reason, None
    tasks.move(context.session, task, T.BLOCKED, context.caller, context.now)
    ceo = await ceo_of(context.session, view.project.id)
    notices.notify(
        context.session,
        view.project.id,
        ceo.id,
        "task blocked",
        f"{view.seat.name} blocked task {task.id} ({task.title}): {payload.reason}\n"
        "There is no unblock. Kill it and issue the work again if it is still needed.",
        context.now,
        urgent=True,
    )
    return await item(context, task)


def _reason(reason: str) -> None:
    if tasks.non_blank(reason) < tasks.REASON_MIN_CHARACTERS:
        raise Refusal(
            "reason_too_short",
            f"Give a reason of at least {tasks.REASON_MIN_CHARACTERS} characters.",
            rule=tasks.WRK_14.id,
            hint="Say what is in the way, so the plan can change.",
        )


@operation(
    "agent.kill_task",
    summary="Kill a task that is no longer needed, with a reason.",
    authority=Authority.AGENT,
    reversibility=Reversibility.IRREVERSIBLE,
    principals=AGENT,
)
async def kill_task(context: Context, payload: ReasonInput) -> TaskItem:
    """WRK-14: the CEO kills top-level tasks; a lead kills its own subtasks."""
    view = await agent_of(context)
    work_run_only(view)
    task = await tasks.get(context.session, view.project.id, payload.task_id)
    if task.parent_id is None:
        allowed = view.seat.kind == SeatKind.CEO
    else:
        allowed = task.author_id == view.seat.id
    if not allowed:
        raise Refusal(
            "not_yours_to_kill",
            "The CEO kills top-level tasks and a lead kills its own subtasks.",
            rule=tasks.WRK_14.id,
            hint="Block your own task, or suggest the change to the CEO.",
        )
    _reason(payload.reason)
    task.reason, task.claimant_id = payload.reason, None
    tasks.move(context.session, task, T.KILLED, context.caller, context.now)
    for child in await tasks.open_tasks(context.session, view.project.id, task.id):
        if child.state in (T.READY, T.CLAIMED, T.BLOCKED):
            child.reason, child.claimant_id = f"its parent task {task.id} was killed", None
            tasks.move(context.session, child, T.KILLED, tasks.WORK_JOB, context.now)
    return await item(context, task)


@operation(
    "agent.review_task",
    summary="Give your verdict on a task you were asked to review: ok or not ok, with notes.",
    authority=Authority.AGENT,
    reversibility=Reversibility.IRREVERSIBLE,
    principals=AGENT,
)
async def review_task(context: Context, payload: ReviewInput) -> TaskItem:
    """WRK-9, INV-3: the verdict comes from the one reviewer seat asked, never from the
    author. Ok closes the task as reviewed; not ok sends it back (WRK-8)."""
    view = await agent_of(context)
    work_run_only(view)
    task = await tasks.get(context.session, view.project.id, payload.task_id)
    review = await context.session.scalar(
        select(Review).where(
            Review.task_id == task.id, Review.reviewer_id == view.seat.id, Review.ok.is_(None)
        )
    )
    own = task.claimant_id == view.seat.id or task.author_id == view.seat.id
    if review is None or task.state != T.REVIEW or own or view.seat.kind != SeatKind.REVIEWER:
        raise Refusal(
            "not_your_review",
            f"Task {task.id} is not waiting for your review."
            + (" Nobody reviews work they did or a test they wrote." if own else ""),
            rule=tasks.INV_3.id if own else reviews.WRK_9.id,
            hint="Review only the tasks you were asked to review.",
        )
    if tasks.non_blank(payload.notes) < reviews.NOTES_MIN_CHARACTERS:
        raise Refusal(
            "notes_too_short",
            f"Review notes have at least {reviews.NOTES_MIN_CHARACTERS} characters.",
            rule=reviews.WRK_9.id,
            hint="Say what you checked and what you found.",
        )
    review.ok, review.notes, review.answered_at = payload.ok, payload.notes, context.now
    if payload.ok:
        from crewmind.domain.work.model import Label

        await tasks.passed(
            context.session, task, Label.REVIEWED, payload.notes, context.now, context.caller
        )
        await reviews.consider_for_audit(
            context.session, services_of(context).settings, view.project, task, context.now
        )
    else:
        await tasks.failed(
            context.session, task, payload.notes, context.now, context.caller, what="the review"
        )
    return await item(context, task)


@operation(
    "agent.suggest",
    summary="Suggest work to the CEO. A suggestion creates no task.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def suggest(context: Context, payload: SuggestInput) -> Board:
    """WRK-2: any agent influences the backlog only through suggestions, which go to the
    CEO's next planning run."""
    view = await agent_of(context)
    row = Suggestion(
        project_id=view.project.id, seat_id=view.seat.id, text=payload.text, created_at=context.now
    )
    context.session.add(row)
    await context.session.flush()
    context.record(SUGGESTED, subject=("suggestion", str(row.id)), project_id=view.project.id)
    ceo = await ceo_of(context.session, view.project.id)
    notices.notify(
        context.session,
        view.project.id,
        ceo.id,
        "suggestion",
        f"{view.seat.name} suggests: {payload.text}",
        context.now,
    )
    return await board_of(context, view)


async def board_of(context: Context, view: AgentView) -> Board:
    session = context.session
    rows = list(
        await session.scalars(
            select(Task)
            .where(Task.project_id == view.project.id, Task.state.in_(OPEN_STATES))
            .order_by(Task.id)
        )
    )
    reviewing = set(
        await session.scalars(
            select(Review.task_id).where(Review.reviewer_id == view.seat.id, Review.ok.is_(None))
        )
    )
    yours = [t for t in rows if t.claimant_id == view.seat.id or t.id in reviewing]
    claimable: list[Task] = []
    for task in rows:
        if task.state != TaskState.READY:
            continue
        try:
            await tasks.check_claim(session, task, view.seat, context.now)
        except Refusal:
            continue
        claimable.append(task)
    waiting: list[str] = []
    if view.seat.kind == SeatKind.CEO:
        found = await session.execute(
            select(Suggestion, Seat)
            .join(Seat, Seat.id == Suggestion.seat_id)
            .where(Suggestion.project_id == view.project.id, Suggestion.handed_to_run.is_(None))
            .order_by(Suggestion.id)
        )
        waiting = [f"{seat.name}: {row.text}" for row, seat in found.all()]
    return Board(
        yours=[await item(context, t) for t in yours],
        claimable=[await item(context, t) for t in claimable],
        open=[await item(context, t) for t in rows],
        suggestions=waiting,
    )


@operation(
    "agent.board",
    summary="See the board: what you hold, what you may claim, and every open task.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def board(context: Context, payload: Empty) -> Board:
    """IF-6.3: the board, as this agent may see and act on it."""
    return await board_of(context, await agent_of(context))
