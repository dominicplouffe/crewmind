"""Tasks: who creates them, the ceilings, claiming, completing, and the failure loop
(WRK-1 to WRK-4, WRK-6, WRK-8, WRK-14, INV-2, INV-3, INV-16, section 7.3).

Nothing here lets the doer say the work is done. Completion only routes a task to the
platform's check or to another agent's review; those, not the claimant, close it (P5).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller, platform_job
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.state_machine import NEW
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.model import LIVE_STATES, SeatKind, SeatState
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.integrations import push
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import SettingsService, Subject
from nightsquad.domain.work.model import (
    ATTEMPTS_KEPT,
    MAX_FAILURES,
    OPEN_STATES,
    TASK_MACHINE,
    Label,
    TaskState,
    TestKind,
)
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import Evidence, Project, Run, Seat, Task, TaskAttempt, Team

WRK_2 = rules.register(Rule("WRK-2", "Only the CEO creates tasks; only a lead creates subtasks."))
WRK_3 = rules.register(Rule("WRK-3", "Task creation stays within its ceilings and floors."))
WRK_4 = rules.register(Rule("WRK-4", "A task is claimed by its lead or assignee, one at a time."))
WRK_6 = rules.register(Rule("WRK-6", "Only the claimant completes, with evidence."))
WRK_8 = rules.register(Rule("WRK-8", "Three failures block a task."))
WRK_14 = rules.register(Rule("WRK-14", "Only the claimant blocks; the CEO or the lead kills."))
INV_3 = rules.register(Rule("INV-3", "No agent grades its own work or claims its own test."))
INV_16 = rules.register(Rule("INV-16", "A claimed task has a live run or a path back to ready."))

TASK_CHANGED = event_type("task.state_changed", "A task changed state (7.3).")
WORK_JOB = platform_job("work: checks and claims")

T = TaskState
TEST_MIN_CHARACTERS = 15  # WRK-3
NOT_BEFORE_MOST = timedelta(hours=6)  # WRK-3
SUSPECT_AFTER = 2  # WRK-3: the check is the suspect once it has blocked or killed 2 tasks
EVIDENCE_SHARE_FROM = 3  # WRK-3: the evidence share applies once 3 tasks are open
REASON_MIN_CHARACTERS = 10  # WRK-14
COMPLETION_MIN_CHARACTERS = 10  # WRK-6
CLAIM_EXPIRY_TIMEOUTS = 2  # WRK-4: a claim with no live run for 2 x `run.timeout`


def subject(project: Project) -> Subject:
    return Subject(Scope.PROJECT, project.id, project.type)


def move(
    session: AsyncSession,
    task: Task,
    target: TaskState,
    caller: Caller,
    now: datetime,
    detail: dict[str, Any] | None = None,
) -> None:
    """The one place a task changes state. A transition not in section 7.3 is refused."""
    TASK_MACHINE.check(task.state, target)
    before = task.state
    task.state = target
    if target in (T.DONE, T.KILLED, T.CLOSED_UNREAD):
        task.closed_at = now
    append_event(
        session,
        type=TASK_CHANGED,
        caller=caller,
        at=now,
        subject=("task", str(task.id)),
        project_id=task.project_id,
        before={"state": before},
        after={"state": target, "label": task.label},
        detail=detail,
    )


async def workers(session: AsyncSession, project_id: str) -> list[Seat]:
    """The active agents that do work besides the CEO: leads and workers."""
    rows = await session.scalars(
        select(Seat).where(
            Seat.project_id == project_id,
            Seat.state == SeatState.ACTIVE,
            Seat.kind.in_([SeatKind.LEAD, SeatKind.WORKER]),
        )
    )
    return list(rows)


async def is_solo(session: AsyncSession, project_id: str) -> bool:
    """Section 3: a solo project is one where a single agent plans and does the work."""
    return not await workers(session, project_id)


async def get(session: AsyncSession, project_id: str, task_id: int) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise Refusal(
            "task_not_found",
            f"There is no task {task_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            hint="Look at the board for the tasks that exist.",
        )
    return task


async def open_tasks(session: AsyncSession, project_id: str, parent_id: int | None) -> list[Task]:
    wanted = select(Task).where(Task.project_id == project_id, Task.state.in_(OPEN_STATES))
    wanted = wanted.where(
        Task.parent_id.is_(None) if parent_id is None else Task.parent_id == parent_id
    )
    return list(await session.scalars(wanted.order_by(Task.id)))


async def check_creation(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    *,
    parent: Task | None,
    success_test: str,
    not_before: datetime | None,
    outside_evidence: bool,
    test_fingerprint: str | None,
    now: datetime,
) -> None:
    """WRK-3: the ceilings and floors every new task meets, whoever creates it."""
    values = await settings.effective(session, subject(project))
    siblings = await open_tasks(session, project.id, parent.id if parent else None)
    limit = int(values["tasks.max_subtasks" if parent else "tasks.max_open"])
    if len(siblings) >= limit:
        what = f"subtasks under task {parent.id}" if parent else "top-level tasks"
        name = "tasks.max_subtasks" if parent else "tasks.max_open"
        raise Refusal(
            "too_many_open_tasks",
            f"{len(siblings)} {what} are open and `{name}` is {limit}.",
            rule=WRK_3.id,
            hint="Finish or kill an open one first.",
        )
    if len(success_test.strip()) < TEST_MIN_CHARACTERS:
        raise Refusal(
            "success_test_too_short",
            f"A success test has at least {TEST_MIN_CHARACTERS} characters, so that someone "
            "else can tell whether the work is done.",
            rule=WRK_3.id,
            hint="Say what will be true, or give the command that shows it.",
        )
    if not_before is not None and not_before > now + NOT_BEFORE_MOST:
        raise Refusal(
            "not_before_too_far",
            "A not-before time is at most 6 hours ahead.",
            rule=WRK_3.id,
            hint="Create the task closer to when it can start.",
        )
    if test_fingerprint is not None:
        dead = await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.project_id == project.id,
                Task.test_fingerprint == test_fingerprint,
                Task.state.in_([T.BLOCKED, T.KILLED]),
            )
        )
        if (dead or 0) >= SUSPECT_AFTER:
            raise Refusal(
                "check_is_the_suspect",
                f"This command test has already blocked or killed {dead} tasks. The check is "
                "the suspect.",
                rule=WRK_3.id,
                hint="Fix or replace the test before issuing the work again.",
            )
    if project.type == "explore" and parent is None and not outside_evidence:
        window = timedelta(seconds=int(values["evidence.drought_after"]))
        verified = await session.scalar(
            select(func.max(Evidence.settled_at)).where(
                Evidence.project_id == project.id, Evidence.state == "verified"
            )
        )
        if now - max(filter(None, [verified, project.created_at]), default=now) >= window:
            raise Refusal(
                "evidence_drought",
                f"No outside evidence has been verified for {int(window.total_seconds() // 3600)} "
                "hours (`evidence.drought_after`). Until some is, only tasks that produce "
                "outside evidence may be created.",
                rule=WRK_3.id,
                hint="Create a task that goes and gets evidence from outside.",
            )
        open_now = [*siblings]
        if len(open_now) + 1 >= EVIDENCE_SHARE_FROM:
            share = int(values["evidence.min_share"])
            producing = sum(1 for task in open_now if task.outside_evidence)
            if producing * 100 < share * (len(open_now) + 1):
                raise Refusal(
                    "too_little_outside_evidence",
                    f"With this task, {producing} of {len(open_now) + 1} open tasks would "
                    f"produce outside evidence, and `evidence.min_share` is {share}%.",
                    rule=WRK_3.id,
                    hint="Create a task that produces outside evidence first.",
                )


async def notify_claimable(session: AsyncSession, task: Task, now: datetime) -> None:
    """Wake whoever may claim a ready task (EXE-2)."""
    seat_id = task.reserved_for or task.assignee_id
    if seat_id is None:
        if task.team_id is not None:
            lead = await session.scalar(
                select(Seat).where(
                    Seat.team_id == task.team_id, Seat.is_lead, Seat.state == SeatState.ACTIVE
                )
            )
            seat_id = lead.id if lead else None
        else:
            seat_id = (await ceo_of(session, task.project_id)).id
    if seat_id is not None:
        notices.notify(
            session,
            task.project_id,
            seat_id,
            "task ready",
            f"Task {task.id} is ready for you to claim: {task.title}",
            now,
            urgent=True,
        )


async def held_by(session: AsyncSession, seat_id: str) -> Task | None:
    return await session.scalar(
        select(Task).where(Task.claimant_id == seat_id, Task.state == T.CLAIMED).limit(1)
    )


async def check_claim(session: AsyncSession, task: Task, seat: Seat, now: datetime) -> None:
    """WRK-4, INV-3: who may claim, when, and never one's own test while others could."""
    if task.state != T.READY:
        raise Refusal(
            "task_not_ready",
            f"Task {task.id} is {task.state}; only a ready task can be claimed.",
            rule=WRK_4.id,
            hint="Look at the board for tasks that are ready.",
        )
    if task.not_before is not None and now < task.not_before:
        raise Refusal(
            "task_not_yet",
            f"Task {task.id} cannot start before {task.not_before:%H:%M} UTC.",
            rule=WRK_4.id,
            hint="Claim it after that time.",
        )
    if task.reserved_for is not None and task.reserved_for != seat.id:
        holder = await session.get(Seat, task.reserved_for)
        if holder is not None and holder.state == SeatState.ACTIVE:
            raise Refusal(
                "task_reserved",
                f"Task {task.id} came back from a failed check and is reserved for {holder.name}.",
                rule=WRK_4.id,
                hint="Leave it for them.",
            )
    if task.parent_id is not None:
        allowed = task.assignee_id == seat.id
        who = "the agent it is assigned to"
    elif task.team_id is not None:
        allowed = seat.team_id == task.team_id and seat.is_lead
        who = "the lead of its team"
    else:
        allowed = seat.kind == SeatKind.CEO
        who = "the CEO, in a project with no team"
    if not allowed:
        raise Refusal(
            "not_yours_to_claim",
            f"Task {task.id} can be claimed only by {who}.",
            rule=WRK_4.id,
            hint="Claim a task that is yours, or suggest one to the CEO.",
        )
    if task.author_id == seat.id and not await is_solo(session, task.project_id):
        raise Refusal(
            "own_test",
            f"You wrote the success test of task {task.id}, so you cannot do the work while "
            "another agent could.",
            rule=INV_3.id,
            hint="Leave it to its team.",
        )
    other = await held_by(session, seat.id)
    if other is not None:
        raise Refusal(
            "one_item_at_a_time",
            f"You hold task {other.id} ({other.title}). An agent holds one item at a time.",
            rule=WRK_4.id,
            hint="Complete or block it first.",
        )


