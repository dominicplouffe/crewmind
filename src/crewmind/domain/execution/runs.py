"""Runs: queuing, leasing, liveness, endings, retries and revocation (EXE-3 to EXE-10, 7.7).

Runners lease from the database (EXE-5). Every function here is one step that a runner,
the dispatcher or the scheduler takes inside its own transaction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import platform_job
from crewmind.catalog.refusal import Refusal
from crewmind.domain.accounts.credentials import hash_secret, mint_secret
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import notices
from crewmind.domain.execution.model import (
    EXE_10,
    LEASE_TTL,
    LIVE_STATES,
    MAX_ATTEMPTS,
    OPEN_STATES,
    RETRY_BACKOFF,
    RUN_MACHINE,
    RunKind,
    RunState,
    SeatState,
)
from crewmind.domain.projects import lifecycle
from crewmind.domain.projects.model import Hold, ProjectState
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import SettingsService, Subject
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Project, Run, RunRefusal, Seat, Wake

RUN_STATE_CHANGED = event_type("run.state_changed", "A run changed state (7.7).")
RUN_PREFIX = "cm_run_"

RUNNER = platform_job("runner")
REAPER = platform_job("scheduler: reap dead runs")
REVOKER = platform_job("platform: revoke runs")

# Which run kinds may lease in each project state (section 7.1).
ALLOWED: dict[str, frozenset[RunKind]] = {
    ProjectState.RUNNING: frozenset({RunKind.WORK, RunKind.CHAT, RunKind.CHECK}),
    ProjectState.HELD: frozenset({RunKind.CHAT}),
    ProjectState.PAUSED: frozenset({RunKind.CHAT}),
    ProjectState.READY: frozenset({RunKind.CHAT}),
    ProjectState.COMPLETED: frozenset({RunKind.CHAT}),
}


@dataclass(frozen=True)
class Pinned:
    """What a run runs on, fixed at lease (EXE-6)."""

    provider: str
    model: str
    credential_id: str | None
    harness: str
    effort: str


class Wait(Exception):
    """A run cannot be leased yet, for a reason that lifts by itself: a credential cooling
    off, or a provider at its ceiling. The run stays queued and the hold is shown (EXE-4)."""


SeatResolver = Callable[[AsyncSession, Project, Seat], Awaitable[Pinned]]
ProviderGate = Callable[[AsyncSession, str], Awaitable[bool]]


async def _never_saturated(session: AsyncSession, provider: str) -> bool:
    return False


provider_saturated: ProviderGate = _never_saturated
"""Whether a provider is at its install-wide ceiling (LLM-12). Leasing looks past a
saturated provider, so one provider cannot block the others."""


async def _mock_resolver(session: AsyncSession, project: Project, seat: Seat) -> Pinned:
    return Pinned("mock", "mock-1", None, "loop", "medium")


seat_resolver: SeatResolver = _mock_resolver
"""Validates a seat and decides what it runs on (LLM-6, LLM-7). It raises a Refusal when
the seat cannot run. The model gateway replaces the default."""


@dataclass(frozen=True)
class Lease:
    """A leased run and its token. The token exists here once and is stored only as a hash."""

    run_id: str
    project_id: str
    seat_id: str
    kind: RunKind
    token: str
    harness: str
    timeout: timedelta


def subject(project: Project) -> Subject:
    return Subject(Scope.PROJECT, project.id, project.type)


async def at_wall(session: AsyncSession, project_id: str) -> bool:
    holds = await lifecycle.active_holds(session, project_id)
    return any(row.reason == Hold.BUDGET_WALL for row in holds)


async def allowed_kinds(session: AsyncSession, project: Project) -> frozenset[RunKind]:
    """The run kinds this project may lease now (section 7.1). At the wall, none (GOV-3)."""
    kinds = ALLOWED.get(project.state, frozenset())
    if project.state == ProjectState.PAUSED and await at_wall(session, project.id):
        return frozenset()
    return kinds


def _move(
    session: AsyncSession,
    run: Run,
    target: RunState,
    now: datetime,
    *,
    actor: Any = RUNNER,
    detail: str | None = None,
) -> None:
    source = run.state
    RUN_MACHINE.check(source, target)
    run.state = target
    if target not in OPEN_STATES:
        run.ended_at = now
        run.token_revoked = True
        run.end_detail = detail
    append_event(
        session,
        type=RUN_STATE_CHANGED,
        caller=actor,
        at=now,
        subject=("run", run.id),
        project_id=run.project_id,
        before={"state": source},
        after={"state": target},
        detail={"kind": run.kind, "seat": run.seat_id, "attempt": run.attempt, "why": detail},
    )


async def has_open_run(session: AsyncSession, seat_id: str, kind: RunKind = RunKind.WORK) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(Run.seat_id == seat_id, Run.kind == kind, Run.state.in_(OPEN_STATES))
    )
    return bool(count)


async def queue(
    session: AsyncSession,
    seat: Seat,
    kind: RunKind,
    reasons: list[str],
    now: datetime,
    *,
    wake: Wake | None = None,
    attempt: int = 1,
    not_before: datetime | None = None,
) -> Run:
    """Queue a run for a wake (7.7). Each run records why it was woken (EXE-4)."""
    if wake is None:
        wake = Wake(
            project_id=seat.project_id, seat_id=seat.id, kind=kind, reasons=reasons, created_at=now
        )
        session.add(wake)
        await session.flush()
    RUN_MACHINE.check("(new)", RunState.QUEUED)
    run = Run(
        project_id=seat.project_id,
        seat_id=seat.id,
        wake_id=wake.id,
        kind=kind,
        state=RunState.QUEUED,
        attempt=attempt,
        not_before=not_before,
        queued_at=now,
    )
    session.add(run)
    await session.flush()
    append_event(
        session,
        type=RUN_STATE_CHANGED,
        caller=platform_job("dispatcher"),
        at=now,
        subject=("run", run.id),
        project_id=run.project_id,
        after={"state": RunState.QUEUED},
        detail={"kind": kind, "seat": seat.id, "attempt": attempt, "reasons": reasons},
    )
    return run


async def lease(
    session: AsyncSession,
    settings: SettingsService,
    runner_id: str,
    capacity: int,
    now: datetime,
) -> list[Lease]:
    """Lease up to `capacity` queued runs to one runner (EXE-5, INV-12, INV-13).

    On Postgres the rows are locked with skip-locking, so two runners never take one run.
    Runs queued at the same instant are taken in the order their seats were created.
    A run whose project no longer allows its kind is dropped. At the wall nothing is leased.
    A seat that cannot run fails here, before any sandbox starts or token is spent (LLM-6).
    """
    if capacity <= 0:
        return []
    candidates = await session.scalars(
        select(Run)
        .join(Seat, Seat.id == Run.seat_id)
        .where(Run.state == RunState.QUEUED)
        .where((Run.not_before.is_(None)) | (Run.not_before <= now))
        .order_by(Run.queued_at, Seat.created_at, Seat.name, Run.id)
        .with_for_update(skip_locked=True, of=Run)
    )
    leases: list[Lease] = []
    for run in candidates:
        if len(leases) >= capacity:
            break
        project = await session.get(Project, run.project_id)
        seat = await session.get(Seat, run.seat_id)
        assert project is not None
        assert seat is not None
        kind = RunKind(run.kind)
        if kind not in await allowed_kinds(session, project) or seat.state != SeatState.ACTIVE:
            _move(session, run, RunState.DROPPED, now, detail=f"the project is {project.state}")
            continue
        values = await settings.effective(session, subject(project))
        if kind is RunKind.WORK:
            live = await session.scalar(
                select(func.count())
                .select_from(Run)
                .where(
                    Run.project_id == project.id,
                    Run.kind == RunKind.WORK,
                    Run.state.in_(LIVE_STATES),
                )
            )
            allowed = await concurrency_limit(session, project.id, int(values["run.concurrency"]))
            if (live or 0) >= allowed:
                continue
        refusal: Refusal | None = None
        pinned: Pinned | None = None
        try:
            pinned = await seat_resolver(session, project, seat)
            if await provider_saturated(session, pinned.provider):
                continue
        except Wait:
            continue
        except Refusal as refused:
            refusal = refused
        plain, digest = mint_secret(RUN_PREFIX)
        run.leased_by = runner_id
        run.leased_at = now
        run.heartbeat_at = now
        run.token_hash = digest
        run.max_tokens = int(values["run.max_tokens"]) or None
        _move(session, run, RunState.LEASED, now)
        if refusal is not None or pinned is None:
            assert refusal is not None
            _move(session, run, RunState.FAILED, now, detail=refusal.envelope.message)
            await conversation.platform_line(
                session,
                project.id,
                f"{seat.name} cannot run: {refusal.envelope.message}",
                now,
                detail={"kind": "seat check failed", "seat": seat.name},
            )
            continue
        run.provider, run.model = pinned.provider, pinned.model
        run.credential_id, run.harness, run.effort = (
            pinned.credential_id,
            pinned.harness,
            pinned.effort,
        )
        await session.flush()
        leases.append(
            Lease(
                run_id=run.id,
                project_id=project.id,
                seat_id=seat.id,
                kind=kind,
                token=plain,
                harness=pinned.harness,
                timeout=timedelta(seconds=int(values["run.timeout"])),
            )
        )
    return leases


async def _held(session: AsyncSession, run_id: str, runner_id: str) -> Run | None:
    """The run, if this runner still holds it live. A reaped or revoked run is not (INV-15)."""
    run = await session.get(Run, run_id, with_for_update=True)
    if run is None or run.leased_by != runner_id or run.state not in LIVE_STATES:
        return None
    return run


async def started(session: AsyncSession, run_id: str, runner_id: str, now: datetime) -> bool:
    run = await _held(session, run_id, runner_id)
    if run is None or run.state != RunState.LEASED:
        return False
    run.started_at = now
    run.heartbeat_at = now
    _move(session, run, RunState.RUNNING, now)
    return True


async def heartbeat(session: AsyncSession, run_id: str, runner_id: str, now: datetime) -> bool:
    """Record that a run is alive. False tells the runner to stop its sandbox: the run was
    revoked, reaped or ended (EXE-7, EXE-9)."""
    run = await _held(session, run_id, runner_id)
    if run is None or run.token_revoked:
        return False
    run.heartbeat_at = now
    return True


async def finish(
    session: AsyncSession,
    run_id: str,
    runner_id: str,
    now: datetime,
    *,
    failed: bool,
    detail: str | None = None,
) -> bool:
    """End a run normally or as failed. A late result from a worker that no longer holds
    the run changes nothing (INV-15)."""
    run = await _held(session, run_id, runner_id)
    if run is None or run.state != RunState.RUNNING:
        return False
    await _end(session, run, RunState.FAILED if failed else RunState.FINISHED, now, detail=detail)
    return True


async def _configured_concurrency(session: AsyncSession, project_id: str, configured: int) -> int:
    return configured


concurrency_limit: Callable[[AsyncSession, str, int], Awaitable[int]] = _configured_concurrency
"""The concurrency a project may use now. The work domain lowers it while the project is
spinning (GOV-7)."""

FailedHook = Callable[[AsyncSession, Run, datetime], Awaitable[None]]
failed_hooks: list[FailedHook] = []
"""Steps run when a run fails or is reaped. The conversation domain counts a chat run's
failure as an involuntary restart of its chat session (MSG-11)."""


async def _end(
    session: AsyncSession,
    run: Run,
    target: RunState,
    now: datetime,
    *,
    actor: Any = RUNNER,
    detail: str | None = None,
) -> None:
    _move(session, run, target, now, actor=actor, detail=detail)
    retryable = target in (RunState.FAILED, RunState.REAPED)
    # After the last attempt the notices are not given back again: the wake is given up
    # in the open (EXE-8), not retried for ever through a fresh wake.
    await notices.settle(session, run.id, failed=retryable and run.attempt < MAX_ATTEMPTS)
    if retryable:
        await _retry(session, run, now)
        for hook in failed_hooks:
            await hook(session, run, now)


async def _retry(session: AsyncSession, run: Run, now: datetime) -> None:
    """EXE-8: up to 3 attempts, 30 seconds x attempt apart, each a new run of the same wake.
    If no attempt reached a model, the messages it was given are unread again."""
    if not run.reached_model and run.delivered:
        for channel_id, (before, _) in run.delivered.items():
            row = await conversation.read_position(session, channel_id, "agent", run.seat_id)
            if row > before:
                await _rewind(session, channel_id, run.seat_id, int(before))
    seat = await session.get(Seat, run.seat_id)
    wake = await session.get(Wake, run.wake_id)
    assert seat is not None
    assert wake is not None
    if run.attempt >= MAX_ATTEMPTS:
        await conversation.platform_line(
            session,
            run.project_id,
            f"{seat.name}'s run failed {MAX_ATTEMPTS} times and was given up: "
            f"{run.end_detail or 'no detail'}.",
            now,
            detail={"kind": "run gave up", "seat": seat.name},
        )
        return
    await queue(
        session,
        seat,
        RunKind(run.kind),
        list(wake.reasons),
        now,
        wake=wake,
        attempt=run.attempt + 1,
        not_before=now + RETRY_BACKOFF * run.attempt,
    )


async def _rewind(session: AsyncSession, channel_id: str, seat_id: str, position: int) -> None:
    from crewmind.storage.models import ReadPosition

    row = await session.scalar(
        select(ReadPosition).where(
            ReadPosition.channel_id == channel_id,
            ReadPosition.reader_kind == "agent",
            ReadPosition.reader_id == seat_id,
        )
    )
    if row is not None:
        row.last_read = position


async def reap(session: AsyncSession, settings: SettingsService, now: datetime) -> list[str]:
    """Reap live runs whose heartbeat is stale or that have outlived `run.timeout` (EXE-7).
    Reaping revokes the token; tokens the gateway already metered stay on the ledger."""
    reaped: list[str] = []
    rows = await session.scalars(
        select(Run).where(Run.state.in_(LIVE_STATES)).with_for_update(skip_locked=True)
    )
    for run in rows:
        project = await session.get(Project, run.project_id)
        assert project is not None
        timeout = timedelta(
            seconds=int(await settings.get(session, subject(project), "run.timeout"))
        )
        last = run.heartbeat_at or run.leased_at or run.queued_at
        stale = now - last > LEASE_TTL
        too_long = run.started_at is not None and now - run.started_at > timeout
        if stale or too_long:
            why = "its heartbeat stopped" if stale else f"it ran past {timeout}"
            await _end(session, run, RunState.REAPED, now, actor=REAPER, detail=why)
            reaped.append(run.id)
    return reaped


async def revoke(
    session: AsyncSession,
    project_id: str,
    now: datetime,
    *,
    kinds: frozenset[RunKind],
    cause: str,
    live_may_finish: bool = False,
) -> None:
    """Drop queued runs and, unless they may finish, kill live ones (EXE-9, PRJ-2). The
    runner sees the revocation at its next heartbeat and stops the sandbox."""
    rows = await session.scalars(
        select(Run).where(
            Run.project_id == project_id, Run.kind.in_(kinds), Run.state.in_(OPEN_STATES)
        )
    )
    for run in rows:
        if run.state == RunState.QUEUED:
            _move(session, run, RunState.DROPPED, now, actor=REVOKER, detail=cause)
        elif not live_may_finish:
            _move(session, run, RunState.KILLED, now, actor=REVOKER, detail=cause)
            await notices.settle(session, run.id, failed=True)


async def kill(session: AsyncSession, run: Run, now: datetime, *, caller: Any) -> None:
    """Kill one run on a person's request (7.7). Its notices are given back."""
    if run.state == RunState.QUEUED:
        _move(session, run, RunState.DROPPED, now, actor=caller, detail="interrupted")
        return
    _move(session, run, RunState.KILLED, now, actor=caller, detail="interrupted")
    await notices.settle(session, run.id, failed=True)


