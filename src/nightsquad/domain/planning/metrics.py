"""Metric requirements (PLN-11): the platform reads a number from a public page on a
schedule, writes the requirement met when the number reaches its target, and says when
the project is losing ground. No agent writes a reading."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.conversation import service as conversation
from nightsquad.domain.execution import notices
from nightsquad.domain.execution.roster import ceo_of
from nightsquad.domain.planning import acceptance, authority
from nightsquad.domain.planning.model import OPEN_SCOPE, RequirementState, RequirementTest
from nightsquad.domain.planning.readiness import PLANNING_JOB, move
from nightsquad.domain.settings.service import SettingsService
from nightsquad.domain.work import fetch
from nightsquad.storage.models import MetricReading, Project, Requirement

PLN_11 = rules.register(
    Rule("PLN-11", "A metric is read by the platform from a public page, never by an agent.")
)
WINDOW = 6  # PLN-11: losing ground is judged over a 6-reading window
PATTERN_MOST = 300
R = RequirementState
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def describe(metric: dict[str, Any]) -> str:
    word = "at least" if metric["at_least"] else "at most"
    return f"The number read from {metric['url']} is {word} {metric['target']:g}."


def check_source(url: str | None, pattern: str | None, target: float | None) -> None:
    """PLN-11, WRK-12: a metric names a public URL and a pattern that finds one number."""
    if not url or not pattern or target is None:
        raise Refusal(
            "metric_needs_a_source",
            "A metric requirement names a public URL, a pattern that finds the number on the "
            "page, and a target.",
            rule=PLN_11.id,
        )
    try:
        fetch.check_url(url)
    except fetch.FetchRefused as refused:
        raise Refusal(
            "metric_source_not_public",
            f"The metric's page cannot be read: {refused}.",
            rule=PLN_11.id,
            hint="Give a public http or https address.",
        ) from refused
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        raise Refusal(
            "metric_pattern_invalid", f"The pattern is not valid: {error}.", rule=PLN_11.id
        ) from error
    if compiled.groups != 1 or len(pattern) > PATTERN_MOST:
        raise Refusal(
            "metric_pattern_invalid",
            "The pattern has exactly one group, around the number, and at most "
            f"{PATTERN_MOST} characters.",
            rule=PLN_11.id,
            hint='For example: "Subscribers: ([0-9,.]+)".',
        )


def read_number(page: bytes, pattern: str) -> float | None:
    """The number the pattern finds on the page, or None."""
    found = re.search(pattern, page.decode("utf-8", errors="replace"))
    if found is None:
        return None
    number = _NUMBER.search(found.group(1).replace(",", ""))
    return float(number.group(0)) if number else None


def reached(value: float, metric: dict[str, Any]) -> bool:
    target = float(metric["target"])
    return value >= target if metric["at_least"] else value <= target


def losing_ground(values: list[float], metric: dict[str, Any]) -> bool:
    """PLN-11: the latest reading is further from target than the oldest in a 6-reading
    window. A single bad reading is not enough: the window must be full."""
    if len(values) < WINDOW:
        return False
    window = values[-WINDOW:]
    target = float(metric["target"])
    if reached(window[-1], metric):
        return False
    return abs(window[-1] - target) > abs(window[0] - target)


async def due(
    session: AsyncSession, settings: SettingsService, now: datetime
) -> list[tuple[int, str, str]]:
    """Metric requirements whose next reading is due, as (id, url, pattern)."""
    rows = await session.execute(
        select(Requirement, Project)
        .join(Project, Project.id == Requirement.project_id)
        .where(
            Requirement.test_kind == RequirementTest.METRIC,
            Requirement.state.in_(OPEN_SCOPE),
            Project.state == "running",
        )
        .order_by(Requirement.id)
    )
    found: list[tuple[int, str, str]] = []
    for requirement, project in rows.all():
        every = int(await settings.get(session, authority.subject(project), "metric.read_every"))
        last = await session.scalar(
            select(MetricReading.at)
            .where(MetricReading.requirement_id == requirement.id)
            .order_by(MetricReading.id.desc())
            .limit(1)
        )
        metric = requirement.metric or {}
        if last is None or now - last >= timedelta(seconds=every):
            found.append((requirement.id, str(metric["url"]), str(metric["pattern"])))
    return found


async def record(
    session: AsyncSession,
    requirement: Requirement,
    project: Project,
    value: float | None,
    failure: str | None,
    now: datetime,
) -> None:
    """Store one reading. A reading that reaches the target writes the requirement met; a
    full window that moves away from the target tells the CEO and the chairman once."""
    session.add(
        MetricReading(
            requirement_id=requirement.id,
            project_id=project.id,
            value=value,
            failure=failure,
            at=now,
        )
    )
    await session.flush()
    metric = dict(requirement.metric or {})
    if value is None:
        return
    if reached(value, metric):
        metric["losing"] = False
        requirement.metric = metric
        if requirement.state == R.ACCEPTED:
            move(session, requirement, R.IN_PROGRESS, PLANNING_JOB, now, {"reading": value})
        if requirement.state == R.IN_PROGRESS:
            move(session, requirement, R.CHECKING, PLANNING_JOB, now, {"reading": value})
        await acceptance.settle(
            session, project, requirement, True, f"The reading is {value:g}.", now, by=PLANNING_JOB
        )
        return
    rows = await session.scalars(
        select(MetricReading.value)
        .where(MetricReading.requirement_id == requirement.id, MetricReading.value.is_not(None))
        .order_by(MetricReading.id)
    )
    losing = losing_ground([float(row) for row in rows if row is not None], metric)
    if losing and not metric.get("losing"):
        text = (
            f"Requirement {requirement.id} is losing ground: the latest reading is {value:g}, "
            f"further from its target of {metric['target']:g} than {WINDOW} readings ago."
        )
        ceo = await ceo_of(session, project.id)
        notices.notify(session, project.id, ceo.id, "losing ground", text, now, urgent=True)
        await conversation.platform_line(
            session, project.id, text, now,
            detail={"kind": "losing ground", "requirement": requirement.id},
        )  # fmt: skip
    metric["losing"] = losing
    requirement.metric = metric


async def latest(session: AsyncSession, requirement_id: int) -> MetricReading | None:
    return await session.scalar(
        select(MetricReading)
        .where(MetricReading.requirement_id == requirement_id)
        .order_by(MetricReading.id.desc())
        .limit(1)
    )