def non_blank(text: str) -> int:
    return len("".join(text.split()))


async def keep_recent_attempts(session: AsyncSession, task: Task) -> None:
    """WRK-1: a task keeps its last 5 attempts."""
    rows = list(
        await session.scalars(
            select(TaskAttempt)
            .where(TaskAttempt.task_id == task.id)
            .order_by(TaskAttempt.id.desc())
        )
    )
    for old in rows[ATTEMPTS_KEPT:]:
        await session.delete(old)


async def attempt_history(session: AsyncSession, task: Task) -> str:
    """The attempts so far, as the claimant is shown them (WRK-8)."""
    rows = list(
        await session.scalars(
            select(TaskAttempt).where(TaskAttempt.task_id == task.id).order_by(TaskAttempt.id)
        )
    )
    words = {True: "passed", False: "failed", None: "not yet checked"}
    lines = [
        f"  attempt {index}: {words[row.passed]}"
        + (f" - {row.output.strip()[-300:]}" if row.output else "")
        for index, row in enumerate(rows, start=1)
    ]
    return "\n".join(lines)


async def passed(
    session: AsyncSession,
    task: Task,
    label: Label,
    output: str | None,
    now: datetime,
    caller: Caller,
) -> None:
    """Close a task as done, with the label that says who checked it (WRK-15)."""
    task.label = label
    task.check_output = output if output is not None else task.check_output
    task.failures = 0
    last = await session.scalar(
        select(TaskAttempt)
        .where(TaskAttempt.task_id == task.id)
        .order_by(TaskAttempt.id.desc())
        .limit(1)
    )
    if last is not None:
        last.passed, last.output = True, output
    move(session, task, T.DONE, caller, now)
    ceo = await ceo_of(session, task.project_id)
    notices.notify(
        session,
        task.project_id,
        ceo.id,
        "task done",
        f"Task {task.id} is done ({label}): {task.title}",
        now,
    )
    if task.parent_id is not None:
        parent = await session.get(Task, task.parent_id)
        if parent is not None and parent.claimant_id and parent.state == T.CLAIMED:
            notices.notify(
                session,
                task.project_id,
                parent.claimant_id,
                "subtask done",
                f"Subtask {task.id} of your task {parent.id} is done ({label}): {task.title}",
                now,
                urgent=True,
            )


