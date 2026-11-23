"""One turn of the Founder: the model speaks through its tools until it has something
to say to the chairman (FND-1, FND-2, FND-6)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog import catalog
from crewmind.catalog.caller import Caller, CallerKind, InstanceRole
from crewmind.catalog.execute import Clock, Context, Executor
from crewmind.catalog.refusal import Refusal
from crewmind.domain.founder import drafting as state
from crewmind.domain.founder import grammar, tree
from crewmind.domain.founder import model as m
from crewmind.domain.founder.grammar import Grade
from crewmind.domain.founder.tools import TOOL_SPECS, NeedsGrade, Toolbox
from crewmind.domain.library import service as library
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import Subject
from crewmind.gateway.protocol import CompletionRequest, ToolCall, Turn
from crewmind.gateway.service import Gateway
from crewmind.services import Services
from crewmind.storage.models import Drafting, Person

logger = logging.getLogger(__name__)

DRAFT, GRADE = "draft", "grade"
CALLS_MOST = 16
"""Model calls in one turn. A turn that needs more ends, and says so."""

WORKING_ON = {
    "search_library": "Looking through the role library for a crew",
    "list_credentials": "Checking who can pay",
    "fetch_url": "Reading a web page",
    "read_upload": "Reading your document",
    "grade_goal": "Grading the goal",
    "rehearse_spec": "Rehearsing the draft",
    "ask": "Writing a question for you",
    "propose_spec": "Writing the draft",
}
"""What the chairman is told the Founder is doing, step by step, so a long turn is never
silent (P17, FND-1)."""

Told = Callable[[str], None]


def working_on(call: ToolCall) -> str:
    said = WORKING_ON.get(call.name, "Working")
    if call.name == "fetch_url" and isinstance(call.arguments.get("url"), str):
        return f"Reading {call.arguments['url'][:80]}"
    return said


CONTEXT_OPERATION = "founder.say"
ROLE_WORDS = 160
"""How much of a role's description the Founder is shown in its list of roles."""

ROLE = """You are the Founder: a platform assistant whose only deliverable is a project spec.
You never do the work the chairman describes, and you never write any part of it. You set
up a project: a crew of agents that will do the work, under a goal, a budget and a finish
line. Work that repeats (every day, every week) is an operate project; work with an end is
a deliver project; a question to settle is an explore project. Begin your first reply by
saying in one sentence what you are setting up: the kind of project, and the crew that
will do the work.
You draft a project with the chairman, in conversation. You act only through your tools.
Draft first, then interview: every question you ask carries your recommended answer, and
those answers are the draft. Ask one decision per question, worded so that "yes" accepts
your recommendation. Look up what you can look up instead of asking. Rehearse the draft
before you call it ready, and act on what the rehearsal finds. When a tool refuses a call,
read the reason and do what it says. Write to the chairman in plain, short sentences."""


def caller_of(person: Person) -> Caller:
    return Caller(CallerKind.PERSON, person.id, role=InstanceRole(person.role))


async def grade_goal(gateway: Gateway, goal: str) -> Grade:
    """FND-7: the model grades against the fixed rubric; the platform checks each quote
    and computes the verdict."""
    request = CompletionRequest(
        system=f"{grammar.rubric()}\n\n# The goal grammar\n\n{state.doctrine_text()}",
        messages=[Turn(role="user", content=f"The goal to grade:\n\n{goal}")],
    )
    response = await gateway.founder_call(request, purpose=GRADE)
    return grammar.check(goal, grammar.parse(response.text))


