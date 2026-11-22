"""The rehearsal report: what a drill found, in plain words (RHS-2, RHS-3)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

NOT_QUALITY = (
    "A rehearsal checks that the project is set up to run under the rules. It does not "
    "predict how good the work will be."
)
NOT_EXERCISED = (
    "What real agents write, and whether it is any good.",
    "Any command a real success test would run: the drill's own tests are read by a reviewer.",
    "Alerts, email and anything outside this machine.",
)
SAMPLED = "audit sample"


class Step(BaseModel):
    what: str
    after_seconds: float | None = Field(
        description="Drill time since the start. Empty when the step did not happen."
    )
    happened: bool


class Wait(BaseModel):
    kind: str
    times: int


class RuleHit(BaseModel):
    rule: str
    code: str
    times: int
    message: str


class Estimate(BaseModel):
    runs_to_first_close: int
    tokens_to_first_close: int | None
    basis: str


class RehearsalReport(BaseModel):
    verdict: str
    ok: bool = Field(description="Whether the walk reached its first verified close.")
    walk: list[Step]
    waited_for_the_chairman: list[Wait]
    clock: list[str] = Field(description="What the wall-clock rules do at their real numbers.")
    staffing: list[str]
    rules_hit: list[RuleHit]
    estimate: Estimate
    parallelism: str
    longest_chain: str
    projected_duration: str
    setup_missing: list[str]
    not_exercised: list[str]
    note: str = NOT_QUALITY
    text: str = Field(default="", description="The report as plain text.")


class History(BaseModel):
    """What this install's own finished runs say, when there are enough of them (GOV-4)."""

    runs: int = 0
    median_tokens: int | None = None
    median_seconds: float | None = None


def hours(seconds: float) -> str:
    if seconds >= 3600:
        value = seconds / 3600
        return f"{value:.0f} h" if value == int(value) else f"{value:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.0f} min"
    return f"{seconds:.0f} s"


def _first(events: list[dict[str, Any]], kind: str, **after: Any) -> dict[str, Any] | None:
    for event in events:
        values: dict[str, Any] = event.get("after") or {}
        if event["type"] == kind and all(values.get(k) == v for k, v in after.items()):
            return event
    return None


def _state(event: dict[str, Any]) -> str | None:
    values: dict[str, Any] = event.get("after") or {}
    return values.get("state")


def _walk(found: dict[str, Any], type: str) -> list[Step]:
    events: list[dict[str, Any]] = found["events"]
    start = datetime.fromisoformat(found["started_at"])
    scope = "bet" if type == "explore" else "requirement"
    plans = _first(events, f"{scope}.state_changed")
    accepted = _first(
        events, f"{scope}.state_changed", state="active" if type == "explore" else "accepted"
    )
    closes = _first(events, "task.state_changed", state="done")
    marks: list[tuple[str, dict[str, Any] | None]] = [
        ("Roles resolve and the project is created", _first(events, "project.created")),
        ("Teams are hired", _first(events, "team.hired") or _first(events, "seat.created")),
        ("The project starts", _first(events, "project.state_changed", state="running")),
        ("The CEO plans", plans),
        ("Scope is accepted", accepted),
        ("Work is claimed", _first(events, "task.state_changed", state="claimed")),
        ("A first deliverable is handed in", _first(events, "task.state_changed", state="review")),
        ("A task closes with evidence", closes),
    ]
    if type == "deliver":
        marks.append(
            ("The project is ready", _first(events, "project.state_changed", state="ready"))
        )
    elif type == "operate":
        marks.append(
            ("A requirement is met", _first(events, "requirement.state_changed", state="met"))
        )
    else:
        ended = next(
            (
                event
                for event in events
                if event["type"] == "bet.state_changed" and _state(event) not in (None, "active")
            ),
            None,
        )
        marks.append(("A bet ends with its finding", ended))
    return [
        Step(
            what=what,
            happened=event is not None,
            after_seconds=(datetime.fromisoformat(event["at"]) - start).total_seconds()
            if event
            else None,
        )
        for what, event in marks
    ]


def _staffing(found: dict[str, Any], type: str) -> list[str]:
    seats: list[dict[str, Any]] = found["seats"]
    settings: dict[str, Any] = found["settings"]
    lines: list[str] = []
    unread = [
        event
        for event in found["events"]
        if event["type"] == "task.state_changed" and _state(event) == "closed unread"
    ]
    if unread:
        lines.append(
            f"{len(unread)} task(s) closed unread: a review was asked for and nobody hired "
            "can give it."
        )
    teams = sorted({seat["team"] for seat in seats if seat["team"]})
    for team in teams:
        members = [seat for seat in seats if seat["team"] == team]
        if not any(seat["runs"] for seat in members):
            lines.append(f"Team {team} had nothing to do in the drill.")
    hired_reviewers = [seat for seat in seats if seat["kind"] == "reviewer" and seat["team"]]
    if settings.get("review.independent") and not hired_reviewers:
        lines.append(
            "Independent read is on and no reviewer is hired: the platform staffed one "
            "reviewer seat, which reads everything."
        )
    if type != "explore" and not any(seat["role"] == "plan-adversary" for seat in seats):
        lines.append("No plan adversary is staffed. One is expected on this type of project.")
    return lines