async def failed(
    session: AsyncSession, task: Task, output: str, now: datetime, caller: Caller, *, what: str
) -> None:
    """WRK-8: a failed check or a rejected review. The task goes back to ready, reserved for
    its claimant, with the attempt history. The third failure blocks it and tells the CEO;
    if the same command already killed another task, the chairman is alarmed."""
    task.failures += 1
    task.check_output = output
    last = await session.scalar(
        select(TaskAttempt)
        .where(TaskAttempt.task_id == task.id)
        .order_by(TaskAttempt.id.desc())
        .limit(1)
    )
    if last is not None:
        last.passed, last.output = False, output
    claimant = task.claimant_id
    ceo = await ceo_of(session, task.project_id)
    if task.failures >= MAX_FAILURES:
        task.reason = f"{what} failed {MAX_FAILURES} times"
        task.claimant_id = None
        move(session, task, T.BLOCKED, caller, now, {"why": task.reason})
        notices.notify(
            session,
            task.project_id,
            ceo.id,
            "task blocked",
            f"Task {task.id} ({task.title}) is blocked: {task.reason}. Last output:\n"
            f"{output.strip()[-600:]}\nKill it and issue the work again, with a better test "
            "if the test was the problem.",
            now,
            urgent=True,
        )
        if task.test_fingerprint is not None:
            earlier = await session.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.project_id == task.project_id,
                    Task.test_fingerprint == task.test_fingerprint,
                    Task.id != task.id,
                    Task.state.in_([T.BLOCKED, T.KILLED]),
                )
            )
            if earlier:
                project = await session.get(Project, task.project_id)
                assert project is not None
                body = (
                    f"Task {task.id} ({task.title}) is the second task to die on the same "
                    "check. The check itself may be wrong."
                )
                await push.raise_alarm(session, project, body, now)
                await conversation.platform_line(
                    session, project.id, body, now, detail={"kind": "check suspect", "alarm": True}
                )
        return
    task.reserved_for, task.claimant_id = claimant, None
    move(session, task, T.READY, caller, now, {"why": f"{what} failed"})
    if claimant is not None:
        notices.notify(
            session,
            task.project_id,
            claimant,
            "task returned",
            f"Task {task.id} ({task.title}) came back: {what} failed, attempt "
            f"{task.failures} of {MAX_FAILURES}. It is reserved for you; claim it again when "
            f"you hold nothing else.\n{await attempt_history(session, task)}",
            now,
            urgent=True,
        )


