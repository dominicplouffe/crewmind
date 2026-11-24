"""The `squad` command, generated from the operation catalog (IF-1.2, section 9.4).

This adapter holds no business rules. `projects.hold` is `squad projects hold`. Inputs
are options; any input can be given whole with `--input` as JSON. Every command has
`--json` (IF-4.3), secrets come from hidden input (IF-4.5), and exit codes follow IF-4.4.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import socket
import sys
from collections.abc import Callable, Coroutine
from enum import IntEnum
from pathlib import Path
from typing import Any, cast

import httpx
import typer
from pydantic import BaseModel, ValidationError
from typer.core import TyperGroup

from nightsquad.catalog.operation import Operation
from nightsquad.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from nightsquad.catalog.registry import Catalog, catalog, load_domain_modules
from nightsquad.catalog.surfaces import Surface, exposed_on
from nightsquad.surfaces.cli.config import CliState, api_address, current_token
from nightsquad.surfaces.cli.invoke import (
    HttpInvoker,
    Invoker,
    LocalInvoker,
    ServerUnreachable,
    http_client_factory,
)
from nightsquad.surfaces.cli.options import command_name, parameters_for, values_from

HOST_GROUP = "install"
"""Host-local operations (IF-4.2) are top-level commands: `install.up` is `squad up`."""

ALIASES: dict[str, str] = {
    "login": "auth.login",
    "logout": "auth.logout",
    "whoami": "auth.whoami",
    "accept": "auth.use_link",
}
"""Short top-level names for everyday commands. Each is the same command as its operation."""


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

Around = Callable[[Catalog, Invoker, Operation, BaseModel], Coroutine[Any, Any, BaseModel]]


class SignedIn(BaseModel):
    signed_in_as: str
    role: str
    token_expires_at: str | None


async def _login(
    source: Catalog, invoker: Invoker, operation: Operation, payload: BaseModel
) -> BaseModel:
    """`squad login` stores a personal token, not the session (IF-4.1): sign in, mint a
    token with the session, end the session, keep the token."""
    session = (await invoker.invoke(operation, payload)).model_dump(mode="json")
    bearer: str = session["session"]
    mint = source.get("tokens.mint")
    name = f"nightsquad CLI on {socket.gethostname()}"
    minted = (await invoker.invoke(mint, mint.input(name=name), bearer=bearer)).model_dump(
        mode="json"
    )
    logout = source.get("auth.logout")
    await invoker.invoke(logout, logout.input(), bearer=bearer)
    CliState(token=minted["token"], token_id=minted["token_id"]).save()
    return SignedIn(
        signed_in_as=session["name"], role=session["role"], token_expires_at=minted["expires_at"]
    )


async def _logout(
    source: Catalog, invoker: Invoker, operation: Operation, payload: BaseModel
) -> BaseModel:
    """`squad logout` revokes the stored token on the server, then forgets it."""
    state = CliState.load()
    if state.token and state.token_id:
        revoke = source.get("tokens.revoke")
        await invoker.invoke(revoke, revoke.input(token_id=state.token_id), bearer=state.token)
    CliState.clear()
    return operation.output()


AROUND: dict[str, Around] = {"auth.login": _login, "auth.logout": _logout}
"""Client-side steps around two operations: where the CLI keeps its own token."""


def _fail(envelope: ErrorEnvelope, code: ExitCode, json_output: bool) -> typer.Exit:
    if json_output:
        typer.echo(envelope.model_dump_json(), err=True)
    else:
        typer.echo(envelope.message, err=True)
        if envelope.hint:
            typer.echo(envelope.hint, err=True)
    return typer.Exit(code)


def _show(value: Any, indent: str = "") -> None:
    """Print a result in plain lines."""
    if isinstance(value, dict):
        items = cast("dict[str, Any]", value)
        for key, item in items.items():
            if isinstance(item, dict | list) and item:
                typer.echo(f"{indent}{key}:")
                _show(item, indent + "  ")
            else:
                typer.echo(f"{indent}{key}: {'' if item is None else item}")
    elif isinstance(value, list):
        for item in cast("list[Any]", value):
            if isinstance(item, dict):
                row = cast("dict[str, Any]", item)
                shown = ", ".join(f"{k}={v}" for k, v in row.items() if v is not None)
                typer.echo(f"{indent}- {shown}")
            else:
                typer.echo(f"{indent}- {item}")


def _print(result: BaseModel, json_output: bool) -> None:
    if json_output:
        typer.echo(result.model_dump_json())
    else:
        _show(result.model_dump(mode="json"))


def _command(source: Catalog, operation: Operation, invoker: Invoker) -> Callable[..., None]:
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
            values.update(cast("dict[str, Any]", loaded))
        values.update(values_from(operation.input, options, may_prompt=not json_output))
        try:
            payload = operation.input.model_validate(values)
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
                for problem in error.errors()
            )
            raise typer.BadParameter(problems) from error
        around = AROUND.get(operation.name)
        try:
            if around is None:
                result = asyncio.run(invoker.invoke(operation, payload))
            else:
                result = asyncio.run(around(source, invoker, operation, payload))
        except Refusal as refusal:
            envelope = refusal.envelope
            raise _fail(envelope, EXIT_BY_KIND[envelope.kind], json_output) from refusal
        except ServerUnreachable as error:
            envelope = ErrorEnvelope(
                kind=RefusalKind.NOT_FOUND,
                code="server_unreachable",
                message=f"The Nightsquad server did not answer: {error}",
                hint="Start it with `squad up`, or set NIGHTSQUAD_API to its address.",
            )
            raise _fail(envelope, ExitCode.UNREACHABLE, json_output) from error
        _print(result, json_output)

    parameters = parameters_for(operation.input)
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
    command.__doc__ = operation.summary
    return command


def build_cli(source: Catalog, invoker: Invoker, local_invoker: Invoker) -> typer.Typer:
    """Build the CLI with one command per operation that belongs on it."""
    app = typer.Typer(
        name="nightsquad",
        help="Run a team of AI agents like a company, under rules they cannot get around.",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.callback()
    def root() -> None:  # pyright: ignore[reportUnusedFunction]
        pass

    groups: dict[str, typer.Typer] = {}
    commands: dict[str, Callable[..., None]] = {}
    for operation in source:
        if not exposed_on(operation, Surface.CLI):
            continue
        command = _command(source, operation, local_invoker if operation.host_local else invoker)
        commands[operation.name] = command
        if operation.group == HOST_GROUP:
            app.command(name=command_name(operation.verb))(command)
            continue
        group = groups.get(operation.group)
        if group is None:
            group = typer.Typer(no_args_is_help=operation.group not in CLIENT_COMMANDS)
            groups[operation.group] = group
            app.add_typer(group, name=command_name(operation.group))
        group.command(name=command_name(operation.verb))(command)
    for alias, target in ALIASES.items():
        if target in commands:
            app.command(name=alias)(commands[target])
    if "chat" in groups:
        add_chat_command(groups["chat"])
    if "founder" in groups:
        add_draft_commands(app, groups["founder"])
    return app


CLIENT_COMMANDS = {"chat", "draft"}
CLIENT_VERBS = {"founder.eval"}
"""Commands inside a group that are clients too: `squad founder eval` calls `goals.grade`
and compares (FND-7)."""
"""Interactive clients of catalog operations. `squad chat` is the project chat in the
terminal (IF-4.8): it calls `chat.*`, `runs.interrupt` and the live stream, and defines no
operation of its own."""


def add_chat_command(group: typer.Typer) -> None:
    """`squad chat` with no subcommand opens the project chat in the terminal."""

    @group.callback(invoke_without_command=True, help="Open a project's chat in the terminal.")
    def chat(  # pyright: ignore[reportUnusedFunction]
        context: typer.Context,
        project: str = typer.Option(
            None, "--project", help="The project's id or name. Default: your only one."
        ),
    ) -> None:
        if context.invoked_subcommand is not None:
            return
        from nightsquad.surfaces.cli.chat.app import ChatApp
        from nightsquad.surfaces.cli.chat.client import ChatClient, ChatError

        client = ChatClient(http_client_factory(api_address()), current_token())
        try:
            projects = asyncio.run(client.projects())
        except httpx.TransportError as error:
            typer.echo(
                f"The server at {api_address()} did not answer. Start it with `squad up`.",
                err=True,
            )
            raise typer.Exit(ExitCode.ERROR) from error
        except (ChatError, OSError) as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(ExitCode.ERROR) from error
        matches = [p for p in projects if project in (None, p["project_id"], p["name"])]
        if len(matches) != 1:
            names = ", ".join(p["name"] for p in projects) or "none"
            typer.echo(f"Name one project. Yours: {names}.", err=True)
            raise typer.Exit(ExitCode.USAGE)
        ChatApp(client, matches[0]["project_id"], matches[0]["name"]).run()


def _signed_in_client() -> httpx.Client:
    token = current_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=api_address(), headers=headers, timeout=120)


_DOCUMENT = typer.Option(None, "--document", help="A brief to grill first.")
_GOALS = typer.Option(..., "--goal", help="A goal file. Repeat for more.")
_GRADES = typer.Option(..., "--grades", help="Its hand grades (JSON), in the same order.")


def add_draft_commands(app: typer.Typer, founder: typer.Typer) -> None:
    """`squad draft` is the Founder in the terminal (IF-4.6, IF-4.7), and `nightsquad
    founder eval` checks the grader against hand grades (FND-7). Both are clients of
    catalog operations."""

    @app.command(name="draft", help="Draft a project by talking with the Founder.")
    def draft(  # pyright: ignore[reportUnusedFunction]
        brief: str = typer.Option(None, "--brief", help="What you want done."),
        document: Path = _DOCUMENT,
        resume: str = typer.Option(None, "--resume", help="A conversation to carry on with."),
        quick: bool = typer.Option(False, "--quick", help="The Founder decides and starts."),
        credential: str = typer.Option(None, "--credential", help="Who pays, in quick mode."),
    ) -> None:
        from nightsquad.surfaces.cli.draft import run_draft

        with _signed_in_client() as client:
            try:
                run_draft(
                    client, brief=brief, document=document, resume=resume, quick=quick,
                    credential=credential,
                )  # fmt: skip
            except httpx.TransportError as error:
                typer.echo(
                    f"The server at {api_address()} did not answer. Start it with `squad up`.",
                    err=True,
                )
                raise typer.Exit(ExitCode.UNREACHABLE) from error

    @founder.command(name="eval", help="Grade goals with the Founder's model and compare.")
    def evaluate(  # pyright: ignore[reportUnusedFunction]
        goal: list[Path] = _GOALS,
        grades: list[Path] = _GRADES,
    ) -> None:
        from nightsquad.surfaces.cli.draft import run_eval

        with _signed_in_client() as client:
            raise typer.Exit(run_eval(client, list(zip(goal, grades, strict=True))))


def exposed_operations(app: typer.Typer) -> set[str]:
    """The operation names the CLI actually offers. A top-level command is a host-local
    operation unless it is a declared alias; anything else is reported under its own name."""
    names: set[str] = set()
    root = typer.main.get_command(app)
    if not isinstance(root, TyperGroup):
        return names
    for name, command in root.commands.items():
        if isinstance(command, TyperGroup):
            for verb in command.commands:
                names.add(f"{name}.{verb}".replace("-", "_"))
            names -= CLIENT_VERBS
        elif name not in ALIASES and name not in CLIENT_COMMANDS:
            names.add(f"{HOST_GROUP}.{name}".replace("-", "_"))
    return names


def main() -> None:
    """Entry point of the `squad` command (also installed as `nightsquad`) (IF-4.1)."""
    from nightsquad.runtime import host_executor

    load_domain_modules()
    invoker = HttpInvoker(http_client_factory(api_address()), current_token)
    app = build_cli(catalog, invoker, LocalInvoker(host_executor))
    app()
