"""The `crewmind` command, generated from the operation catalog (IF-1.2, section 9.4).

This adapter holds no business rules. `projects.hold` is `crewmind projects hold`. Scalar
inputs are options; any input can be given whole with `--input` as JSON. Every command has
`--json` (IF-4.3), and exit codes follow IF-4.4.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
import types
from collections.abc import Callable
from enum import IntEnum
from typing import Any, Union, get_args, get_origin

import typer
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from typer.core import TyperGroup

from crewmind.catalog.operation import Operation
from crewmind.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from crewmind.catalog.registry import Catalog, catalog, load_domain_modules
from crewmind.catalog.surfaces import Surface, exposed_on
from crewmind.surfaces.cli.invoke import (
    HttpInvoker,
    Invoker,
    LocalInvoker,
    ServerUnreachable,
    http_client_factory,
)

DEFAULT_API = "http://127.0.0.1:8420"


class ExitCode(IntEnum):
    """Exit codes (IF-4.4). Code 2 is a usage error, raised by the argument parser."""

    OK = 0
    ERROR = 1
    USAGE = 2
    REFUSED = 3
    UNAUTHENTICATED = 4
    NOT_FOUND = 5
    UNREACHABLE = 6


EXIT_BY_KIND: dict[RefusalKind, ExitCode] = {
    RefusalKind.RULE: ExitCode.REFUSED,
    RefusalKind.FORBIDDEN: ExitCode.REFUSED,
    RefusalKind.UNAUTHENTICATED: ExitCode.UNAUTHENTICATED,
    RefusalKind.NOT_FOUND: ExitCode.NOT_FOUND,
    RefusalKind.INVALID: ExitCode.USAGE,
}

_SCALARS: tuple[type, ...] = (str, int, float, bool)


def command_name(identifier: str) -> str:
    return identifier.replace("_", "-")


def _scalar_type(annotation: Any) -> type | None:
    """The scalar type behind an annotation, or None when it cannot be a command-line option."""
    if annotation in _SCALARS:
        return annotation
    if get_origin(annotation) in (Union, types.UnionType):
        members = [member for member in get_args(annotation) if member is not type(None)]
        if len(members) == 1 and members[0] in _SCALARS:
            return members[0]
    return None


def _option(field_name: str, field: FieldInfo, scalar: type) -> inspect.Parameter:
    flag = f"--{command_name(field_name)}"
    if scalar is bool:
        flag = f"{flag}/--no-{command_name(field_name)}"
    return inspect.Parameter(
        field_name,
        inspect.Parameter.KEYWORD_ONLY,
        annotation=scalar | None,
        default=typer.Option(None, flag, help=field.description),
    )


def _fail(envelope: ErrorEnvelope, code: ExitCode, json_output: bool) -> typer.Exit:
    if json_output:
        typer.echo(envelope.model_dump_json(), err=True)
    else:
        typer.echo(envelope.message, err=True)
        if envelope.hint:
            typer.echo(envelope.hint, err=True)
    return typer.Exit(code)


def _print(result: BaseModel, json_output: bool) -> None:
    if json_output:
        typer.echo(result.model_dump_json())
        return
    for key, value in result.model_dump(mode="json").items():
        typer.echo(f"{key}: {value}")


def _command(operation: Operation, invoker: Invoker) -> Callable[..., None]:
    scalar_fields = {
        name: scalar
        for name, field in operation.input.model_fields.items()
        if (scalar := _scalar_type(field.annotation)) is not None
    }

    def command(**options: Any) -> None:
        json_output: bool = options.pop("json_output")
        raw_input: str | None = options.pop("input_json")
        values: dict[str, Any] = {}
        if raw_input is not None:
            text = sys.stdin.read() if raw_input == "-" else raw_input
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError as error:
                raise typer.BadParameter(f"--input is not JSON: {error}") from error
            if not isinstance(loaded, dict):
                raise typer.BadParameter("--input must be a JSON object")
            values.update(loaded)  # pyright: ignore[reportUnknownArgumentType]
        values.update({name: value for name, value in options.items() if value is not None})
        try:
            payload = operation.input.model_validate(values)
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
                for problem in error.errors()
            )
            raise typer.BadParameter(problems) from error
        try:
            result = asyncio.run(invoker.invoke(operation, payload))
        except Refusal as refusal:
            envelope = refusal.envelope
            raise _fail(envelope, EXIT_BY_KIND[envelope.kind], json_output) from refusal
        except ServerUnreachable as error:
            envelope = ErrorEnvelope(
                kind=RefusalKind.NOT_FOUND,
                code="server_unreachable",
                message=f"The crewmind server did not answer: {error}",
                hint="Start it with `crewmind up`, or set CREWMIND_API to its address.",
            )
            raise _fail(envelope, ExitCode.UNREACHABLE, json_output) from error
        _print(result, json_output)

    parameters = [
        _option(name, operation.input.model_fields[name], scalar)
        for name, scalar in scalar_fields.items()
    ]
    parameters.append(
        inspect.Parameter(
            "input_json",
            inspect.Parameter.KEYWORD_ONLY,
            annotation=str | None,
            default=typer.Option(
                None, "--input", help="The whole input as a JSON object; '-' reads standard input."
            ),
        )
    )
    parameters.append(
        inspect.Parameter(
            "json_output",
            inspect.Parameter.KEYWORD_ONLY,
            annotation=bool,
            default=typer.Option(False, "--json", help="Write the result as JSON."),
        )
    )
    command.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    command.__annotations__ = {parameter.name: parameter.annotation for parameter in parameters}
    command.__doc__ = _help(operation, scalar_fields)
    return command


def _help(operation: Operation, scalar_fields: dict[str, type]) -> str:
    required_elsewhere = [
        name
        for name, field in operation.input.model_fields.items()
        if name not in scalar_fields and field.default is PydanticUndefined
    ]
    if not required_elsewhere:
        return operation.summary
    return f"{operation.summary}\n\nGive {', '.join(required_elsewhere)} with --input."


def build_cli(
    catalog: Catalog, invoker: Invoker, local_invoker: Invoker | None = None
) -> typer.Typer:
    """Build the CLI with one command per operation that belongs on it."""
    app = typer.Typer(
        name="crewmind",
        help="Run a team of AI agents like a company, under rules they cannot get around.",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.callback()
    def root() -> None:  # pyright: ignore[reportUnusedFunction]
        pass

    host = local_invoker or LocalInvoker()
    groups: dict[str, typer.Typer] = {}
    for operation in catalog:
        if not exposed_on(operation, Surface.CLI):
            continue
        group = groups.get(operation.group)
        if group is None:
            group = typer.Typer(no_args_is_help=True)
            groups[operation.group] = group
            app.add_typer(group, name=command_name(operation.group))
        chosen = host if operation.host_local else invoker
        group.command(name=command_name(operation.verb))(_command(operation, chosen))
    return app


def exposed_operations(app: typer.Typer) -> set[str]:
    """The operation names the CLI actually offers: every command under a group."""
    names: set[str] = set()
    root = typer.main.get_command(app)
    if not isinstance(root, TyperGroup):
        return names
    for group_name, group in root.commands.items():
        if isinstance(group, TyperGroup):
            for verb in group.commands:
                names.add(f"{group_name}.{verb}".replace("-", "_"))
        else:
            names.add(group_name.replace("-", "_"))
    return names


def main() -> None:
    """Entry point of the `crewmind` command (IF-4.1)."""
    load_domain_modules()
    invoker = HttpInvoker(
        http_client_factory(
            os.environ.get("CREWMIND_API", DEFAULT_API), os.environ.get("CREWMIND_TOKEN")
        )
    )
    build_cli(catalog, invoker)()
