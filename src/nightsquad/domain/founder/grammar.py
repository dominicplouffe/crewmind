"""The goal grammar: ten elements, the grade of each, and the verdict (FND-6, FND-7,
FND-8). A model grades; the platform checks the grade's evidence and computes the verdict."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules

FND_7 = rules.register(
    Rule("FND-7", "A goal is graded on ten elements, each with a quoted line or a reason.")
)
FND_8 = rules.register(
    Rule("FND-8", "A date is an outside fact with a source or a chairman target, never prose.")
)

ELEMENTS: tuple[tuple[str, str], ...] = (
    ("finish_line", "A finish line, and a record the project does not write itself"),
    ("beneficiary", "Who the output must be right for"),
    ("standard", "A named reference class, and that the brief is a subset of it"),
    ("anti_metrics", "Plausible substitutes that do not count"),
    ("method_constraints", "Method constraints, only where they matter, and falsifiable"),
    ("stated_bias", "A bias, marked as one the project may override on evidence"),
    ("quality_bar", "A quality bar, with a reason and an owner"),
    ("human_role", "The human's role, including what they will not do"),
    ("resource_posture", "Resource posture, with a reason and a release condition"),
    ("failure_deliverable", "What is owed if the finish line is missed"),
)
IDS = tuple(element for element, _ in ELEMENTS)
LOAD_BEARING = frozenset(
    {"finish_line", "standard", "anti_metrics", "quality_bar", "failure_deliverable"}
)
"""FND-7: missing any of these means the goal is not ready."""

PRESENT, WEAK, MISSING = "present", "weak", "missing"


class ElementGrade(BaseModel):
    element: str
    grade: Literal["present", "weak", "missing"]
    quote: str = Field("", description="The line of the goal the grade rests on.")
    reason: str = Field("", description="Why it does not apply, when graded present unquoted.")
    fix: str = Field("", description="The named fix, when weak or missing.")


class Grade(BaseModel):
    ready: bool
    elements: list[ElementGrade]
    missing: list[str] = Field(description="Elements graded missing.")
    weak: list[str]
    summary: str


def _squash(text: str) -> str:
    return " ".join(text.split()).lower()


def parse(answer: str) -> list[dict[str, Any]]:
    """The grader's answer is a JSON list, possibly inside a fenced block."""
    found = re.search(r"\[.*\]", answer, re.DOTALL)
    try:
        rows = json.loads(found.group(0) if found else answer)
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        raise Refusal(
            "grade_unreadable",
            "The grader did not answer with a list of ten grades.",
            rule=FND_7.id,
            hint="Grade again.",
        )
    return [row for row in rows if isinstance(row, dict)]  # pyright: ignore[reportUnknownVariableType]


def check(goal: str, rows: list[dict[str, Any]]) -> Grade:
    """Turn a grader's rows into a grade the platform stands behind (FND-7).

    Every element is graded once. A grade of present or weak quotes a line that is in
    the goal, or, for present, gives the reason the element does not apply; a quote that
    is not in the goal is refused. The verdict is arithmetic: the goal is ready when no
    load-bearing element is missing."""
    try:
        grades = {row.element: row for row in (ElementGrade.model_validate(r) for r in rows)}
    except ValidationError as error:
        raise Refusal(
            "grade_unreadable",
            f"The grade is not in the expected form: {error.errors()[0]['msg']}.",
            rule=FND_7.id,
        ) from error
    absent = [element for element in IDS if element not in grades]
    extra = [element for element in grades if element not in IDS]
    if absent or extra:
        raise Refusal(
            "grade_incomplete",
            "A grade covers each of the ten elements once."
            + (f" Not graded: {', '.join(absent)}." if absent else "")
            + (f" Not an element: {', '.join(extra)}." if extra else ""),
            rule=FND_7.id,
        )
    text = _squash(goal)
    for grade in grades.values():
        quote = _squash(grade.quote)
        if quote and quote not in text:
            raise Refusal(
                "quote_not_in_goal",
                f"The grade of {grade.element} quotes a line that is not in the goal.",
                rule=FND_7.id,
                hint="Quote the goal word for word.",
            )
        if grade.grade == WEAK and not quote:
            raise Refusal(
                "grade_without_evidence",
                f"{grade.element} is graded weak with no quoted line.",
                rule=FND_7.id,
            )
        if grade.grade == PRESENT and not quote and not grade.reason.strip():
            raise Refusal(
                "grade_without_evidence",
                f"{grade.element} is graded present with no quoted line and no reason it "
                "does not apply. Silence is not accepted.",
                rule=FND_7.id,
            )
        if grade.grade != PRESENT and not grade.fix.strip():
            raise Refusal(
                "grade_without_fix",
                f"{grade.element} is graded {grade.grade} with no named fix.",
                rule=FND_7.id,
            )
    ordered = [grades[element] for element in IDS]
    missing = [grade.element for grade in ordered if grade.grade == MISSING]
    weak = [grade.element for grade in ordered if grade.grade == WEAK]
    blocking = [element for element in missing if element in LOAD_BEARING]
    if blocking:
        summary = f"Not ready: {', '.join(blocking)} missing."
    elif missing or weak:
        summary = "Ready, with " + ", ".join([*missing, *weak]) + " to improve."
    else:
        summary = "Ready: all ten elements are present."
    return Grade(ready=not blocking, elements=ordered, missing=missing, weak=weak, summary=summary)


MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
DATE = re.compile(
    rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}"
    rf"|(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\b(?:\s+\d{{4}})?"
    rf"|(?:{MONTHS})\s+\d{{4}}|q[1-4]\s+\d{{4}}|(?:by|before|in)\s+(?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)


def date_in(goal: str) -> str | None:
    """A calendar date written into goal prose, if there is one (FND-8)."""
    found = DATE.search(goal)
    return found.group(0) if found else None


def no_dates(goal: str) -> None:
    found = date_in(goal)
    if found:
        raise Refusal(
            "date_in_goal",
            f'The goal prose holds a date ("{found}"). A date is stored as an outside fact '
            "with its source, or as the chairman's target; it is never written into the goal.",
            rule=FND_8.id,
            hint="Remove it from the goal and give it as the deadline, with its source.",
        )


RUBRIC = """Grade the goal below against the ten elements of the goal grammar. Answer with a
JSON list of exactly ten objects, in this order, one per element:

{elements}

Each object has: "element" (the id), "grade" ("present", "weak" or "missing"), "quote" (the
line of the goal the grade rests on, copied word for word; empty only when missing, or when
the element does not apply), "reason" (when an element does not apply, grade it "present"
and say why here), and "fix" (for "weak" or "missing": the one change that would fix it).
Quote only the goal. Do not grade what the goal could have meant; grade what it says."""


def rubric() -> str:
    lines = "\n".join(f'- "{element}": {what}' for element, what in ELEMENTS)
    return RUBRIC.format(elements=lines)
