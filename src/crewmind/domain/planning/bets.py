"""Explore: bets, the time box, findings and the findings report (PRJ-7, SPD-7, 7.4)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.artifacts import service as artifacts
from crewmind.domain.budget import service as budget
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution import notices
from crewmind.domain.execution.roster import ceo_of
from crewmind.domain.planning import authority, completion, projection, readiness, reserve
from crewmind.domain.planning.authority import Actor
from crewmind.domain.planning.model import BET_MACHINE, FINDINGS, BetState
from crewmind.domain.planning.readiness import PLANNING_JOB
from crewmind.domain.projects.model import ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.domain.work import tasks
from crewmind.domain.work.model import OPEN_STATES, TaskState
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Artifact, Bet, Evidence, Project, Seat, Task

SPD_7 = rules.register(
    Rule("SPD-7", "Explore is time-boxed: no new bet in the final 20% of the time box.")
)
PRJ_7 = rules.register(
    Rule("PRJ-7", "A bet ends with a finding; confirmed needs verified outside evidence.")
)
BET_CHANGED = event_type("bet.state_changed", "A bet changed state (7.4).")
REPORT_ASSEMBLED = event_type("findings.report_assembled", "The findings report was built.")
PROMOTED = event_type("project.promoted", "An Explore project was promoted to a Deliver draft.")
B = BetState
LAST_SHARE = 0.2  # SPD-7: the final 20% of the time box
REASON_MIN_CHARACTERS = 10  # 7.4: an extension carries a reason
FINDING_MIN_CHARACTERS = 20  # PRJ-7: a finding says what was learned
REPORT = "findings-report.md"


def _move(
    session: AsyncSession,
    bet: Bet,
    target: BetState,
    caller: Caller,
    now: datetime,
    detail: dict[str, object] | None = None,
) -> None:
    """The one place a bet changes state (7.4)."""
    BET_MACHINE.check(bet.state, target)
    before = bet.state
    bet.state = target
    append_event(
        session,
        type=BET_CHANGED,
        caller=caller,
        at=now,
        subject=("bet", str(bet.id)),
        project_id=bet.project_id,
        before={"state": before},
        after={"state": target},
        detail=detail,
    )


async def get(session: AsyncSession, project_id: str, bet_id: int) -> Bet:
    bet = await session.get(Bet, bet_id)
    if bet is None or bet.project_id != project_id:
        raise Refusal(
            "bet_not_found", f"There is no bet {bet_id} in this project.",
            kind=RefusalKind.NOT_FOUND,
        )  # fmt: skip
    return bet


async def time_box(
    session: AsyncSession, settings: SettingsService, project: Project, now: datetime
) -> tuple[datetime, datetime] | None:
    """When the time box began and when it ends: `explore.timebox` from the first start."""
    started = await projection.started_at(session, project.id)
    if started is None:
        return None
    length = int(await settings.get(session, authority.subject(project), "explore.timebox"))
    return started, started + timedelta(seconds=length)


async def open_bet(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    actor: Actor,
    *,
    statement: str,
    kill_condition: str,
    window_hours: int | None,
    now: datetime,
) -> Bet:
    """7.4, SPD-7, GOV-3, GOV-10: the CEO opens a bet with a kill condition and a kill
    date inside the time box. Refused in the final 20% of the time box, in wrap-up mode
    and after a reserve draw."""
    if project.type != ProjectType.EXPLORE:
        raise Refusal(
            "bets_are_for_explore",
            "Only an Explore project has bets. This project has requirements.",
            rule=PRJ_7.id,
        )
    box = await time_box(session, settings, project, now)
    assert box is not None
    started, ends = box
    last_fifth = ends - (ends - started) * LAST_SHARE
    if now >= last_fifth:
        raise Refusal(
            "time_box_nearly_over",
            f"The time box ends on {ends.strftime('%d %b %Y %H:%M UTC')} and its final 20% "
            f"began on {last_fifth.strftime('%d %b %Y %H:%M UTC')}. No new bet is opened now.",
            rule=SPD_7.id,
            hint="Write the findings for the bets that are open.",
        )
    if await reserve.drawn_now(session, settings, project, now):
        raise Refusal(
            "reserve_funds_findings_only",
            "The CEO reserve is drawn. It funds findings for bets already active; no bet is "
            "opened.",
            rule=reserve.GOV_10.id,
        )
    wrapup = await readiness.in_wrapup(session, settings, project, now)
    if wrapup is not None:
        raise Refusal(
            "wrap_up_mode",
            f"The project is in wrap-up mode ({budget.arithmetic(wrapup)}), so new bets are "
            "refused.",
            rule=budget.GOV_3.id,
            hint="Write the findings for the bets that are open.",
        )
    default = int(await settings.get(session, authority.subject(project), "bet.window"))
    window = timedelta(hours=window_hours) if window_hours else timedelta(seconds=default)
    kill_at = now + window
    if kill_at > ends:
        raise Refusal(
            "bet_outlives_the_time_box",
            f"This bet would run until {kill_at.strftime('%d %b %Y %H:%M UTC')}, after the "
            f"time box ends on {ends.strftime('%d %b %Y %H:%M UTC')}.",
            rule=SPD_7.id,
            hint="Give a shorter window.",
        )
    bet = Bet(
        project_id=project.id,
        statement=statement.strip(),
        kill_condition=kill_condition.strip(),
        kill_at=kill_at,
        state="(new)",
        extended=False,
        opened_at=now,
    )
    session.add(bet)
    await session.flush()
    _move(session, bet, B.ACTIVE, actor.caller, now, {"kill_at": kill_at.isoformat()})
    await conversation.platform_line(
        session,
        project.id,
        f"Bet {bet.id} opened: {bet.statement} It is killed if: {bet.kill_condition} "
        f"Kill date: {kill_at.strftime('%d %b %Y %H:%M UTC')}.",
        now,
        detail={"kind": "bet opened", "bet": bet.id},
    )
    return bet


async def expire(session: AsyncSession, project: Project, now: datetime) -> list[Bet]:
    """PRJ-7, 7.4: a bet expires at its kill date and its open tasks block."""
    due = list(
        await session.scalars(
            select(Bet)
            .where(Bet.project_id == project.id, Bet.state == B.ACTIVE, Bet.kill_at <= now)
            .order_by(Bet.id)
        )
    )
    if not due:
        return []
    ceo = await ceo_of(session, project.id)
    for bet in due:
        _move(session, bet, B.EXPIRED, PLANNING_JOB, now)
        why = f"Bet {bet.id} expired at its kill date."
        rows = await session.scalars(
            select(Task).where(
                Task.bet_id == bet.id, Task.state.in_([TaskState.READY, TaskState.CLAIMED])
            )
        )
        for task in rows:
            task.reason = why
            tasks.move(session, task, TaskState.BLOCKED, PLANNING_JOB, now, {"why": why})
        text = (
            f"Bet {bet.id} reached its kill date with no finding: {bet.statement} Its open "
            "tasks are blocked. Publish its finding (confirmed, killed or inconclusive)."
        )
        notices.notify(session, project.id, ceo.id, "bet expired", text, now, urgent=True)
        await conversation.platform_line(
            session, project.id, text + " The chairman may extend it once.", now,
            detail={"kind": "bet expired", "bet": bet.id},
        )  # fmt: skip
    return due


async def extend(
    session: AsyncSession,
    project: Project,
    actor: Actor,
    bet: Bet,
    until: datetime,
    reason: str,
    now: datetime,
) -> None:
    """PRJ-7, 7.4: the chairman may extend an expired bet once, with a reason, to a
    future date."""
    assert actor.is_chairman
    if bet.extended:
        raise Refusal(
            "bet_already_extended",
            f"Bet {bet.id} was already extended once. It now needs its finding.",
            rule=PRJ_7.id,
        )
    if len(reason.strip()) < REASON_MIN_CHARACTERS:
        raise Refusal(
            "reason_too_short",
            f"Give a reason of at least {REASON_MIN_CHARACTERS} characters.",
            rule=PRJ_7.id,
        )
    if until <= now:
        raise Refusal("date_in_the_past", "Extend the bet to a time in the future.", rule=PRJ_7.id)
    _move(session, bet, B.ACTIVE, actor.caller, now, {"until": until.isoformat()})
    bet.extended, bet.extension_reason, bet.kill_at = True, reason.strip(), until
    ceo = await ceo_of(session, project.id)
    notices.notify(
        session, project.id, ceo.id, "bet extended",
        f"The chairman extended bet {bet.id} to {until.strftime('%d %b %Y %H:%M UTC')}: "
        f"{reason.strip()} Tasks blocked at its expiry stay blocked; create new ones.",
        now, urgent=True,
    )  # fmt: skip


async def publish_finding(
    session: AsyncSession,
    settings: SettingsService,
    blobs: artifacts.BlobStore,
    project: Project,
    seat: Seat,
    caller: Caller,
    bet: Bet,
    *,
    result: BetState,
    text: str,
    evidence: list[int],
    now: datetime,
) -> str:
    """PRJ-7: every ended bet gets a finding, written by the CEO and published as an
    artifact: confirmed, killed or inconclusive, with its evidence. Evidence counts only
    once verified, and a confirmed bet needs some. Returns the artifact's name."""
    if result not in FINDINGS:
        raise Refusal("not_a_finding", "A finding is confirmed, killed or inconclusive.")
    if len(text.strip()) < FINDING_MIN_CHARACTERS:
        raise Refusal(
            "finding_too_short",
            f"A finding says what was learned, in at least {FINDING_MIN_CHARACTERS} characters.",
            rule=PRJ_7.id,
        )
    rows = list(
        await session.scalars(
            select(Evidence)
            .where(Evidence.project_id == project.id, Evidence.id.in_(evidence or [0]))
            .order_by(Evidence.id)
        )
    )
    unverified = sorted(set(evidence) - {row.id for row in rows if row.state == "verified"})
    if unverified:
        listed = ", ".join(str(one) for one in unverified)
        raise Refusal(
            "evidence_not_verified",
            f"Evidence {listed} is not verified, so it cannot support a finding.",
            rule=PRJ_7.id,
            hint="Cite only evidence the platform has verified.",
        )
    if result == B.CONFIRMED and not rows:
        raise Refusal(
            "confirmed_needs_evidence",
            "A bet is confirmed only with verified outside evidence.",
            rule=PRJ_7.id,
            hint="File evidence and wait for the platform to verify it, or publish the "
            "finding as inconclusive.",
        )
    _move(session, bet, result, caller, now, {"evidence": [row.id for row in rows]})
    bet.ended_at = now
    name = f"finding-bet-{bet.id}.md"
    cited = "\n".join(f"- {row.url}: {row.claim}" for row in rows) or "- none"
    body = (
        f"# Finding for bet {bet.id}: {result}\n\n**The bet.** {bet.statement}\n\n"
        f"**Killed if.** {bet.kill_condition}\n\n**What was found.** {text.strip()}\n\n"
        f"**Verified evidence.**\n{cited}\n"
    )
    await artifacts.add_version(
        session,
        settings,
        blobs,
        project,
        name=name,
        content=body.encode(),
        kind=artifacts.Kind.REPORT,
        audience=artifacts.Audience.CHAIRMAN,
        author=artifacts.Author("agent", seat.id, seat.name, caller.run_id, seat.display_name),
        caller=caller,
        now=now,
        media_type="text/markdown",
    )
    bet.finding = name
    why = f"Bet {bet.id} ended: {result}."
    for task in await session.scalars(
        select(Task).where(Task.bet_id == bet.id, Task.state.in_(OPEN_STATES))
    ):
        if task.state in (TaskState.READY, TaskState.CLAIMED, TaskState.BLOCKED):
            task.reason = why
            tasks.move(session, task, TaskState.KILLED, caller, now, {"why": why})
    return name


