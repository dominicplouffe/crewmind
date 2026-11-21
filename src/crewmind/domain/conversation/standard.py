"""The communication standard's mechanical lint (MSG-12, P18).

Pure functions over a message's text. The lint is feedback, never a refusal: a message
that fails is sent back to its author once, and posts with a marker if it still fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WORD_BUDGETS = {"short": 60, "normal": 150, "detailed": 400}  # MSG-12
NEED_LINE = "Need from you:"  # MSG-12

LONG, UNCLEAR = "long", "unclear"

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LIKELIHOOD = re.compile(r"\b(likely|unlikely|probably|improbable|chance)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(\.\d+)?\s?%|\b\d+ (in|out of) \d+\b")


@dataclass(frozen=True)
class Finding:
    marker: str
    feedback: str


def own_words(body: str) -> str:
    """The author's own text: quoted lines and code are left out (MSG-12)."""
    text = _FENCE.sub(" ", body)
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return _INLINE_CODE.sub(" ", "\n".join(lines))


def word_count(body: str) -> int:
    return len(own_words(body).split())


def asks_something(body: str) -> bool:
    return "?" in own_words(body)


def has_need_line(body: str) -> bool:
    return any(
        line.strip().lower().startswith(NEED_LINE.lower()) for line in own_words(body).splitlines()
    )


def lint(body: str, *, budget: int, to_a_person: bool) -> list[Finding]:
    """The measurable parts of MSG-12. Returns nothing when the message meets them."""
    found: list[Finding] = []
    words = word_count(body)
    if words > budget:
        found.append(
            Finding(
                LONG,
                f"It has {words} words and the budget is {budget}. Lead with the answer, cut "
                "what the reader does not need, and link a file instead of pasting it.",
            )
        )
    if to_a_person and asks_something(body) and not has_need_line(body):
        found.append(
            Finding(
                UNCLEAR,
                f'It asks something but has no "{NEED_LINE}" line. End with one line that '
                f'starts "{NEED_LINE}" and says exactly what you need.',
            )
        )
    text = own_words(body)
    if _LIKELIHOOD.search(text) and not _NUMBER.search(text):
        found.append(
            Finding(
                UNCLEAR,
                "It states a likelihood without a number. Say it in plain words with a "
                'number, such as "likely, about 70%".',
            )
        )
    return found


def marker_of(findings: list[Finding]) -> str | None:
    """The one marker a message that still fails is posted with."""
    markers = {finding.marker for finding in findings}
    return LONG if LONG in markers else UNCLEAR if markers else None


def feedback_of(findings: list[Finding]) -> str:
    return (
        "Your message was not posted yet. It does not meet the communication standard: "
        + " ".join(finding.feedback for finding in findings)
        + " Rewrite it once and post it again; the next version is posted as it is."
    )


def quoted(question: str, body: str) -> str:
    """CHAT-11: after a correction, the reply quotes the question it should have answered."""
    if question.strip() and question.strip() not in body:
        quote = "\n".join(f"> {line}" for line in question.strip().splitlines())
        return f"{quote}\n\n{body}"
    return body