class FounderTurn:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        clock: Clock,
        gateway: Gateway,
        services: Services,
        executor: Executor,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._gateway = gateway
        self._services = services
        self._executor = executor

    def _context(self, session: AsyncSession, person: Person) -> Context:
        return Context(
            caller=caller_of(person),
            session=session,
            now=self._clock(),
            operation=catalog.get(CONTEXT_OPERATION),
            sessions=self._sessions,
            services=self._services,
            executor=self._executor,
        )

    async def _system(self, session: AsyncSession, drafting: Drafting) -> str:
        """The doctrine, then where the interview stands. The state is the platform's own
        account, so the model need not remember it."""
        entries = await state.ledger(session, drafting.id)
        done = {entry.settles for entry in entries}
        waiting = await state.open_items(session, drafting.id)
        pace = await self._services.settings.get(
            session, Subject(Scope.PERSON, drafting.person_id), "grill.pace"
        )
        ready = tree.ready(done)[: None if pace == "batch" else 1]
        asking = (
            "Decisions to ask now, all of them in one call of `ask`, one question each: "
            if pace == "batch"
            else "Next decision to ask: "
        )
        missing = await state.not_ready_because(session, drafting)
        lines = [
            "# Where the interview stands",
            "Settled: "
            + ("; ".join(f"{e.settles} = {e.value} ({e.source})" for e in entries) or "nothing"),
            "Open passages of the document: "
            + (", ".join(f"item:{item.id} ({item.problem})" for item in waiting) or "none"),
            asking + (", ".join(decision.key for decision in ready) or "none"),
            "Grade of the current goal: " + str((drafting.grade or {}).get("summary", "none")),
            "Not ready because: " + (" ".join(missing) or "nothing; it is ready"),
        ]
        lines += await self._known(session, drafting)
        if drafting.quick:
            lines.append(
                "This is quick mode: ask nothing. Decide everything yourself, propose the "
                "spec with a value for every decision of the tree, and stop."
            )
        if drafting.rest_accepted:
            lines.append("The chairman said: use your recommendations for the rest. Ask nothing.")
        if drafting.document:
            lines.append(
                "The chairman gave a document. Read it with read_upload, list what it says "
                "with ask (`extracted`), and resolve every passage with a problem before "
                "you draft."
            )
        return "\n\n".join([ROLE, state.doctrine_text(), "\n".join(lines)])

    async def _known(self, session: AsyncSession, drafting: Drafting) -> list[str]:
        """What the Founder would otherwise look up or write again on every turn: the role
        library, and its own draft. A turn starts from nothing but this prompt and the
        conversation, so what is not here is redone, at the chairman's expense in time."""
        await library.load_starter(session, self._clock())
        roles = await library.current_roles(session)
        known = [
            "",
            "# The role library",
            "A team's `role` is one of these slugs. Search only for what is not here.",
            *(
                f"- {role.slug} ({role.seat_kind}): {role.description[:ROLE_WORDS]}"
                for role in roles
            ),
            "",
            "# The current draft",
        ]
        if drafting.draft is None:
            known.append(
                "There is none yet. In this turn: look up what you need, call propose_spec "
                "once with the whole spec, then ask."
            )
        else:
            known += [
                json.dumps(drafting.draft, ensure_ascii=False),
                "This draft is kept. Do not write it again. When an answer changes it, call "
                "propose_spec with `changes`: only the fields of the spec that differ, and "
                "any decision whose value changed. When an answer changes nothing in it, "
                "go straight to the next questions.",
            ]
        return known

    async def _history(self, session: AsyncSession, drafting: Drafting) -> list[Turn]:
        turns: list[Turn] = []
        for line in await state.lines(session, drafting.id):
            role = "assistant" if line.author == m.FOUNDER else "user"
            body = line.body if line.author != m.PLATFORM else f"(platform) {line.body}"
            turns.append(Turn(role=role, content=body))
        return turns

    async def run_tool(self, drafting_id: str, call: ToolCall) -> dict[str, Any]:
        """Each tool call is one transaction. A refusal is rolled back, noted on the
        conversation and handed to the model as the tool's result, with its rule. A tool
        that needs a goal graded is called again once the grade is in hand, so no model
        call is made with a transaction open."""
        graded: dict[str, Grade] = {}
        try:
            while True:
                try:
                    async with self._sessions() as session, session.begin():
                        drafting = await session.get(Drafting, drafting_id)
                        assert drafting is not None
                        person = await session.get(Person, drafting.person_id)
                        assert person is not None
                        box = Toolbox(self._context(session, person), drafting, graded)
                        return await box.call(call.name, call.arguments)
                except NeedsGrade as needed:
                    graded[needed.goal] = await grade_goal(self._gateway, needed.goal)
        except Refusal as refusal:
            envelope = refusal.envelope
            async with self._sessions() as session, session.begin():
                drafting = await session.get(Drafting, drafting_id)
                assert drafting is not None
                drafting.rules_hit = [
                    *(drafting.rules_hit or []),
                    {
                        "tool": call.name,
                        "rule": envelope.rule,
                        "code": envelope.code,
                        "message": envelope.message,
                    },
                ]
            return {"refused": envelope.model_dump(mode="json")}

    async def take(
        self,
        drafting_id: str,
        on_delta: Callable[[str], None] | None = None,
        on_step: Told | None = None,
    ) -> None:
        """Run the Founder until it speaks. A failure is written on the conversation and
        the turn stays owed, so nothing is lost (FND-1). `on_step` is told what the Founder
        is doing as it works, in plain words (P17)."""
        try:
            await self._take(drafting_id, on_delta, on_step or (lambda _: None))
        except Exception as error:
            logger.exception("founder: the turn of %s failed", drafting_id)
            async with self._sessions() as session, session.begin():
                drafting = await session.get(Drafting, drafting_id)
                assert drafting is not None
                reason = error.envelope.message if isinstance(error, Refusal) else str(error)
                # P17, P18: say what fixes it. Sending again helps only when nothing is missing.
                hint = error.envelope.hint if isinstance(error, Refusal) else None
                after = f" {hint}" if hint else " Send your message again to retry."
                drafting.turn, drafting.failure = m.FAILED_TURN, reason
                drafting.turn_attempts += 1
                state.say(
                    session,
                    drafting,
                    m.PLATFORM,
                    f"The Founder could not answer: {reason}{after}",
                    self._clock(),
                    {"kind": "failure"},
                )

    async def _take(
        self, drafting_id: str, on_delta: Callable[[str], None] | None, on_step: Told
    ) -> None:
        async with self._sessions() as session:
            drafting = await session.get(Drafting, drafting_id)
            assert drafting is not None
            system = await self._system(session, drafting)
            messages = await self._history(session, drafting)
            calls = drafting.model_calls
        said, spoke, refused = "", False, ""
        on_step("Thinking")
        for _ in range(CALLS_MOST):
            request = CompletionRequest(system=system, messages=messages, tools=TOOL_SPECS)
            response = await self._gateway.founder_call(
                request, purpose=DRAFT, calls_so_far=calls, on_delta=on_delta
            )
            calls += 1
            if not response.tool_calls:
                said, spoke = response.text, True
                break
            messages.append(
                Turn(role="assistant", content=response.text, tool_calls=response.tool_calls)
            )
            for call in response.tool_calls:
                on_step(working_on(call))
                result = await self.run_tool(drafting_id, call)
                if "refused" in result:
                    refused = str(result["refused"]["message"])
                    on_step(f"A step was not accepted, so the Founder is fixing it: {refused}")
                messages.append(Turn(role="tool", content=json.dumps(result), tool_call_id=call.id))
            on_step("Thinking")
        async with self._sessions() as session, session.begin():
            drafting = await session.get(Drafting, drafting_id)
            assert drafting is not None
            drafting.model_calls = calls
            drafting.turn, drafting.failure = m.IDLE, None
            if said.strip():
                state.say(session, drafting, m.FOUNDER, said.strip(), self._clock())
            elif not spoke:
                # P17: a turn that runs out of steps says so, and says what stopped it.
                why = f" The last step that was not accepted: {refused}" if refused else ""
                state.say(
                    session,
                    drafting,
                    m.PLATFORM,
                    f"The Founder worked through {CALLS_MOST} steps and did not finish this "
                    f"turn. What it settled is kept.{why} Send a message to have it carry on.",
                    self._clock(),
                    {"kind": "out of steps"},
                )
