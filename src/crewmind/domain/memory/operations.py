"""Operations on pinned memory: an agent's own notes, and what people can see (MEM-1,
MEM-6, INV-25)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.execution.agent import agent_of
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.memory import pinned
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import PinnedNote, Seat

MEM_1 = rules.register(
    Rule("MEM-1", "An agent's pinned notes are its own and stay within its size cap.")
)
NOTE_PINNED = event_type("pinned_note.added", "An agent pinned a note for itself (MEM-1).")
NOTE_UNPINNED = event_type("pinned_note.removed", "An agent removed a pinned note (MEM-1).")
AGENT = frozenset({Principal.AGENT_RUN})


class NoteInput(BaseModel):
    text: str = Field(
        min_length=3, max_length=2000, description="What to keep in front of you in every run."
    )


class NoteRef(BaseModel):
    note_id: int = Field(description="The note's id, as shown in your pinned memory.")


class NoteItem(BaseModel):
    id: int
    text: str
    tokens_used: int
    tokens_cap: int


class PinnedInput(ProjectRef):
    seat: str | None = Field(default=None, description="An agent's name. Default: the CEO.")


class PinnedView(BaseModel):
    seat: str
    text: str = Field(description="Exactly what this agent is given at the start of every run.")
    project_tokens: int
    project_cap: int
    agent_tokens: int
    agent_cap: int


@operation(
    "agent.pin_note",
    summary="Pin a note for yourself. It is in front of you in every run until you remove it.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def pin_note(context: Context, payload: NoteInput) -> NoteItem:
    """MEM-1, MEM-7: an agent's own memory notes. A note past the cap is refused, naming
    what to retire. Allowed in a chat run: it changes only the agent's own memory (INV-23)."""
    view = await agent_of(context)
    settings = services_of(context).settings
    _, cap = await pinned.caps(context.session, settings, view.project)
    current = await pinned.pinned_for(context.session, view.project, view.seat)
    size = current.agent_tokens + pinned.estimate_tokens(payload.text)
    if size > cap:
        listed = "; ".join(
            f"note {n.id} ({pinned.estimate_tokens(n.text)} tokens)" for n in current.notes
        )
        raise Refusal(
            "pinned_notes_full",
            f"This note would bring your pinned memory to about {size:,} tokens; the cap "
            f"`memory.pinned_agent_tokens` is {cap:,}.",
            rule=MEM_1.id,
            hint=f"Remove a note first with agent_unpin_note. Yours: {listed or 'none'}.",
        )
    row = PinnedNote(
        project_id=view.project.id, seat_id=view.seat.id, text=payload.text, created_at=context.now
    )
    context.session.add(row)
    await context.session.flush()
    context.record(NOTE_PINNED, subject=("pinned_note", str(row.id)), project_id=view.project.id)
    return NoteItem(id=row.id, text=row.text, tokens_used=size, tokens_cap=cap)


@operation(
    "agent.unpin_note",
    summary="Remove one of your own pinned notes.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def unpin_note(context: Context, payload: NoteRef) -> NoteItem:
    """MEM-1, P3: an agent removes only its own notes."""
    view = await agent_of(context)
    row = await context.session.get(PinnedNote, payload.note_id)
    if row is None or row.seat_id != view.seat.id:
        raise Refusal(
            "note_not_yours",
            f"Note {payload.note_id} is not one of your pinned notes.",
            kind=RefusalKind.NOT_FOUND,
            rule=MEM_1.id,
            hint="Your notes are listed in your pinned memory.",
        )
    await context.session.delete(row)
    context.record(NOTE_UNPINNED, subject=("pinned_note", str(row.id)), project_id=view.project.id)
    await context.session.flush()
    _, cap = await pinned.caps(context.session, services_of(context).settings, view.project)
    current = await pinned.pinned_for(context.session, view.project, view.seat)
    return NoteItem(id=row.id, text=row.text, tokens_used=current.agent_tokens, tokens_cap=cap)


@operation(
    "memory.pinned",
    summary="Show exactly what an agent is given at the start of every run.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_pinned(context: Context, payload: PinnedInput) -> PinnedView:
    """MEM-6, INV-25: pinned memory is visible. This is the text the context pack carries."""
    project = view_of(context).project
    if payload.seat is None:
        seat = await ceo_of(context.session, project.id)
    else:
        found = await context.session.scalar(
            select(Seat).where(Seat.project_id == project.id, Seat.name == payload.seat)
        )
        if found is None:
            raise Refusal(
                "seat_not_found",
                f"There is no agent named {payload.seat} in this project.",
                kind=RefusalKind.NOT_FOUND,
                hint="List the agents with `roster show`.",
            )
        seat = found
    current = await pinned.pinned_for(context.session, project, seat)
    project_cap, agent_cap = await pinned.caps(
        context.session, services_of(context).settings, project
    )
    return PinnedView(
        seat=seat.name,
        text=current.render(),
        project_tokens=current.project_tokens,
        project_cap=project_cap,
        agent_tokens=current.agent_tokens,
        agent_cap=agent_cap,
    )
