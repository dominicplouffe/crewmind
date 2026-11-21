"""Operations on pinned memory: an agent's own notes, and what people can see (MEM-1,
MEM-6, INV-25)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.registry import catalog
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.execution.agent import agent_of
from crewmind.domain.execution.agent_operations import work_run_only
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.memory import pinned, recall
from crewmind.domain.memory.engine import Recalled
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import Subject
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import PinnedNote, Seat

MEM_1 = rules.register(
    Rule("MEM-1", "An agent's pinned notes are its own and stay within its size cap.")
)
NOTE_PINNED = event_type("pinned_note.added", "An agent pinned a note for itself (MEM-1).")
NOTE_UNPINNED = event_type("pinned_note.removed", "An agent removed a pinned note (MEM-1).")
AGENT = frozenset({Principal.AGENT_RUN})
ORDER_CHARACTERS = 400  # MSG-4: the most a standing order may have


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


MEM_3 = rules.register(
    Rule("MEM-3", "Memory is read and changed only within the scopes the caller belongs to.")
)
MEMORY_ADDED = event_type("memory.added", "A memory was added by a person or an agent (MEM-6).")
MEMORY_EDITED = event_type("memory.edited", "A person edited a memory (MEM-6).")
MEMORY_FORGOTTEN = event_type(
    "memory.forgotten", "A memory was forgotten. Its content is not recorded (MEM-6)."
)
LISTED = 200  # the most entries one scope shows in the Memory panel


class MemoryItem(BaseModel):
    id: str
    scope: str = Field(description="project, team <name>, agent <name>, or your preferences.")
    text: str
    source: str | None
    untrusted: bool = Field(description="It came from outside the project (P4).")
    at: datetime


class MemoryList(BaseModel):
    items: list[MemoryItem]


class ListInput(ProjectRef):
    scope: str | None = Field(
        default=None, description="project, team <name> or agent <name>. Default: all of them."
    )


class SearchInput(ProjectRef):
    query: str = Field(min_length=2, max_length=400, description="What to look for.")


class RememberInput(ProjectRef):
    text: str = Field(min_length=3, max_length=2000, description="The fact to remember.")
    scope: str = Field(default="project", description="project, team <name> or agent <name>.")


class EntryRef(ProjectRef):
    memory_id: str = Field(description="The entry's id, from `memory list`.")


class EditInput(EntryRef):
    text: str = Field(min_length=3, max_length=2000, description="The corrected fact.")


class PreferenceInput(BaseModel):
    text: str = Field(
        min_length=3, max_length=2000, description='A preference, such as "plain English".'
    )


class PreferenceRef(BaseModel):
    memory_id: str = Field(description="The preference's id, from `memory preferences`.")


class AgentRememberInput(BaseModel):
    text: str = Field(min_length=3, max_length=2000, description="The fact to remember.")
    scope: Literal["agent", "team", "project"] = Field(
        default="agent", description="Who should recall it: you, your team or the project."
    )


class RecallInput(BaseModel):
    query: str = Field(min_length=2, max_length=400, description="What you want to recall.")


def _memory_item(row: Recalled, label: str) -> MemoryItem:
    return MemoryItem(
        id=row.id,
        scope=label,
        text=row.text,
        source=row.metadata.get("source"),
        untrusted=bool(row.metadata.get("untrusted")),
        at=row.updated_at,
    )


async def _scopes(context: Context, scope: str | None) -> list[recall.ScopeName]:
    project = view_of(context).project
    names = await recall.project_scopes(context.session, project)
    if scope is None:
        return names
    chosen = [name for name in names if name.label == scope.strip().lower()]
    chosen = chosen or [name for name in names if name.label.lower() == scope.strip().lower()]
    if not chosen:
        raise Refusal(
            "scope_not_found",
            f"There is no memory scope named {scope} in this project.",
            kind=RefusalKind.NOT_FOUND,
            rule=MEM_3.id,
            hint="Use one of: " + ", ".join(name.label for name in names) + ".",
        )
    return chosen


async def _entry(context: Context, payload: EntryRef) -> tuple[Recalled, str]:
    """An entry that belongs to this project, with its scope's plain name (MEM-3)."""
    names = {name.scope: name.label for name in await _scopes(context, None)}
    row = await services_of(context).memory.get(payload.memory_id)
    if row is None or row.scope not in names:
        raise Refusal(
            "memory_not_found",
            f"There is no memory {payload.memory_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
            rule=MEM_3.id,
            hint="List the entries with `memory list`.",
        )
    return row, names[row.scope]


