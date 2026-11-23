"""What a person does while drafting a project with the Founder (FND-1, FND-3, FND-5,
FND-12, FND-13, IF-4.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog import catalog
from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.domain.connections import holds
from crewmind.domain.conversation import service as conversation
from crewmind.domain.founder import drafting as state
from crewmind.domain.founder import model as m
from crewmind.domain.founder.grammar import Grade
from crewmind.domain.founder.model import DRAFTING_MACHINE, D
from crewmind.domain.founder.turn import grade_goal
from crewmind.domain.library import transfer
from crewmind.domain.library.spec import ProjectSpec
from crewmind.domain.library.spec_operations import missing_credentials
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import Drafting, GrillItem

DRAFTING_CHANGED = event_type(
    "drafting.state_changed", "A drafting conversation changed state (7.19)."
)
DRAFTING_EDITED = event_type(
    "drafting.edited", "The chairman spoke, answered or accepted recommendations in a drafting."
)
BRIEF_MAX = 200_000
WHO_PAYS = "who_pays"


class StartInput(BaseModel):
    brief: str = Field(
        min_length=1, max_length=BRIEF_MAX, description="What you want, in your own words."
    )
    document: str | None = Field(
        default=None, max_length=BRIEF_MAX, description="The text of a brief to grill first."
    )


class QuickInput(BaseModel):
    brief: str = Field(min_length=1, max_length=BRIEF_MAX, description="What you want.")
    credential: str | None = Field(
        default=None, description="The credential that pays. Needed when you have several."
    )


class DraftingRef(BaseModel):
    drafting_id: str = Field(description="The conversation's id, from `founder list`.")


class SayInput(DraftingRef):
    body: str = Field(min_length=1, max_length=BRIEF_MAX, description="Your message.")


class DraftAnswerInput(DraftingRef):
    question_id: int = Field(description="The question's id.")
    answer: str = Field(
        default="",
        max_length=4000,
        description='Empty or "yes" accepts the recommendation; a letter picks an option; '
        "anything else is your own answer.",
    )


class ConfirmDraftInput(DraftingRef):
    start: bool = Field(default=False, description="Start the project once it is created.")


class Line(BaseModel):
    id: int
    author: str = Field(description="person, founder or platform.")
    body: str
    detail: dict[str, Any] | None
    at: datetime


class QuestionView(BaseModel):
    id: int
    settles: str
    text: str
    options: list[str]
    recommended: int | None = Field(description="The recommended option. Empty: you choose.")
    changes: str = Field(description="What your answer changes.")


class LedgerLine(BaseModel):
    settles: str
    value: str
    source: str = Field(description="words (yours), answer or assumption.")
    passage: str | None


class DraftingView(BaseModel):
    drafting_id: str
    state: str
    quick: bool
    waiting_for: str = Field(description="you, the Founder, or nobody.")
    failure: str | None
    lines: list[Line]
    questions: list[QuestionView] = Field(description="Questions waiting for your answer.")
    ledger: list[LedgerLine]
    draft: dict[str, Any] | None = Field(description="The proposed project spec.")
    grade: dict[str, Any] | None
    rehearsal: str | None = Field(description="The verdict of the rehearsal of this draft.")
    ready: bool
    not_ready_because: list[str]
    rules_hit: list[dict[str, Any]] = Field(
        description="Tool calls of the Founder that a rule refused."
    )
    project_id: str | None


class DraftingItem(BaseModel):
    drafting_id: str
    state: str
    quick: bool
    opening: str
    project_id: str | None
    updated_at: datetime


class DraftingList(BaseModel):
    items: list[DraftingItem]


class CreatedProject(BaseModel):
    project_id: str
    name: str
    state: str
    missing: list[str] = Field(description="What is still needed before it can start.")
    missing_credentials: list[str] = Field(
        description="Model credentials the roster needs that you do not have yet."
    )
    waiting: list[str] = Field(
        description="Who in the crew could not work yet, and why: a connection their role "
        "needs, or a seat that cannot run. Starting now means starting without it (CON-5)."
    )
    can_start: bool = Field(description="The project is a draft and can be started.")


async def view(context: Context, drafting: Drafting) -> DraftingView:
    session = context.session
    questions = await state.open_question(session, drafting.id)
    missing = await state.not_ready_because(session, drafting)
    waiting = "nobody"
    if drafting.state == D.DRAFTING:
        waiting = "the Founder" if drafting.turn == m.DUE else "you"
    rehearsed = drafting.draft is not None and drafting.rehearsed_draft == state.fingerprint(
        drafting.draft
    )
    return DraftingView(
        drafting_id=drafting.id,
        state=drafting.state,
        quick=drafting.quick,
        waiting_for=waiting,
        failure=drafting.failure,
        lines=[
            Line(id=line.id, author=line.author, body=line.body, detail=line.detail, at=line.at)
            for line in await state.lines(session, drafting.id)
        ],
        questions=[
            QuestionView(
                id=question.id,
                settles=question.settles,
                text=question.text,
                options=[str(option) for option in question.options],
                recommended=question.recommended,
                changes=question.changes,
            )
            for question in questions
        ],
        ledger=[
            LedgerLine(
                settles=entry.settles,
                value=entry.value,
                source=entry.source,
                passage=entry.passage,
            )
            for entry in await state.ledger(session, drafting.id)
        ],
        draft=(drafting.draft or {}).get("spec"),
        grade=drafting.grade,
        rehearsal=(drafting.rehearsal or {}).get("verdict") if rehearsed else None,
        ready=not missing and drafting.state == D.DRAFTING,
        not_ready_because=missing,
        rules_hit=list(drafting.rules_hit or []),
        project_id=drafting.project_id,
    )


def _drafting_only(drafting: Drafting) -> None:
    if drafting.state != D.DRAFTING:
        raise Refusal(
            "not_drafting",
            f"This conversation is {drafting.state}; nothing more can be drafted in it.",
            rule=DRAFTING_MACHINE.rule_id,
            hint="Start a new one with `crewmind founder start`.",
        )


async def _begin(context: Context, brief: str, document: str | None, quick: bool) -> Drafting:
    session, person = context.session, context.caller.actor_id
    drafting = state.new(person, m.FOUNDER, context.now, quick=quick)
    least = int(
        await services_of(context).settings.get(
            session, Subject(Scope.INSTALL, INSTALL_SUBJECT), "grill.min_characters"
        )
    )
    # FND-15: an upload, or a paste long enough to be a brief, is grilled before drafting.
    if not quick:
        drafting.document = document or (brief if len(brief) >= least else None)
    session.add(drafting)
    await session.flush()
    state.say(session, drafting, m.PERSON, brief, context.now)
    if document:
        state.say(
            session,
            drafting,
            m.PLATFORM,
            f"A document of {len(document):,} characters is attached.",
            context.now,
            {"kind": "document"},
        )
    context.record(DRAFTING_CHANGED, subject=("drafting", drafting.id), after={"state": D.DRAFTING})
    mine = await state.credentials_of(session, person)
    if len(mine) == 1:
        # FND-4: what can be looked up is looked up. One credential leaves no choice.
        await state.settle(
            session, drafting, WHO_PAYS, mine[0], m.ASSUMPTION, context.now,
            "It is your only credential.",
        )  # fmt: skip
    elif not mine:
        await state.settle(
            session, drafting, WHO_PAYS, "No credential yet", m.ASSUMPTION, context.now,
            "You have no model credential yet. Add one before the project starts.",
        )  # fmt: skip
    return drafting


@operation(
    "founder.start",
    summary="Start drafting a project by describing what you want.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def start(context: Context, payload: StartInput) -> DraftingView:
    """FND-1, FND-15: the conversation lives on the server and can be resumed anywhere. A
    document, or a long paste, is grilled before anything is drafted."""
    drafting = await _begin(context, payload.brief, payload.document, quick=False)
    return await view(context, drafting)


@operation(
    "founder.quick",
    summary="Quick mode: the Founder decides everything itself, then creates and starts.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def quick(context: Context, payload: QuickInput) -> DraftingView:
    """FND-12: one credential pays every seat, and it is never chosen for you: with more
    than one, you say which."""
    mine = await state.credentials_of(context.session, context.caller.actor_id)
    if payload.credential is not None and payload.credential not in mine:
        raise Refusal(
            "credential_not_found",
            f"You have no credential named {payload.credential}.",
            rule=m.FND_3.id,
            hint="List yours with `crewmind credentials list`.",
        )
    if payload.credential is None and len(mine) > 1:
        raise Refusal(
            "say_who_pays",
            "You have more than one credential, and who pays is never chosen for you.",
            rule=m.FND_3.id,
            hint="Name one: " + ", ".join(mine) + ".",
        )
    drafting = await _begin(context, payload.brief, None, quick=True)
    if payload.credential is not None:
        await state.settle(
            context.session, drafting, WHO_PAYS, payload.credential, m.ANSWER, context.now
        )
    return await view(context, drafting)


@operation(
    "founder.show",
    summary="Show a drafting conversation: what was said, the ledger and the draft.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show(context: Context, payload: DraftingRef) -> DraftingView:
    drafting = await state.get(context.session, payload.drafting_id, context.caller.actor_id)
    return await view(context, drafting)


@operation(
    "founder.list",
    summary="List your drafting conversations.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_draftings(context: Context, payload: Empty) -> DraftingList:
    rows = await context.session.scalars(
        select(Drafting)
        .where(Drafting.person_id == context.caller.actor_id, Drafting.kind == m.FOUNDER)
        .order_by(Drafting.updated_at.desc())
    )
    items: list[DraftingItem] = []
    for row in rows:
        first = (await state.lines(context.session, row.id))[:1]
        items.append(
            DraftingItem(
                drafting_id=row.id,
                state=row.state,
                quick=row.quick,
                opening=first[0].body[:120] if first else "",
                project_id=row.project_id,
                updated_at=row.updated_at,
            )
        )
    return DraftingList(items=items)


@operation(
    "founder.say",
    summary="Say something to the Founder in a drafting conversation.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def say(context: Context, payload: SayInput) -> DraftingView:
    drafting = await state.get(context.session, payload.drafting_id, context.caller.actor_id)
    _drafting_only(drafting)
    state.say(context.session, drafting, m.PERSON, payload.body, context.now)
    drafting.turn = m.DUE
    context.record(DRAFTING_EDITED, subject=("drafting", drafting.id), after={"what": "said"})
    return await view(context, drafting)


@operation(
    "founder.answer",
    summary="Answer a question the Founder asked.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def answer(context: Context, payload: DraftAnswerInput) -> DraftingView:
    """FND-3, FND-5: the answer goes into the ledger, tagged as an answer."""
    drafting = await state.get(context.session, payload.drafting_id, context.caller.actor_id)
    _drafting_only(drafting)
    question = await state.answer(
        context.session, drafting, payload.question_id, payload.answer, context.now
    )
    context.record(
        DRAFTING_EDITED,
        subject=("drafting", drafting.id),
        after={"what": "answered", "settles": question.settles},
    )
    return await view(context, drafting)


@operation(
    "founder.accept_rest",
    summary="Tell the Founder to use its own recommendations for everything still open.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def accept_rest(context: Context, payload: DraftingRef) -> DraftingView:
    """FND-15: what is accepted this way is recorded as an assumption, not as an answer."""
    drafting = await state.get(context.session, payload.drafting_id, context.caller.actor_id)
    _drafting_only(drafting)
    recorded = await state.accept_the_rest(context.session, drafting, context.now)
    state.say(
        context.session,
        drafting,
        m.PERSON,
        "Use your recommendations for the rest.",
        context.now,
        {"kind": "accept rest", "recorded": recorded},
    )
    context.record(
        DRAFTING_EDITED,
        subject=("drafting", drafting.id),
        after={"what": "accepted the rest", "recorded": recorded},
    )
    return await view(context, drafting)


@operation(
    "founder.discard",
    summary="Discard a drafting conversation you no longer want. No project comes of it.",
    authority=Authority.PERSON,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def discard(context: Context, payload: DraftingRef) -> DraftingView:
    """7.19, FND-1: the person who started a draft may drop it. It leaves the list of
    unfinished drafts and takes no further turn. The conversation is kept in the record."""
    drafting = await state.get(context.session, payload.drafting_id, context.caller.actor_id)
    _drafting_only(drafting)
    DRAFTING_MACHINE.check(D.DRAFTING, D.DISCARDED)
    drafting.state, drafting.turn = D.DISCARDED, m.IDLE
    drafting.updated_at = context.now
    context.record(
        DRAFTING_CHANGED,
        subject=("drafting", drafting.id),
        before={"state": D.DRAFTING},
        after={"state": D.DISCARDED},
    )
    return await view(context, drafting)


class GoalInput(BaseModel):
    goal: str = Field(min_length=1, max_length=BRIEF_MAX, description="The goal, in prose.")


async def _graded(_: Any, payload: GoalInput, services: Any) -> Grade:
    """The model call is made before the operation's transaction opens."""
    return await grade_goal(services.wired["gateway"], payload.goal)


