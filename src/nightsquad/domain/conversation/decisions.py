"""Closed decisions: a topic the chairman has ruled on, and the one way to raise it again
(MSG-5, INV-26, CHAT-8, section 7.17)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import PERSON_AND_MCP, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.state_machine import NEW, StateMachine
from nightsquad.domain.conversation import service
from nightsquad.domain.conversation.service import Author
from nightsquad.domain.decisions import items
from nightsquad.domain.execution.agent import agent_of
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.memory import pinned
from nightsquad.domain.projects.access import view_of
from nightsquad.domain.projects.operations import ProjectRef
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import Subject
from nightsquad.services import services_of
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import (
    Artifact,
    ArtifactVersion,
    ClosedDecision,
    Message,
    ReopenRequest,
    Seat,
)

INV_26 = rules.register(
    Rule(
        "INV-26",
        "A closed decision is reopened only by the chairman, or on a request with newer evidence.",
    )
)
MSG_5 = rules.register(
    Rule("MSG-5", "One reopen request per decision per cooldown; only the chairman rules.")
)
DECISION_CHANGED = event_type("decision.state_changed", "A closed decision changed state.")
REOPEN_REQUESTED = event_type("decision.reopen_requested", "An agent asked to reopen a decision.")
REOPEN_ANSWERED = event_type("decision.reopen_answered", "The chairman answered a reopen request.")

TOPIC_MAX = 200


class DecisionState(StrEnum):
    CLOSED = "closed"
    REOPENED = "reopened"


D = DecisionState
DECISION_MACHINE = StateMachine(
    "closed decision",
    "7.17-decision",
    [(NEW, D.CLOSED), (D.CLOSED, D.REOPENED), (D.REOPENED, D.CLOSED)],
)


class DecideInput(ProjectRef):
    text: str = Field(
        min_length=3,
        max_length=4000,
        description="The topic, a colon, then your ruling: `Taxes: never include them`.",
    )


class DecisionRef(ProjectRef):
    decision_id: int = Field(description="The decision's id, from `decisions list`.")


class RuleInput(DecisionRef):
    ruling: str = Field(min_length=3, max_length=4000, description="Your new ruling.")


class Evidence(BaseModel):
    kind: Literal["artifact", "message"] = Field(description="artifact or message.")
    ref: str = Field(description="The artifact's name, or the message's id.")


class RequestInput(BaseModel):
    decision_id: int = Field(description="The closed decision to raise again.")
    reason: str = Field(min_length=20, max_length=2000, description="What has changed.")
    evidence: list[Evidence] = Field(
        min_length=1, description="What is new since the decision: files or people's messages."
    )


class AnswerInput(ProjectRef):
    request_id: int = Field(description="The request's id, from `decisions requests`.")
    approve: bool = Field(description="Whether to reopen the decision.")


class DecisionItem(BaseModel):
    id: int
    topic: str
    ruling: str
    state: str
    decided_at: datetime
    note: str | None = None


class DecisionList(BaseModel):
    items: list[DecisionItem]


class RequestItem(BaseModel):
    id: int
    decision_id: int
    by: str
    reason: str
    evidence: list[Evidence]
    approved: bool | None
    at: datetime


class RequestList(BaseModel):
    items: list[RequestItem]


def _item(row: ClosedDecision, note: str | None = None) -> DecisionItem:
    return DecisionItem(
        id=row.id,
        topic=row.topic,
        ruling=row.ruling,
        state=row.state,
        decided_at=row.decided_at,
        note=note,
    )


def _move(context: Context, row: ClosedDecision, target: DecisionState) -> None:
    DECISION_MACHINE.check(row.state, target)
    before = row.state
    row.state = target
    context.record(
        DECISION_CHANGED,
        subject=("decision", str(row.id)),
        project_id=row.project_id,
        before={"state": before},
        after={"state": target, "topic": row.topic, "ruling": row.ruling},
    )


async def _decision(session: AsyncSession, project_id: str, decision_id: int) -> ClosedDecision:
    row = await session.get(ClosedDecision, decision_id)
    if row is None or row.project_id != project_id:
        raise Refusal(
            "decision_not_found",
            f"There is no decision {decision_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            hint="List them with `decisions list`.",
        )
    return row


def split(text: str) -> tuple[str, str]:
    """`Topic: ruling` in the chairman's words. With no colon, the ruling is its own topic."""
    topic, separator, ruling = text.strip().partition(":")
    if not separator or not ruling.strip() or len(topic) > TOPIC_MAX:
        return text.strip()[:TOPIC_MAX], text.strip()
    return topic.strip(), ruling.strip()