async def expire_claims(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> None:
    """WRK-4, INV-16: a claim with no live run behind it for 2 x `run.timeout` returns the
    task to ready, so a dead agent never strands work."""
    timeout = timedelta(seconds=int(await settings.get(session, subject(project), "run.timeout")))
    claimed = await session.scalars(
        select(Task).where(Task.project_id == project.id, Task.state == T.CLAIMED)
    )
    for task in claimed:
        assert task.claimant_id is not None
        live = await session.scalar(
            select(Run.id)
            .where(Run.seat_id == task.claimant_id, Run.state.in_(LIVE_STATES))
            .limit(1)
        )
        if live is not None:
            continue
        last_ended = await session.scalar(
            select(func.max(Run.ended_at)).where(Run.seat_id == task.claimant_id)
        )
        since = max(filter(None, [task.claimed_at, last_ended]), default=now)
        if now - since >= CLAIM_EXPIRY_TIMEOUTS * timeout:
            task.claimant_id, task.claimed_at = None, None
            move(session, task, T.READY, WORK_JOB, now, {"why": "the claim had no live run"})
            await notify_claimable(session, task, now)


async def team_named(session: AsyncSession, project_id: str, name: str) -> Team:
    team = await session.scalar(
        select(Team).where(Team.project_id == project_id, func.lower(Team.name) == name.lower())
    )
    if team is None or team.state != "active":
        raise Refusal(
            "team_not_found",
            f"There is no active team named {name}.",
            kind=RefusalKind.NOT_FOUND,
            rule=WRK_2.id,
            hint="Hire the team first, or name one that exists.",
        )
    return team


def new_task(**fields: Any) -> Task:
    TASK_MACHINE.check(NEW, T.READY)
    return Task(state=T.READY, failures=0, **fields)


def needs_check(task: Task) -> bool:
    return task.test_kind == TestKind.COMMAND
