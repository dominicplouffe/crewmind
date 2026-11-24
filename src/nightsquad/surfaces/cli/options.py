"""Turning an operation's input model into command-line options (IF-4.3, IF-4.5)."""

from __future__ import annotations

import inspect
import json
import sys
import types
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

import typer
from pydantic import BaseModel, SecretStr
from pydantic.fields import FieldInfo

_SCALARS: tuple[type, ...] = (str, int, float, bool)


def command_name(identifier: str) -> str:
    return identifier.replace("_", "-")


def _unwrap(annotation: Any) -> Any:
    """Strip `| None` from an annotation."""
    if get_origin(annotation) in (Union, types.UnionType):
        members = [member for member in get_args(annotation) if member is not type(None)]
        if len(members) == 1:
            return members[0]
    return annotation


def kind_of(field: FieldInfo) -> str | None:
    """How a field is given on the command line, or None when only `--input` can give it."""
    annotation = _unwrap(field.annotation)
    if annotation is SecretStr:
        return "secret"
    if annotation in _SCALARS:
        return "scalar"
    if annotation in (datetime, date) or get_origin(annotation) is Literal:
        return "text"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "text"
    if get_origin(annotation) is dict:
        return "pairs"
    if get_origin(annotation) is list and get_args(annotation) == (str,):
        return "list"
    return None


def parameters_for(model: type[BaseModel]) -> list[inspect.Parameter]:
    parameters: list[inspect.Parameter] = []

    def add(name: str, annotation: Any, option: Any) -> None:
        parameters.append(
            inspect.Parameter(
                name, inspect.Parameter.KEYWORD_ONLY, annotation=annotation, default=option
            )
        )

    for name, field in model.model_fields.items():
        flag = f"--{command_name(name)}"
        kind = kind_of(field)
        if kind == "scalar":
            scalar = _unwrap(field.annotation)
            shown = f"{flag}/--no-{command_name(name)}" if scalar is bool else flag
            add(name, scalar | None, typer.Option(None, shown, help=field.description))
        elif kind == "text":
            add(name, str | None, typer.Option(None, flag, help=field.description))
        elif kind == "pairs":
            add(
                name,
                list[str] | None,
                typer.Option(None, flag, help=f"{field.description} Repeat as NAME=VALUE."),
            )
        elif kind == "list":
            add(name, list[str] | None, typer.Option(None, flag, help=field.description))
        elif kind == "secret":
            add(
                f"{name}_file",
                Path | None,
                typer.Option(None, f"{flag}-file", help=f"Read {name} from this file."),
            )
            add(
                f"{name}_stdin",
                bool,
                typer.Option(False, f"{flag}-stdin", help=f"Read {name} from standard input."),
            )
    return parameters


def _pair(text: str) -> tuple[str, Any]:
    name, separator, raw = text.partition("=")
    if not separator:
        raise typer.BadParameter(f"{text!r} is not NAME=VALUE")
    try:
        return name, json.loads(raw)
    except json.JSONDecodeError:
        return name, raw


def _secret(name: str, options: dict[str, Any], may_prompt: bool) -> str | None:
    """Read a secret from a file, standard input or a hidden prompt; never from an argument
    and never echoed (IF-4.5)."""
    path: Path | None = options.pop(f"{name}_file")
    from_stdin: bool = options.pop(f"{name}_stdin")
    if path is not None:
        return path.read_text(encoding="utf-8").rstrip("\n")
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    if may_prompt and sys.stdin.isatty():
        return typer.prompt(command_name(name).replace("-", " ").capitalize(), hide_input=True)
    return None


def values_from(
    model: type[BaseModel], options: dict[str, Any], *, may_prompt: bool
) -> dict[str, Any]:
    """The input values given on the command line."""
    values: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        kind = kind_of(field)
        if kind == "secret":
            secret = _secret(name, options, may_prompt)
            if secret is not None:
                values[name] = secret
        elif kind == "pairs":
            pairs: list[str] | None = options.pop(name)
            if pairs:
                values[name] = dict(_pair(pair) for pair in pairs)
        elif kind is not None:
            value = options.pop(name)
            if value is not None and value != []:
                values[name] = value
    return values