@operation(
    "decisions.decide",
    summary="Close a topic with your ruling. Agents cannot raise it again without new evidence.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/decide",
)
async def decide(context: Context, payload: DecideInput) -> DecisionItem:
    """MSG-5, CHAT-8: the ruling is recorded in the chairman's words and pinned in every
    run's memory."""
    topic, ruling = split(payload.text)
    DECISION_MACHINE.check(NEW, D.CLOSED)
    row = ClosedDecision(
        project_id=payload.project_id,
        topic=topic,
        ruling=ruling,
        state=D.CLOSED,
        decided_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    context.record(
        DECISION_CHANGED,
        subject=("decision", str(row.id)),
        project_id=row.project_id,
        after={"state": D.CLOSED, "topic": topic, "ruling": ruling},
    )
    await service.platform_line(
        context.session,
        row.project_id,
        f"Decision {row.id} is closed. {topic}: {ruling}",
        context.now,
        detail={"kind": "decision closed", "decision": row.id},
    )
    project = view_of(context).project
    ceo = await ceo_of(context.session, project.id)
    note = await pinned.note_if_over(
        context.session, services_of(context).settings, project, ceo, context.now
    )
    return _item(row, note)


@operation(
    "decisions.reopen",
    summary="Reopen a closed decision. You can do this at any time.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def reopen(context: Context, payload: DecisionRef) -> DecisionItem:
    """MSG-5, INV-26: the chairman may reopen any decision at any time."""
    row = await _decision(context.session, payload.project_id, payload.decision_id)
    _move(context, row, D.REOPENED)
    row.reopened_at = context.now
    await service.platform_line(
        context.session,
        row.project_id,
        f"Decision {row.id} ({row.topic}) is open again. It binds nobody until a new ruling.",
        context.now,
        detail={"kind": "decision reopened", "decision": row.id},
    )
    return _item(row)


@operation(
    "decisions.rule",
    summary="Give a new ruling on a reopened decision, which closes it again.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def rule_again(context: Context, payload: RuleInput) -> DecisionItem:
    row = await _decision(context.session, payload.project_id, payload.decision_id)
    row.ruling = payload.ruling.strip()
    _move(context, row, D.CLOSED)
    row.decided_at = context.now
    await service.platform_line(
        context.session,
        row.project_id,
        f"Decision {row.id} is closed again. {row.topic}: {row.ruling}",
        context.now,
        detail={"kind": "decision closed", "decision": row.id},
    )
    return _item(row)


@operation(
    "decisions.list",
    summary="List a project's decisions and their rulings.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_decisions(context: Context, payload: ProjectRef) -> DecisionList:
    rows = await context.session.scalars(
        select(ClosedDecision)
        .where(ClosedDecision.project_id == payload.project_id)
        .order_by(ClosedDecision.id)
    )
    return DecisionList(items=[_item(row) for row in rows])


async def _newer(
    session: AsyncSession, project_id: str, evidence: Evidence, decided_at: datetime
) -> str | None:
    """Why this piece of evidence does not count, or None when it is newer than the
    decision. Until evidence records exist (WRK-12), evidence is a file version or a
    person's message."""
    if evidence.kind == "artifact":
        newest = await session.scalar(
            select(ArtifactVersion.created_at)
            .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
            .where(Artifact.project_id == project_id, Artifact.name == evidence.ref)
            .order_by(ArtifactVersion.version.desc())
            .limit(1)
        )
        if newest is None:
            return f"there is no file named {evidence.ref}"
        return (
            None if newest > decided_at else f"the file {evidence.ref} is older than the decision"
        )
    message = await session.get(Message, int(evidence.ref)) if evidence.ref.isdigit() else None
    if message is None or message.project_id != project_id:
        return f"there is no message {evidence.ref}"
    if message.author_kind != Author.PERSON:
        return f"message {evidence.ref} is not from a person"
    if message.created_at <= decided_at:
        return f"message {evidence.ref} is older than the decision"
    return None


@operation(
    "agent.request_reopen",
    summary="Ask the chairman to reopen a closed decision. You must link evidence newer than it.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=frozenset({Principal.AGENT_RUN}),
)
async def request_reopen(context: Context, payload: RequestInput) -> RequestItem:
    """MSG-5, INV-26: an agent raises a closed topic only by this request, only with
    evidence newer than the decision, and at most once per `decision.reopen_cooldown`."""
    view = await agent_of(context)
    row = await _decision(context.session, view.project.id, payload.decision_id)
    if row.state != D.CLOSED:
        raise Refusal(
            "decision_not_closed",
            f"Decision {row.id} is already open; there is nothing to reopen.",
            rule=INV_26.id,
            hint="Wait for the chairman's new ruling.",
        )
    stale = [
        reason
        for item in payload.evidence
        if (reason := await _newer(context.session, view.project.id, item, row.decided_at))
    ]
    if stale:
        raise Refusal(
            "no_newer_evidence",
            f"Decision {row.id} ({row.topic}) is closed, and this evidence does not count: "
            f"{'; '.join(stale)}.",
            rule=INV_26.id,
            hint="Link a file version or a person's message newer than the decision, or let "
            "the topic rest.",
        )
    subject = Subject(Scope.PROJECT, view.project.id, view.project.type)
    cooldown = timedelta(
        seconds=int(
            await services_of(context).settings.get(
                context.session, subject, "decision.reopen_cooldown"
            )
        )
    )
    last = await context.session.scalar(
        select(ReopenRequest.created_at)
        .where(ReopenRequest.decision_id == row.id)
        .order_by(ReopenRequest.id.desc())
        .limit(1)
    )
    if last is not None and context.now < last + cooldown:
        raise Refusal(
            "reopen_too_soon",
            f"A reopen request for decision {row.id} was filed on {last:%d %b %Y}. Another "
            f"may be filed from {last + cooldown:%d %b %Y}.",
            rule=MSG_5.id,
            hint="Work within the ruling until then.",
        )
    request = ReopenRequest(
        decision_id=row.id,
        project_id=view.project.id,
        seat_id=view.seat.id,
        reason=payload.reason,
        evidence=[item.model_dump() for item in payload.evidence],
        approved=None,
        created_at=context.now,
    )
    context.session.add(request)
    await context.session.flush()
    context.record(
        REOPEN_REQUESTED,
        subject=("reopen_request", str(request.id)),
        project_id=view.project.id,
        after={"decision": row.id, "by": view.seat.name},
    )
    links = ", ".join(f"{item.kind} {item.ref}" for item in payload.evidence)
    filed = await items.file(
        context.session,
        services_of(context).settings,
        view.project,
        REOPEN.name,
        filer=context.caller,
        fields={"request_id": request.id, "decision_id": row.id, "reason": payload.reason},
        recommendation="Reopen the decision only if the new evidence changes the picture.",
        if_declined="The ruling stands and the agent works within it.",
        subject=("reopen_request", str(request.id)),
        now=context.now,
        announce=False,
    )
    await service.platform_line(
        context.session,
        view.project.id,
        f"{view.seat.display_name} asks to reopen decision {row.id} ({row.topic}): "
        f"{payload.reason}\n"
        f"New evidence: {links}. Answer with `decisions answer`. The ruling stands until you do.",
        context.now,
        detail={
            "kind": "decision item",
            "item": filed.id,
            "item_kind": filed.kind,
            "request": request.id,
            "decision": row.id,
        },
    )
    return _request_item(request, view.seat.name)


def _request_item(row: ReopenRequest, by: str) -> RequestItem:
    return RequestItem(
        id=row.id,
        decision_id=row.decision_id,
        by=by,
        reason=row.reason,
        evidence=[Evidence.model_validate(item) for item in row.evidence],
        approved=row.approved,
        at=row.created_at,
    )


@operation(
    "decisions.requests",
    summary="List agents' requests to reopen decisions.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def requests(context: Context, payload: ProjectRef) -> RequestList:
    rows = await context.session.execute(
        select(ReopenRequest, Seat)
        .join(Seat, Seat.id == ReopenRequest.seat_id)
        .where(ReopenRequest.project_id == payload.project_id)
        .order_by(ReopenRequest.id)
    )
    return RequestList(items=[_request_item(row, seat.name) for row, seat in rows.all()])


@operation(
    "decisions.answer",
    summary="Approve or decline an agent's request to reopen a decision.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def answer(context: Context, payload: AnswerInput) -> DecisionItem:
    """INV-26: a request reopens nothing by itself. Only the chairman's approval does."""
    request = await context.session.get(ReopenRequest, payload.request_id)
    if request is None or request.project_id != payload.project_id:
        raise Refusal(
            "request_not_found",
            f"There is no reopen request {payload.request_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            hint="List them with `decisions requests`.",
        )
    if request.approved is not None:
        raise Refusal(
            "request_already_answered",
            f"Request {request.id} was already answered.",
            rule=MSG_5.id,
            hint="If you have changed your mind, reopen it yourself with `decisions reopen`.",
        )
    request.approved, request.answered_at = payload.approve, context.now
    await items.settle(
        context.session, REOPEN.name, ("reopen_request", str(request.id)),
        "approve" if payload.approve else "deny", context.caller, context.now,
    )  # fmt: skip
    context.record(
        REOPEN_ANSWERED,
        subject=("reopen_request", str(request.id)),
        project_id=request.project_id,
        after={"approved": payload.approve},
    )
    row = await _decision(context.session, payload.project_id, request.decision_id)
    if payload.approve:
        _move(context, row, D.REOPENED)
        row.reopened_at = context.now
    await service.platform_line(
        context.session,
        row.project_id,
        f"Decision {row.id} ({row.topic}) is open again."
        if payload.approve
        else f"The request to reopen decision {row.id} ({row.topic}) is declined. It stands.",
        context.now,
        detail={"kind": "reopen answered", "decision": row.id, "approved": payload.approve},
    )
    return _item(row)


async def _reopen(done: items.Settling) -> None:
    """INV-26, HUM-2: the chairman's answer goes through the answer operation; at the
    deadline the request is denied and the ruling stands."""
    request_id = int(done.item.fields["request_id"])
    if done.call is not None:
        await done.call(
            "decisions.answer", request_id=request_id, approve=done.outcome == "approve"
        )
        return
    request = await done.session.get(ReopenRequest, request_id)
    if request is None or request.approved is not None:
        return
    request.approved, request.answered_at = False, done.now
    append_event(
        done.session,
        type=REOPEN_ANSWERED,
        caller=done.caller,
        at=done.now,
        subject=("reopen_request", str(request.id)),
        project_id=request.project_id,
        after={"approved": False},
        detail={"default": True},
    )


REOPEN = items.register(
    items.Kind(
        name="reopen request",
        filed_by="agent",
        actions=("approve", "deny"),
        default="deny",
        window=timedelta(days=7),
        title=lambda f: f"Request to reopen decision {f['decision_id']}",
        apply=_reopen,
        positive=("approve",),
    )
)