async def assemble_report(
    session: AsyncSession,
    settings: SettingsService,
    blobs: artifacts.BlobStore,
    project: Project,
    now: datetime,
    *,
    why: str,
) -> str:
    """PRJ-7: the platform assembles the findings report from the findings as they are."""
    bets = list(
        await session.scalars(select(Bet).where(Bet.project_id == project.id).order_by(Bet.id))
    )
    parts = [f"# Findings report: {project.name}", f"Written by the platform because {why}.", ""]
    for bet in bets:
        parts.append(f"## Bet {bet.id}: {bet.state}")
        parts.append(bet.statement)
        if bet.finding is None:
            parts.append("No finding was published for this bet.")
            parts.append("")
            continue
        artifact = await artifacts.named(session, project.id, bet.finding)
        assert artifact is not None
        history = await artifacts.versions(session, artifact)
        parts.append(blobs.read(history[-1].content_hash).decode().split("\n", 1)[1].strip())
        parts.append("")
    if not bets:
        parts.append("No bet was opened.")
    await artifacts.add_version(
        session,
        settings,
        blobs,
        project,
        name=REPORT,
        content="\n".join(parts).encode(),
        kind=artifacts.Kind.REPORT,
        audience=artifacts.Audience.CHAIRMAN,
        author=artifacts.Author("platform", PLANNING_JOB.actor_id, "crewmind"),
        caller=PLANNING_JOB,
        now=now,
        media_type="text/markdown",
    )
    append_event(
        session,
        type=REPORT_ASSEMBLED,
        caller=PLANNING_JOB,
        at=now,
        subject=("project", project.id),
        project_id=project.id,
        after={"artifact": REPORT, "bets": len(bets)},
        detail={"why": why},
    )
    return REPORT