@operation(
    "memory.list",
    summary="Show what a project, a team or an agent remembers, newest first.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_memory(context: Context, payload: ListInput) -> MemoryList:
    """MEM-6: memory is visible, with each entry's source and date."""
    engine = services_of(context).memory
    items: list[MemoryItem] = []
    for name in await _scopes(context, payload.scope):
        items += [_memory_item(row, name.label) for row in await engine.listed(name.scope, LISTED)]
    return MemoryList(items=sorted(items, key=lambda item: item.at, reverse=True))


@operation(
    "memory.search",
    summary="Search what a project remembers.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def search_memory(context: Context, payload: SearchInput) -> MemoryList:
    names = {name.scope: name.label for name in await _scopes(context, None)}
    found = await services_of(context).memory.search(list(names), payload.query, LISTED)
    return MemoryList(items=[_memory_item(row, names[row.scope]) for row in found])


@operation(
    "memory.remember",
    summary="Add a fact to a project's memory yourself.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def remember(context: Context, payload: RememberInput) -> MemoryItem:
    (name,) = (await _scopes(context, payload.scope))[:1]
    engine = services_of(context).memory
    memory_id = await engine.add(
        name.scope, payload.text, recall.metadata(payload.project_id, "the chairman")
    )
    context.record(MEMORY_ADDED, subject=("memory", memory_id), project_id=payload.project_id)
    row = await engine.get(memory_id)
    assert row is not None
    return _memory_item(row, name.label)


@operation(
    "memory.edit",
    summary="Correct a memory.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def edit(context: Context, payload: EditInput) -> MemoryItem:
    """MEM-6: the chairman can edit any entry. The engine keeps the earlier version in its
    history, with its dates (MEM-4)."""
    row, label = await _entry(context, payload)
    engine = services_of(context).memory
    await engine.update(row.id, payload.text)
    context.record(MEMORY_EDITED, subject=("memory", row.id), project_id=payload.project_id)
    current = await engine.get(row.id)
    assert current is not None
    return _memory_item(current, label)


@operation(
    "memory.forget",
    summary="Forget a memory for good. It is deleted, not hidden.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def forget(context: Context, payload: EntryRef) -> MemoryItem:
    """MEM-6, INV-21: the entry is deleted from the store, the index and the history. The
    event log records that it was forgotten, without its content."""
    row, label = await _entry(context, payload)
    await services_of(context).memory.forget(row.id)
    context.record(MEMORY_FORGOTTEN, subject=("memory", row.id), project_id=payload.project_id)
    return _memory_item(row, label)


@operation(
    "memory.pin",
    summary="Pin a memory so it is in front of the agents in every run.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def pin_memory(context: Context, payload: EntryRef) -> PinnedView:
    """MEM-6, MEM-1: a pinned entry moves from searched memory to exact memory. A project
    entry becomes a standing order in the chairman's name; a team's or an agent's entry
    becomes a pinned note of that agent (a team's goes to its lead)."""
    row, _ = await _entry(context, payload)
    project = view_of(context).project
    kind, _, key = row.scope.partition(":")
    if kind == "project":
        pin = catalog.get("orders.pin")
        await context.executor.call(
            context, pin, pin.input(project_id=project.id, what=row.text[:ORDER_CHARACTERS])
        )
        seat = await ceo_of(context.session, project.id)
    else:
        wanted = select(Seat).where(Seat.project_id == project.id)
        wanted = (
            wanted.where(Seat.id == key)
            if kind == "agent"
            else wanted.where(Seat.team_id == key, Seat.is_lead)
        )
        found = await context.session.scalar(wanted)
        seat = found or await ceo_of(context.session, project.id)
        note = PinnedNote(
            project_id=project.id, seat_id=seat.id, text=row.text, created_at=context.now
        )
        context.session.add(note)
        await context.session.flush()
        context.record(NOTE_PINNED, subject=("pinned_note", str(note.id)), project_id=project.id)
        await pinned.note_if_over(
            context.session, services_of(context).settings, project, seat, context.now
        )
    show = catalog.get("memory.pinned")
    return await context.executor.call(
        context, show, show.input(project_id=project.id, seat=seat.name)
    )


@operation(
    "memory.preferences",
    summary="Show your own preferences, which agents recall in every project you chair.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def preferences(context: Context, payload: Empty) -> MemoryList:
    """MEM-3: the chairman scope is opt-in, visible and editable. It holds only what its
    owner puts there."""
    scope = recall.person_scope(context.caller.actor_id)
    rows = await services_of(context).memory.listed(scope, LISTED)
    return MemoryList(items=[_memory_item(row, "your preferences") for row in rows])


@operation(
    "memory.prefer",
    summary="Add a preference that agents recall in every project you chair.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def prefer(context: Context, payload: PreferenceInput) -> MemoryItem:
    engine = services_of(context).memory
    scope = recall.person_scope(context.caller.actor_id)
    memory_id = await engine.add(scope, payload.text, recall.metadata(None, "the chairman"))
    context.record(MEMORY_ADDED, subject=("memory", memory_id))
    row = await engine.get(memory_id)
    assert row is not None
    return _memory_item(row, "your preferences")


@operation(
    "memory.forget_preference",
    summary="Forget one of your own preferences.",
    authority=Authority.PERSON,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def forget_preference(context: Context, payload: PreferenceRef) -> MemoryItem:
    """MEM-3, P3: a person forgets only their own preferences."""
    engine = services_of(context).memory
    row = await engine.get(payload.memory_id)
    if row is None or row.scope != recall.person_scope(context.caller.actor_id):
        raise Refusal(
            "memory_not_found",
            f"There is no preference {payload.memory_id} of yours.",
            kind=RefusalKind.NOT_FOUND,
            rule=MEM_3.id,
            hint="List them with `memory preferences`.",
        )
    await engine.forget(row.id)
    context.record(MEMORY_FORGOTTEN, subject=("memory", row.id))
    return _memory_item(row, "your preferences")


@operation(
    "agent.remember",
    summary="Remember a fact for later runs: for yourself, your team or the whole project.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def agent_remember(context: Context, payload: AgentRememberInput) -> MemoryItem:
    """MEM-3, MEM-7, INV-23: an agent writes within its own scopes. In a chat run it may
    write only its own notes; a team's or the project's memory needs a work run."""
    view = await agent_of(context)
    if payload.scope == "agent":
        scope, label = recall.agent_scope(view.seat.id), f"agent {view.seat.name}"
    else:
        work_run_only(view)
        if payload.scope == "team" and view.seat.team_id is None:
            raise Refusal(
                "no_team",
                "You are not in a team, so you have no team memory.",
                rule=MEM_3.id,
                hint="Remember it for yourself or for the project.",
            )
        scope = (
            recall.team_scope(view.seat.team_id or "")
            if payload.scope == "team"
            else recall.project_scope(view.project.id)
        )
        label = payload.scope
    engine = services_of(context).memory
    source = recall.source_of(view.run, view.seat.name, context.now)
    memory_id = await engine.add(scope, payload.text, recall.metadata(view.project.id, source))
    context.record(MEMORY_ADDED, subject=("memory", memory_id), project_id=view.project.id)
    row = await engine.get(memory_id)
    assert row is not None
    return _memory_item(row, label)


@operation(
    "agent.recall",
    summary="Search your memory: yours, your team's, the project's, the chairman's preferences.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def agent_recall(context: Context, payload: RecallInput) -> MemoryList:
    """MEM-3, MEM-5, P3: an agent reads only the scopes it belongs to."""
    view = await agent_of(context)
    services = services_of(context)
    limit = int(
        await services.settings.get(
            context.session,
            Subject(Scope.PROJECT, view.project.id, view.project.type),
            "memory.recall_k",
        )
    )
    scopes = await recall.scopes_for(context.session, view.seat)
    found = await services.memory.search(scopes, payload.query, limit)
    return MemoryList(items=[_memory_item(row, row.scope.split(":", 1)[0]) for row in found])
