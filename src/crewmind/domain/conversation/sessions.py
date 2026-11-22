"""Chat sessions: an agent's warm chat, which holds many chat runs, one per reply (MSG-11,
section 7.17).

A session is a record, not a run: it is metered through its runs and is never reaped. It
stays warm for `chat.keep_warm` after the last message, restarts when what the agent runs
on changes, and is held after repeated involuntary restarts so a broken chat stops
costing tokens.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import platform_job
from crewmind.catalog.state_machine import NEW, StateMachine
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import runs
from crewmind.domain.execution.model import RunKind
from crewmind.domain.memory import pinned
from crewmind.domain.models.service import paying_credential
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import ChatSession, Message, Project, Role, Run, Seat

SESSION_CHANGED = event_type("chat_session.state_changed", "A chat session changed state.")
SESSION_RESTARTED = event_type("chat_session.restarted", "A chat session restarted (MSG-11).")
SESSIONS_JOB = platform_job("dispatcher: chat sessions")

HOLD_AFTER_RESTARTS = 3  # MSG-11: restarts are held after 3 involuntary ones ...
RESTART_WINDOW = timedelta(minutes=10)  # ... in 10 minutes


class SessionState(StrEnum):
    WARM = "warm"
    HELD = "held"
    CLOSED = "closed"


S = SessionState
CHAT_SESSION_MACHINE = StateMachine(
    "chat session",
    "7.17-chat-session",
    [(NEW, S.WARM), (S.WARM, S.HELD), (S.HELD, S.WARM), (S.WARM, S.CLOSED)],
)


def _move(
    session: AsyncSession, row: ChatSession, target: SessionState, now: datetime, why: str
) -> None:
    CHAT_SESSION_MACHINE.check(row.state, target)
    before = row.state
    row.state = target
    append_event(
        session,
        type=SESSION_CHANGED,
        caller=SESSIONS_JOB,
        at=now,
        subject=("chat_session", str(row.id)),
        project_id=row.project_id,
        before={"state": before},
        after={"state": target},
        detail={"why": why},
    )


async def fingerprint(session: AsyncSession, project: Project, seat: Seat, now: datetime) -> str:
    """What a session restarts on: the credential that pays, the role's grants and brief,
    and the standing orders (MSG-11)."""
    role = await session.get(Role, seat.role_id)
    credential = await paying_credential(session, project, seat, now)
    current = await pinned.pinned_for(session, project, seat)
    parts = {
        "credential": credential.id if credential else None,
        "model": seat.override_model,
        "grants": sorted(str(tool) for tool in role.tools) if role else [],
        "brief": role.charter if role else "",
        "orders": [order.text for order in current.orders],
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


async def current(session: AsyncSession, seat_id: str) -> ChatSession | None:
    """The agent's open session, if it has one."""
    return await session.scalar(
        select(ChatSession)
        .where(ChatSession.seat_id == seat_id, ChatSession.state != S.CLOSED)
        .order_by(ChatSession.id.desc())
        .limit(1)
    )


async def on_message(
    session: AsyncSession, project: Project, seat: Seat, message: Message, now: datetime
) -> bool:
    """A message addressed to the agent starts or reuses its session. Returns whether a
    chat run may start: not while the session is held and this is the same message."""
    mark = await fingerprint(session, project, seat, now)
    row = await current(session, seat.id)
    if row is None:
        CHAT_SESSION_MACHINE.check(NEW, S.WARM)
        row = ChatSession(
            project_id=project.id,
            seat_id=seat.id,
            state=S.WARM,
            fingerprint=mark,
            restarts=[],
            opened_at=now,
            last_message_at=now,
        )
        session.add(row)
        await session.flush()
        append_event(
            session,
            type=SESSION_CHANGED,
            caller=SESSIONS_JOB,
            at=now,
            subject=("chat_session", str(row.id)),
            project_id=project.id,
            after={"state": S.WARM},
        )
        return True
    if row.state == S.HELD:
        if row.held_at_message is not None and message.id <= row.held_at_message:
            return False
        _move(session, row, S.WARM, now, "a new message after the hold")
        row.restarts, row.held_reason, row.held_at_message = [], None, None
    if row.fingerprint != mark:
        row.fingerprint = mark
        row.generation += 1
        append_event(
            session,
            type=SESSION_RESTARTED,
            caller=SESSIONS_JOB,
            at=now,
            subject=("chat_session", str(row.id)),
            project_id=project.id,
            detail={"why": "its credential, grants, brief or standing orders changed"},
        )
    row.last_message_at = now
    return True


async def _on_failed_run(session: AsyncSession, run: Run, now: datetime) -> None:
    """MSG-11: a chat run that fails or is reaped is an involuntary restart of its session.
    The third within 10 minutes holds the session and tells the chairman why."""
    if run.kind != RunKind.CHAT:
        return
    row = await current(session, run.seat_id)
    if row is None or row.state != S.WARM:
        return
    recent = [
        stamp for stamp in row.restarts if datetime.fromisoformat(stamp) > now - RESTART_WINDOW
    ]
    row.restarts = [*recent, now.isoformat()]
    row.generation += 1
    append_event(
        session,
        type=SESSION_RESTARTED,
        caller=SESSIONS_JOB,
        at=now,
        subject=("chat_session", str(row.id)),
        project_id=row.project_id,
        detail={"why": run.end_detail or f"its chat run was {run.state}", "involuntary": True},
    )
    if len(row.restarts) < HOLD_AFTER_RESTARTS:
        return
    seat = await session.get(Seat, run.seat_id)
    name = seat.name if seat else "The agent"
    reason = run.end_detail or f"its chat run was {run.state}"
    row.held_reason = reason
    target = await conversation.channel(session, row.project_id, conversation.PROJECT_CHAT)
    row.held_at_message = await session.scalar(
        select(Message.id)
        .where(Message.channel_id == target.id)
        .order_by(Message.id.desc())
        .limit(1)
    )
    _move(session, row, S.HELD, now, reason)
    await conversation.platform_line(
        session,
        row.project_id,
        f"{name}'s chat is held: it failed {HOLD_AFTER_RESTARTS} times in "
        f"{int(RESTART_WINDOW.total_seconds() // 60)} minutes ({reason}). Nothing "
        "more is spent on it. Send a new message once the cause is fixed.",
        now,
        detail={"kind": "chat session held"},
    )


runs.failed_hooks.append(_on_failed_run)


async def close_idle(session: AsyncSession, settings: SettingsService, now: datetime) -> None:
    """Section 7.17: a warm session closes when `chat.keep_warm` passes with no message, so
    an idle chat costs nothing (P8)."""
    keep = timedelta(
        seconds=int(
            await settings.get(session, Subject(Scope.INSTALL, INSTALL_SUBJECT), "chat.keep_warm")
        )
    )
    rows = await session.scalars(
        select(ChatSession).where(
            ChatSession.state == S.WARM, ChatSession.last_message_at <= now - keep
        )
    )
    for row in rows:
        _move(session, row, S.CLOSED, now, "no message for `chat.keep_warm`")
        row.closed_at = now


async def warm_seats(session: AsyncSession) -> dict[str, int]:
    """Each agent with a warm session and that session's generation. A runner keeps a warm
    process only for these, and replaces one whose generation has moved on."""
    rows = await session.execute(
        select(ChatSession.seat_id, ChatSession.generation).where(ChatSession.state == S.WARM)
    )
    return {seat_id: generation for seat_id, generation in rows.all()}
