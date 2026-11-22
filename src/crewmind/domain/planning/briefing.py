"""What the CEO is told about the plan at the start of each run (EXE-3, PLN-1, PLN-2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.domain.execution.model import SeatKind
from crewmind.domain.planning import cycles, plan_view
from crewmind.domain.planning.model import RequirementState
from crewmind.domain.planning.plan_view import PlanView
from crewmind.domain.projects.model import ProjectType
from crewmind.domain.settings.service import SettingsService
from crewmind.storage.models import Project, Seat

SETTLED = (RequirementState.DECLINED, RequirementState.CUT)
TEXT_SHOWN = 160  # characters of each requirement shown in the briefing


async def section(
    session: AsyncSession,
    settings: SettingsService,
    project: Project,
    seat: Seat,
    now: datetime,
) -> str | None:
    """The plan as the CEO needs it to create work: what is in scope, what is ready, and
    whether the plan fits the budget."""
    if seat.kind != SeatKind.CEO:
        return None
    plan = await plan_view.plan_view(session, settings, project, now)
    if project.type == ProjectType.EXPLORE:
        return _bets(plan)
    if not plan.requirements:
        return (
            "# The plan\n\nThere is no scope yet. Propose requirements with "
            "agent_propose_requirement; a task must serve an accepted one."
        )
    lines: list[str] = []
    for item in plan.requirements:
        if item.state in SETTLED:
            continue
        marks = [item.state, f"stage {item.stage}", f"by the {item.author}"]
        if item.estimate_runs is not None:
            marks.append(f"{item.estimate_runs} runs")
        if item.ready:
            marks.append("ready for work")
        text = item.text if len(item.text) <= TEXT_SHOWN else item.text[:TEXT_SHOWN] + "..."
        line = f"- {item.id} ({', '.join(marks)}): {text}"
        if item.not_ready_because and item.state == RequirementState.ACCEPTED:
            line += f" Not ready: {item.not_ready_because}"
        if item.ruling == "failed" and item.ruling_note:
            line += f" Last ruling: not met. {item.ruling_note}"
        lines.append(line)
    numbers = plan.numbers
    dates = [f"Projection: {plan.pace.projection}."]
    if plan.commitment is not None and plan.commitment.beside_projection is not None:
        dates.append(f"Commitment ({plan.commitment.state}): {plan.commitment.beside_projection}.")
    if plan.target is not None:
        dates.append(
            f"The chairman's target date ({plan.target.source}): "
            f"{plan.target.beside_projection}. A target is a wish, not a pace: do not plan "
            "to it by cutting checks."
        )
    if project.type == ProjectType.OPERATE:
        dates += await _cycle_lines(session, project, plan)
    return (
        "# The plan\n\n"
        + "\n".join(lines)
        + f"\n\n{numbers.remaining_runs} runs of accepted scope remain. Plan tokens: "
        f"{numbers.plan_tokens_text}. {numbers.tokens_before_wrapup:,} tokens are left "
        "before wrap-up.\n"
        + "\n".join(dates)
        + "\nA new task names the ready requirement it serves (`requirement_id`)."
    )


async def _cycle_lines(session: AsyncSession, project: Project, plan: PlanView) -> list[str]:
    """PRJ-8: the open cycle and its due time, and the last 3 cycle narratives verbatim."""
    lines: list[str] = []
    current = next((cycle for cycle in plan.cycles if cycle.state == "open"), None)
    if current is not None:
        lines.append(
            f"Cycle {current.number} is open. Its recurring requirements are due by "
            f"{current.due_at.strftime('%d %b %Y %H:%M UTC')}. Write its narrative with "
            "agent_write_cycle_narrative before then."
        )
    for cycle in await cycles.narratives(session, project.id):
        lines.append(f"Cycle {cycle.number} ({cycle.state}): {cycle.narrative}")
    return lines


def _bets(plan: PlanView) -> str:
    """PRJ-7, SPD-7: the bets with their kill dates, and how much of the time box is left."""
    lines = [
        f"- {bet.id} ({bet.state}, kill date {bet.kill_at.strftime('%d %b %Y %H:%M UTC')}): "
        f"{bet.statement} Killed if: {bet.kill_condition}"
        + (f" Finding: {bet.finding}." if bet.finding else "")
        for bet in plan.bets
    ]
    box = plan.time_box
    closing = (
        ""
        if box is None
        else f"\n\nThe time box ends on {box.ends_at.strftime('%d %b %Y %H:%M UTC')}. New "
        f"bets open until {box.new_bets_until.strftime('%d %b %Y %H:%M UTC')}."
    )
    listed = "\n".join(lines) if lines else "No bet is open. Open one with agent_open_bet."
    return (
        f"# The bets\n\n{listed}{closing}\nA new task names the active bet it serves "
        "(`bet_id`). Every bet ends with a finding: agent_publish_finding."
    )