async def close_time_box(
    session: AsyncSession,
    settings: SettingsService,
    blobs: artifacts.BlobStore,
    project: Project,
    now: datetime,
) -> bool:
    """PRJ-7, SPD-7: when the time box ends the platform assembles the findings report,
    once, and tells the chairman it is theirs to end the project."""
    if project.type != ProjectType.EXPLORE:
        return False
    box = await time_box(session, settings, project, now)
    if box is None or now < box[1]:
        return False
    already = await session.scalar(
        select(Artifact.id).where(Artifact.project_id == project.id, Artifact.name == REPORT)
    )
    if already is not None:
        return False
    await assemble_report(session, settings, blobs, project, now, why="the time box ended")
    await conversation.platform_line(
        session,
        project.id,
        f"The time box has ended. The findings report is {REPORT}. End the project, or "
        "promote it to a Deliver project.",
        now,
        detail={"kind": "time box ended"},
    )
    return True


async def report_text(
    session: AsyncSession, blobs: artifacts.BlobStore, project: Project
) -> str | None:
    """The newest findings report, or None when none was assembled."""
    artifact = await artifacts.named(session, project.id, REPORT)
    if artifact is None:
        return None
    history = await artifacts.versions(session, artifact)
    return blobs.read(history[-1].content_hash).decode() if history else None


async def add_findings(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    now: datetime,
    receipt: dict[str, object],
) -> None:
    """An Explore receipt lists each bet with how it ended."""
    if project.type != ProjectType.EXPLORE:
        return
    rows = await session.scalars(select(Bet).where(Bet.project_id == project.id).order_by(Bet.id))
    receipt["bets"] = [
        {"id": bet.id, "statement": bet.statement, "state": bet.state, "finding": bet.finding}
        for bet in rows
    ]
    receipt["findings_report"] = REPORT


completion.receipt_parts.append(add_findings)
