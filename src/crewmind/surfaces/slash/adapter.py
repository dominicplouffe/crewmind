"""Chat slash commands, generated from the operation catalog (CHAT-5, IF-1.1, IF-1.2).

This adapter holds no business rules. `/hold until 2026-11-23T09:00` finds the operation
that declares `/hold`, builds its input from the text, and has the executor run it as the
person who typed it, with that operation's own authority check.
"""

from __future__ import annotations

import json
import shlex
from typing import Any

from pydantic import BaseModel, ValidationError

from crewmind.catalog.operation import PROJECT_FIELD, Operation
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.registry import Catalog
from crewmind.catalog.surfaces import Surface, exposed_on


def commands(catalog: Catalog) -> dict[str, Operation]:
    """Every slash command and the operation behind it."""
    found: dict[str, Operation] = {}
    for operation in catalog:
        if operation.slash_command is not None and exposed_on(operation, Surface.SLASH):
            found[operation.slash_command] = operation
    return found


def exposed_operations(catalog: Catalog) -> set[str]:
    return {operation.name for operation in commands(catalog).values()}


def _value(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse(catalog: Catalog, project_id: str, text: str) -> tuple[Operation, BaseModel]:
    """Turn a line starting with `/` into an operation and its input.

    After the command, `name=value` sets a field, a bare field name followed by a value
    (`until 2026-11-23T09:00`) sets that field, and the remaining words go to the first
    field that needs a value."""
    command, _, rest = text.strip().partition(" ")
    known = commands(catalog)
    operation = known.get(command.lower())
    if operation is None:
        raise Refusal(
            "unknown_command",
            f"There is no command {command}. Commands: {', '.join(sorted(known))}.",
            kind=RefusalKind.NOT_FOUND,
            hint="Type /help to see what each one does.",
        )
    fields = operation.input.model_fields
    values: dict[str, Any] = {PROJECT_FIELD: project_id} if PROJECT_FIELD in fields else {}
    try:
        words = shlex.split(rest)
    except ValueError:
        words = rest.split()
    free: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        name, separator, value = word.partition("=")
        if separator and name in fields:
            values[name] = _value(value)
        elif word in fields and word != PROJECT_FIELD and index + 1 < len(words):
            values[word] = _value(words[index + 1])
            index += 1
        else:
            free.append(word)
        index += 1
    if free:
        open_fields = [n for n in fields if n not in values and n != PROJECT_FIELD]
        required = [n for n in open_fields if fields[n].is_required()]
        target = (required or open_fields or [None])[0]
        if target is None:
            raise Refusal(
                "command_takes_no_text",
                f"{command} takes no text after it.",
                kind=RefusalKind.INVALID,
            )
        values[target] = _value(" ".join(free)) if len(free) == 1 else " ".join(free)
    try:
        return operation, operation.input.model_validate(values)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in error.errors()
        )
        raise Refusal(
            "command_invalid",
            f"{command} could not be understood: {problems}",
            kind=RefusalKind.INVALID,
            hint=f"{command}: {operation.summary}",
        ) from None