@operation(
    "goals.grade",
    summary="Grade a goal against the ten elements of the goal grammar.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="create",
    prepare=_graded,
)
async def grade(context: Context, payload: GoalInput) -> Grade:
    """FND-7, LIB-5: the Founder's model grades; the platform checks every quote against
    the goal and computes the verdict. The call is metered to the install."""
    return context.prepared


async def _call(context: Context, operation_name: str, /, **values: Any) -> Any:
    wanted = catalog.get(operation_name)
    return await context.executor.call(context, wanted, wanted.input(**values))


def _move(context: Context, drafting: Drafting, target: D) -> None:
    DRAFTING_MACHINE.check(drafting.state, target)
    context.record(
        DRAFTING_CHANGED,
        subject=("drafting", drafting.id),
        before={"state": drafting.state},
        after={"state": target},
    )
    drafting.state = target


@operation(
    "founder.create",
    summary="Confirm the ledger and create the project from the draft.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def create(context: Context, payload: ConfirmDraftInput) -> CreatedProject:
    """FND-5, FND-12, FND-13, FND-14: a project is created only from a draft with nothing
    left open: every decision settled, the goal graded ready, the draft rehearsed. Calling
    this is the chairman confirming the ledger. The conversation becomes the project chat,
    and the project records the doctrine it was drafted under."""
    session = context.session
    drafting = await state.get(session, payload.drafting_id, context.caller.actor_id)
    _drafting_only(drafting)
    missing = await state.not_ready_because(session, drafting)
    if drafting.quick:
        # FND-12: quick mode accepts the Founder's own recommendations in place of answers
        # and does not wait on the grade; a draft and its rehearsal are still required.
        missing = [line for line in missing if "rehears" in line or "no draft" in line]
    if missing:
        raise Refusal(
            "draft_not_ready",
            "The draft is not ready: " + " ".join(missing),
            rule=m.FND_5.id,
            hint="See what is open with `crewmind founder show`.",
        )
    assert drafting.draft is not None
    entries = await state.ledger(session, drafting.id)
    spec = ProjectSpec.model_validate(drafting.draft["spec"])
    paid_by = next((entry.value for entry in entries if entry.settles == WHO_PAYS), None)
    mine = await state.credentials_of(session, context.caller.actor_id)
    if spec.paying_credential is None and paid_by in mine:
        spec = spec.model_copy(update={"paying_credential": paid_by})
    if drafting.quick:
        # FND-12: no data sources, secrets, email or integrations in a quick project.
        spec = spec.model_copy(update={"integrations": [], "credentials": []})
        _move(context, drafting, D.CREATING)
    project, still_missing = await transfer.create(context, spec)
    drafting.project_id = project.id
    project.doctrine_fingerprint = drafting.doctrine
    examples = list(
        await session.scalars(
            select(GrillItem.passage).where(
                GrillItem.drafting_id == drafting.id, GrillItem.is_example
            )
        )
    )
    project.extras = {
        **(project.extras or {}),
        "founder": {
            "ledger": [
                {"settles": e.settles, "value": e.value, "source": e.source, "passage": e.passage}
                for e in entries
            ],
            "first_bets": drafting.draft.get("first_bets") or [],
            "examples": examples,
        },
    }
    first = drafting.draft.get("first_requirement")
    if first and spec.type != "explore":
        await _call(
            context,
            "requirements.add",
            project_id=project.id,
            text=first["text"],
            test_kind="observable",
            success_test=first["success_test"],
        )
    for line in await state.lines(session, drafting.id):
        who = {m.PERSON: "You", m.FOUNDER: "The Founder"}.get(line.author, "Platform")
        await conversation.platform_line(
            session,
            project.id,
            f"{who}: {line.body}",
            context.now,
            detail={"kind": "drafting", "author": line.author},
        )
    if not drafting.quick:
        _move(context, drafting, D.CREATED)
    else:
        _move(context, drafting, D.STARTING)
    waiting = [
        blocker.text
        for blocker in await holds.blockers(session, project, context.now, context.caller)
    ]
    started = False
    # Quick mode asks nothing, so it starts without what is missing and says who waits.
    # A chairman who asked to start is never started past what would hold the crew.
    if drafting.quick or (payload.start and not waiting):
        await _call(
            context, "projects.start", project_id=project.id, without_missing=drafting.quick
        )
        started = True
        if drafting.quick:
            _move(context, drafting, D.STARTED)
    return CreatedProject(
        project_id=project.id,
        name=project.name,
        state=project.state,
        missing=still_missing,
        missing_credentials=await missing_credentials(context, spec),
        waiting=waiting,
        can_start=not started,
    )
