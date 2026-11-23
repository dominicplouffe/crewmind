"""Reading pasted `.env` text into names and values (CON-2). Values stay on the server: the
review shows names, kinds and problems only."""

from __future__ import annotations

import re
from dataclasses import dataclass

from crewmind.domain.connections.model import Kind

_LINE = re.compile(r"^\s*(?:export\s+)?([^=\s]+)\s*=\s*(.*?)\s*$")
_SECRET_WORDS = re.compile(
    r"KEY|TOKEN|SECRET|PASS|PWD|CREDENTIAL|AUTH|PRIVATE|CERT|DSN|SIGNATURE|SALT|COOKIE|SESSION"
)
_URL_WITH_PASSWORD = re.compile(r"^[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)


@dataclass
class Line:
    number: int
    key: str
    value: str
    guess: Kind
    problem: str | None = None


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        inner = raw[1:-1]
        return inner.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    hashed = re.search(r"\s+#", raw)
    return raw[: hashed.start()] if hashed else raw


def guess(key: str, value: str) -> Kind:
    """A secret when the name or the value looks like one; a variable otherwise."""
    if _SECRET_WORDS.search(key.upper()) or _URL_WITH_PASSWORD.match(value):
        return Kind.SECRET
    return Kind.VARIABLE


def parse(text: str) -> list[Line]:
    """Every `KEY=value` line, in order. A line that is not one is reported, never guessed;
    a key given twice is reported on its earlier lines (the last one is used)."""
    found: list[Line] = []
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        matched = _LINE.match(raw)
        if matched is None:
            found.append(
                Line(number, stripped.split("=")[0][:100], "", Kind.VARIABLE, "not KEY=value")
            )
            continue
        key, value = matched.group(1), _unquote(matched.group(2))
        found.append(Line(number, key, value, guess(key, value)))
    last = {line.key: line.number for line in found}
    for line in found:
        if line.problem is None and last[line.key] != line.number:
            line.problem = f"given again on line {last[line.key]}"
    return found
