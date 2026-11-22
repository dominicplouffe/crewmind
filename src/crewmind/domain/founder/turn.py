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
from crewmind.gateway.protocol import CompletionRequest, ToolCall, Turn
from crewmind.gateway.service import Gateway
from crewmind.services import Services
from crewmind.storage.models import Drafting, Person

logger = logging.getLogger(__name__)

DRAFT, GRADE = "draft", "grade"
CALLS_MOST = 16
"""Model calls in one turn. A turn that needs more ends, and says so."""
CONTEXT_OPERATION = "founder.say"

ROLE = """You are the Founder: a platform assistant whose only deliverable is a project spec.
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
        following = tree.next_one(done)
        missing = await state.not_ready_because(session, drafting)
        lines = [
            "# Where the interview stands",
            "Settled: "
            + ("; ".join(f"{e.settles} = {e.value} ({e.source})" for e in entries) or "nothing"),
            "Open passages of the document: "
            + (", ".join(f"item:{item.id} ({item.problem})" for item in waiting) or "none"),
            f"Next decision to ask: {following.key if following else 'none'}",
            "Grade of the current goal: " + str((drafting.grade or {}).get("summary", "none")),
            "Not ready because: " + (" ".join(missing) or "nothing; it is ready"),
        ]
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
                    {"tool": call.name, "rule": envelope.rule, "code": envelope.code},
                ]
            return {"refused": envelope.model_dump(mode="json")}

    async def take(self, drafting_id: str, on_delta: Callable[[str], None] | None = None) -> None:
        """Run the Founder until it speaks. A failure is written on the conversation and
        the turn stays owed, so nothing is lost (FND-1)."""
        try:
            await self._take(drafting_id, on_delta)
        except Exception as error:
            logger.exception("founder: the turn of %s failed", drafting_id)
            async with self._sessions() as session, session.begin():
                drafting = await session.get(Drafting, drafting_id)
                assert drafting is not None
                reason = error.envelope.message if isinstance(error, Refusal) else str(error)
                drafting.turn, drafting.failure = m.FAILED_TURN, reason
                drafting.turn_attempts += 1
                state.say(
                    session,
                    drafting,
                    m.PLATFORM,
                    f"The Founder could not answer: {reason} Send your message again to retry.",
                    self._clock(),
                    {"kind": "failure"},
                )

    async def _take(self, drafting_id: str, on_delta: Callable[[str], None] | None) -> None:
        async with self._sessions() as session:
            drafting = await session.get(Drafting, drafting_id)
            assert drafting is not None
            system = await self._system(session, drafting)
            messages = await self._history(session, drafting)
            calls = drafting.model_calls
        said = ""
        for _ in range(CALLS_MOST):
            request = CompletionRequest(system=system, messages=messages, tools=TOOL_SPECS)
            response = await self._gateway.founder_call(
                request, purpose=DRAFT, calls_so_far=calls, on_delta=on_delta
            )
            calls += 1
            if not response.tool_calls:
                said = response.text
                break
            messages.append(
                Turn(role="assistant", content=response.text, tool_calls=response.tool_calls)
            )
            for call in response.tool_calls:
                result = await self.run_tool(drafting_id, call)
                messages.append(Turn(role="tool", content=json.dumps(result), tool_call_id=call.id))
        async with self._sessions() as session, session.begin():
            drafting = await session.get(Drafting, drafting_id)
            assert drafting is not None
            drafting.model_calls = calls
            drafting.turn, drafting.failure = m.IDLE, None
            if said.strip():
                state.say(session, drafting, m.FOUNDER, said.strip(), self._clock())
