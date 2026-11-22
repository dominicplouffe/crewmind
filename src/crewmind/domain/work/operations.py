"""What people see and do about work: the board, and the chairman's audit of sampled closes
(WRK-13, WRK-15, IF-3.8). No operation lets a person create or complete a task: the
chairman steers through directives and the CEO plans (P15)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.execution import notices
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.domain.work import reviews, tasks
from crewmind.domain.work.agent_operations import TaskItem, item
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import AuditSample, Project, Seat, Task, TaskAttempt

AUDIT_SETTLED = event_type("audit.settled", "An audit sample was passed, failed or expired.")

PASSED, FAILED, NOT_REVIEWED = "passed", "failed", "not reviewed"


class TaskListInput(ProjectRef):
    state: str | None = Field(default=None, description="Only tasks in this state.")
    open_only: bool = Field(default=False, description="Leave out closed tasks.")


class TaskList(BaseModel):
    items: list[TaskItem]


class TaskRef(ProjectRef):
    task_id: int = Field(description="The task's id.")


class Attempt(BaseModel):
    by: str
    evidence: str
    result: str = Field(description="passed, failed, or not yet checked.")
    output: str | None
    at: datetime


class TaskDetail(TaskItem):
    author: str
    audience: str
    serves: str | None
    outside_evidence: bool
    test_files: list[str]
    completion_evidence: str | None
    attempts: list[Attempt]
    audit: str | None = Field(
        default=None,
        description="If this close was drawn for the chairman's audit: waiting, passed, "
        "failed or not reviewed.",
    )
    created_at: datetime
    closed_at: datetime | None


class AuditItem(BaseModel):
    id: int
    task_id: int
    title: str
    label: str
    evidence: str | None
    verdict: str | None = Field(description="passed, failed, not reviewed, or waiting for you.")
    expires_at: datetime | None


class AuditList(BaseModel):
    items: list[AuditItem]
    considered: int = Field(description="Observable closes considered so far.")
    drawn: int = Field(description="How many of them were drawn for you.")


class AuditVerdictInput(ProjectRef):
    audit_id: int = Field(description="The sample's id, from `audits list`.")
    verdict: Literal["passed", "failed"] = Field(description="passed or failed.")
    note: str | None = Field(default=None, max_length=2000, description="What you found.")


@operation(
    "tasks.list",
    summary="List a project's tasks with their states and honest labels.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_tasks(context: Context, payload: TaskListInput) -> TaskList:
    """WRK-15: "verified" appears only where the platform ran the test, "reviewed" where an
    independent reviewer passed it, "self-reported" where nobody checked."""
    wanted = select(Task).where(Task.project_id == payload.project_id)
    if payload.state is not None:
        wanted = wanted.where(Task.state == payload.state)
    if payload.open_only:
        wanted = wanted.where(Task.state.in_(tasks.OPEN_STATES))
    rows = await context.session.scalars(wanted.order_by(Task.id))
    return TaskList(items=[await item(context, row) for row in rows])


@operation(
    "tasks.show",
    summary="Show one task: its test, its attempts and who checked it.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_task(context: Context, payload: TaskRef) -> TaskDetail:
    task = await tasks.get(context.session, payload.project_id, payload.task_id)
    author = await context.session.get(Seat, task.author_id)
    rows = await context.session.execute(
        select(TaskAttempt, Seat)
        .join(Seat, Seat.id == TaskAttempt.seat_id)
        .where(TaskAttempt.task_id == task.id)
        .order_by(TaskAttempt.id)
    )
    words = {True: "passed", False: "failed", None: "not yet checked"}
    sample = await context.session.scalar(
        select(AuditSample).where(AuditSample.task_id == task.id, AuditSample.drawn)
    )
    return TaskDetail(
        audit=(sample.verdict or "waiting") if sample else None,
        **(await item(context, task)).model_dump(),
        author=author.name if author else "",
        audience=task.audience,
        serves=task.serves,
        outside_evidence=task.outside_evidence,
        test_files=sorted(task.test_files),
        completion_evidence=task.completion_evidence,
        attempts=[
            Attempt(
                by=seat.name,
                evidence=row.evidence,
                result=words[row.passed],
                output=row.output,
                at=row.at,
            )
            for row, seat in rows.all()
        ],
        created_at=task.created_at,
        closed_at=task.closed_at,
    )


def _audit_item(sample: AuditSample, task: Task) -> AuditItem:
    return AuditItem(
        id=sample.id,
        task_id=task.id,
        title=task.title,
        label=task.label or "",
        evidence=task.completion_evidence,
        verdict=sample.verdict,
        expires_at=sample.expires_at,
    )


@operation(
    "audits.list",
    summary="List the closes drawn for your audit, and how many were considered.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_audits(context: Context, payload: ProjectRef) -> AuditList:
    """WRK-13: every observable close considered is recorded as drawn or skipped."""
    rows = (
        await context.session.execute(
            select(AuditSample, Task)
            .join(Task, Task.id == AuditSample.task_id)
            .where(AuditSample.project_id == payload.project_id)
            .order_by(AuditSample.id)
        )
    ).all()
    drawn = [(sample, task) for sample, task in rows if sample.drawn]
    return AuditList(
        items=[_audit_item(sample, task) for sample, task in drawn],
        considered=len(rows),
        drawn=len(drawn),
    )


@operation(
    "audits.settle",
    summary="Pass or fail a close that was drawn for your audit.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def settle_audit(context: Context, payload: AuditVerdictInput) -> AuditItem:
    """WRK-13: only the chairman passes or fails a sample, once, within `audit.window`. A
    failure reopens nothing: it is recorded and the CEO gets an urgent notice."""
    sample = await context.session.get(AuditSample, payload.audit_id)
    if sample is None or sample.project_id != payload.project_id or not sample.drawn:
        raise Refusal(
            "audit_not_found",
            f"There is no audit sample {payload.audit_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            rule=reviews.WRK_13.id,
            hint="List them with `audits list`.",
        )
    if sample.verdict is not None:
        raise Refusal(
            "audit_already_settled",
            f"Audit sample {sample.id} is already {sample.verdict}.",
            rule=reviews.WRK_13.id,
            hint="Each sample is judged once.",
        )
    sample.verdict, sample.note = payload.verdict, payload.note
    task = await context.session.get(Task, sample.task_id)
    assert task is not None
    context.record(
        AUDIT_SETTLED,
        subject=("audit_sample", str(sample.id)),
        project_id=payload.project_id,
        after={"verdict": payload.verdict, "task": task.id},
    )
    if payload.verdict == FAILED:
        ceo = await ceo_of(context.session, payload.project_id)
        notices.notify(
            context.session,
            payload.project_id,
            ceo.id,
            "audit failed",
            f"The chairman audited task {task.id} ({task.title}), which closed as "
            f"{task.label}, and failed it"
            + (f": {payload.note}" if payload.note else ".")
            + " The task stays closed. Find what went wrong and what must be redone.",
            context.now,
            urgent=True,
        )
    return _audit_item(sample, task)


async def expire_audits(session: AsyncSession, project: Project, now: datetime) -> None:
    """WRK-13: a sample the chairman has not judged within `audit.window` expires as "not
    reviewed"."""
    rows = await session.scalars(
        select(AuditSample).where(
            AuditSample.project_id == project.id,
            AuditSample.drawn,
            AuditSample.verdict.is_(None),
            AuditSample.expires_at <= now,
        )
    )
    for sample in rows:
        sample.verdict = NOT_REVIEWED
        append_event(
            session,
            type=AUDIT_SETTLED,
            caller=tasks.WORK_JOB,
            at=now,
            subject=("audit_sample", str(sample.id)),
            project_id=project.id,
            after={"verdict": NOT_REVIEWED},
        )