def _clock(found: dict[str, Any]) -> list[str]:
    settings: dict[str, Any] = found["settings"]
    lines: list[str] = []
    beat = settings.get("heartbeat.every")
    for jump in found.get("jumps", []):
        lines.append(
            f"The drill had nothing to do for {hours(jump['seconds'])} until the clock woke "
            "the CEO. A real project waits that long at this point"
            + (f" (`heartbeat.every` is {hours(beat)})." if beat else ".")
        )
    if beat and not lines:
        lines.append(
            f"Nothing in the walk waited on the clock. When nothing else wakes the CEO, its "
            f"heartbeat does, every {hours(beat)}."
        )
    return lines


def build(found: dict[str, Any], type: str, history: History) -> RehearsalReport:
    """Turn what a drill found into the report. No number here is invented: each comes
    from the drill, the spec's settings or this install's own finished runs."""
    refusal = found.get("refusal")
    walk = _walk(found, type) if not refusal else []
    waits = Counter(wait["kind"] for wait in found["waits"] if wait["kind"] != SAMPLED)
    hits: dict[tuple[str, str], RuleHit] = {}
    for row in found["refusals"]:
        key = (row["rule"] or "", row["code"])
        hit = hits.setdefault(
            key, RuleHit(rule=key[0], code=key[1], times=0, message=row["message"])
        )
        hit.times += 1
    seats: list[dict[str, Any]] = found["seats"]
    settings: dict[str, Any] = found["settings"]
    runs = sum(seat["runs"] for seat in seats)
    workers = len([seat for seat in seats if seat["kind"] in ("worker", "lead")]) or 1
    allowed = int(settings.get("run.concurrency") or 1)
    missing: list[str] = list(found["missing"])
    if refusal:
        verdict, ok = f"Cannot start: {refusal['message']}", False
    elif found["reached"]:
        ok = True
        verdict = (
            "Runs to its first verified close. Setup is still missing before it can start."
            if missing
            else "Runs to its first verified close."
        )
    else:
        ok = False
        last = next((step.what for step in reversed(walk) if step.happened), "nothing")
        verdict = f"Stalls. The last step reached was: {last}."
    if history.median_tokens is not None:
        estimate = Estimate(
            runs_to_first_close=runs,
            tokens_to_first_close=runs * history.median_tokens,
            basis=f"{runs} runs at this install's median of {history.median_tokens:,} tokens "
            f"a run, from {history.runs} finished runs.",
        )
    else:
        estimate = Estimate(
            runs_to_first_close=runs,
            tokens_to_first_close=None,
            basis="This install has too few finished runs to estimate tokens from.",
        )
    chain = found.get("chain_runs")
    duration = "Not known: this install has too few finished runs to time one."
    if history.median_seconds is not None:
        duration = (
            f"At most about {hours(runs * history.median_seconds)} of run time to the first "
            f"close if its {runs} runs went one after another, at this install's median of "
            f"{hours(history.median_seconds)} a run; less where they run in parallel. Add any "
            "wait on the clock above."
        )
    sampled = settings.get("audit.sample_rate")
    report = RehearsalReport(
        verdict=verdict,
        ok=ok,
        walk=walk,
        waited_for_the_chairman=[Wait(kind=kind, times=times) for kind, times in waits.items()],
        clock=_clock(found) if not refusal else [],
        staffing=_staffing(found, type) if not refusal else [],
        rules_hit=sorted(hits.values(), key=lambda hit: (-hit.times, hit.rule, hit.code)),
        estimate=estimate,
        parallelism=(
            f"{workers} seat(s) can work at once and `run.concurrency` is {allowed}, so at "
            f"most {min(workers, allowed)} run in parallel."
            + (" The concurrency is not used in full." if workers < allowed else "")
        ),
        longest_chain=(
            "The drill plans one requirement, so its chain is one step. The real plan's "
            "longest chain is shown in the Plan panel once the CEO has planned."
            if not chain
            else f"{chain} run(s) along the longest dependency chain."
        ),
        projected_duration=duration,
        setup_missing=missing,
        not_exercised=[
            *NOT_EXERCISED,
            *([f"The chairman's audit of sampled closes ({sampled}% of them)."] if sampled else []),
        ],
    )
    report.text = as_text(report)
    return report


def as_text(report: RehearsalReport) -> str:
    lines = [f"Verdict: {report.verdict}", ""]
    if report.walk:
        lines.append("The walk:")
        for step in report.walk:
            when = "did not happen" if not step.happened else f"at {hours(step.after_seconds or 0)}"
            lines.append(f"  - {step.what}: {when}")
        lines.append("")
    if report.waited_for_the_chairman:
        lines.append("It waited for the chairman:")
        lines += [f"  - {wait.kind}: {wait.times}" for wait in report.waited_for_the_chairman]
    else:
        lines.append("It never waited for the chairman.")
    for title, entries in (
        ("The clock", report.clock),
        ("Staffing", report.staffing),
        ("Setup still missing", report.setup_missing),
        ("Not exercised", report.not_exercised),
    ):
        if entries:
            lines += ["", f"{title}:", *(f"  - {entry}" for entry in entries)]
    lines += ["", "Rules hit:"]
    lines += [
        f"  - {hit.rule or 'no rule'} ({hit.code}): {hit.times}" for hit in report.rules_hit
    ] or ["  - none"]
    lines += [
        "",
        f"Runs and tokens: {report.estimate.basis}",
        f"Parallel work: {report.parallelism}",
        f"Longest chain: {report.longest_chain}",
        f"Duration: {report.projected_duration}",
        "",
        report.note,
    ]
    return "\n".join(lines)
