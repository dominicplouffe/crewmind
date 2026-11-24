"""The communication lint and reporting slots, as pure functions (MSG-8, MSG-12, CHAT-11)."""

from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from nightsquad.domain.conversation import standard
from nightsquad.domain.conversation.speaking import next_slot

NEED = "Need from you: a yes or a no."


@pytest.mark.parametrize(
    ("body", "budget", "to_a_person", "markers"),
    [
        ("The draft is ready.", 60, True, []),
        ("word " * 61, 60, True, ["long"]),
        ("word " * 60, 60, True, []),
        ("> " + "quoted " * 200 + "\n\nAgreed.", 60, True, []),
        ("```\n" + "code " * 200 + "\n```\nIt runs.", 60, True, []),
        ("Which one do you want?", 60, True, ["unclear"]),
        (f"Which one do you want?\n{NEED}", 60, True, []),
        ("Which one do you want?", 60, False, []),
        ("> Which one?\n\nThe second.", 60, True, []),
        ("It is likely to slip.", 60, True, ["unclear"]),
        ("It is likely to slip, about 70%.", 60, True, []),
        ("There is a 1 in 5 chance it slips.", 60, True, []),
        ("It will probably slip. " + "word " * 80, 60, False, ["long", "unclear"]),
    ],
)
def test_MSG_12_the_lint_checks_the_measurable_parts(
    body: str, budget: int, to_a_person: bool, markers: list[str]
) -> None:
    """MSG-12: the word budget (quoted material and code excluded), a "Need from you:" line
    when a person is asked something, and a number with any stated likelihood."""
    found = standard.lint(body, budget=budget, to_a_person=to_a_person)
    assert sorted(finding.marker for finding in found) == markers
    assert standard.marker_of(found) == ("long" if "long" in markers else (markers or [None])[0])


def test_MSG_12_feedback_says_what_to_change_and_that_it_is_not_a_refusal() -> None:
    """MSG-12, P1: the feedback names each failing part and says the next version posts."""
    found = standard.lint("Shall I go on? " + "word " * 200, budget=150, to_a_person=True)
    text = standard.feedback_of(found)
    assert "204 words and the budget is 150" in text
    assert "Need from you:" in text
    assert "the next version is posted as it is" in text


def test_CHAT_11_the_question_is_quoted_once() -> None:
    """CHAT-11: the question is quoted above the answer, and not twice."""
    quoted = standard.quoted("What does it cost?\nPer month.", "About 40 a month.")
    assert quoted == "> What does it cost?\n> Per month.\n\nAbout 40 a month."
    already = "> What does it cost?\n\nAbout 40."
    assert standard.quoted("What does it cost?", already) == already


@pytest.mark.parametrize(
    ("now", "slots", "expected"),
    [
        ("2026-11-21T07:00", 1, "2026-11-21T08:00"),
        ("2026-11-21T08:00", 1, "2026-11-22T08:00"),
        ("2026-11-21T09:00", 2, "2026-11-21T20:00"),
        ("2026-11-21T21:00", 2, "2026-11-22T08:00"),
        ("2026-11-21T13:59", 4, "2026-11-21T14:00"),
        ("2026-11-21T02:30", 4, "2026-11-21T08:00"),
    ],
)
def test_MSG_8_slots_are_evenly_spaced_from_the_first(now: str, slots: int, expected: str) -> None:
    """MSG-8: `report.cadence` slots a day, evenly spaced from the first, strictly after now."""
    at = datetime.fromisoformat(now).replace(tzinfo=UTC)
    slot = next_slot(at, slots, time(8, 0), ZoneInfo("UTC"))
    assert slot == datetime.fromisoformat(expected).replace(tzinfo=UTC)


def test_MSG_8_slots_follow_the_projects_time_zone() -> None:
    """MSG-8: 08:00 in Montreal in November is 13:00 UTC."""
    at = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    assert next_slot(at, 1, time(8, 0), ZoneInfo("America/Toronto")) == datetime(
        2026, 11, 21, 13, 0, tzinfo=UTC
    )