async def _on_hold(session: AsyncSession, project: Project, now: datetime, hold: Hold) -> None:
    """Live runs may finish only at the budget wall (GOV-3); otherwise their tokens are
    revoked (EXE-9)."""
    kinds = frozenset(RunKind) - await allowed_kinds(session, project)
    await revoke(
        session,
        project.id,
        now,
        kinds=kinds,
        cause=f"the project is {project.state}",
        live_may_finish=hold is Hold.BUDGET_WALL,
    )


async def _on_stop(session: AsyncSession, project: Project, now: datetime) -> None:
    await revoke(session, project.id, now, kinds=frozenset(RunKind), cause="the project stopped")


lifecycle.hold_hooks.append(_on_hold)
lifecycle.stop_hooks.append(_on_stop)


async def run_for_token(session: AsyncSession, token: str | None) -> Run | None:
    """The live run a token belongs to. A token works only while its run is leased or
    running and not revoked (INV-4)."""
    if not token or not token.startswith(RUN_PREFIX):
        return None
    run = await session.scalar(select(Run).where(Run.token_hash == hash_secret(token)))
    if run is None or run.token_revoked or run.state not in LIVE_STATES:
        return None
    return run


async def record_refusal(
    session: AsyncSession,
    settings: SettingsService,
    run_id: str,
    operation: str,
    refusal: Refusal,
    now: datetime,
) -> Refusal:
    """Count a refusal against the run (EXE-10). At `refusal.cap` the token is revoked and
    the run ends as terminated; the refusal returned says so."""
    run = await session.get(Run, run_id, with_for_update=True)
    assert run is not None
    envelope = refusal.envelope
    session.add(
        RunRefusal(
            run_id=run.id,
            operation=operation,
            code=envelope.code,
            rule=envelope.rule,
            message=envelope.message,
            at=now,
        )
    )
    run.refusals += 1
    project = await session.get(Project, run.project_id)
    assert project is not None
    cap = int(await settings.get(session, subject(project), "refusal.cap"))
    if run.refusals < cap or run.state != RunState.RUNNING:
        return refusal
    _move(
        session,
        run,
        RunState.TERMINATED,
        now,
        actor=REVOKER,
        detail=f"{run.refusals} refusals reached the cap of {cap}",
    )
    await notices.settle(session, run.id, failed=False)
    return Refusal(
        envelope.code,
        f"{envelope.message} This was refusal {run.refusals} of {cap} in this run, so the "
        "run has been ended and its token revoked. Rephrasing is not a strategy.",
        kind=envelope.kind,
        rule=EXE_10.id,
        hint=envelope.hint,
    )


async def note_success(session: AsyncSession, run_id: str, operation: str) -> None:
    """A later success on a refused operation marks the refusal "got past" (EXE-10, NFR-20)."""
    rows = await session.scalars(
        select(RunRefusal).where(
            RunRefusal.run_id == run_id,
            RunRefusal.operation == operation,
            RunRefusal.got_past.is_(False),
        )
    )
    for row in rows:
        row.got_past = True
