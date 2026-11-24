"""The `squad` command: help, secrets, options and stored login (IF-4.1, IF-4.3, IF-4.5)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from nightsquad.catalog import Surface, catalog
from nightsquad.catalog.registry import load_domain_modules
from nightsquad.catalog.surfaces import exposed_on
from nightsquad.surfaces.cli.config import CliState
from nightsquad.surfaces.cli.main import ALIASES, ExitCode, build_cli
from tests.support import PASSWORD, App, OnLoop, invoker_for, run_cli


def test_IF_4_3_nightsquad_help_runs() -> None:
    """IF-4.3: `squad --help` exits 0 and lists the command groups."""
    result = subprocess.run(
        [sys.executable, "-m", "nightsquad", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    for group in ("projects", "settings", "record", "login", "up", "doctor", "backup"):
        assert group in result.stdout


HAND_WRITTEN = {"draft", "eval"}
"""Interactive clients of catalog operations (IF-4.6): they print a conversation, not a
result."""


def test_IF_4_3_every_command_has_help_and_json() -> None:
    """IF-4.3: every generated command offers --help and --json."""
    load_domain_modules()
    invoker = invoker_for(None)  # type: ignore[arg-type]
    root = get_command(build_cli(catalog, invoker, invoker))
    commands = []
    for name, command in root.commands.items():  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
        commands.extend(getattr(command, "commands", {name: command}).values())  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    on_cli = [o for o in catalog if exposed_on(o, Surface.CLI)]
    assert len(commands) >= len(on_cli)  # pyright: ignore[reportUnknownArgumentType]
    for command in commands:  # pyright: ignore[reportUnknownVariableType]
        options = {option for parameter in command.params for option in parameter.opts}  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if command.name in HAND_WRITTEN:  # pyright: ignore[reportUnknownMemberType]
            continue
        assert "--json" in options, command.name  # pyright: ignore[reportUnknownMemberType]
    for alias, target in ALIASES.items():
        assert target in catalog, alias


def test_IF_4_5_a_secret_is_never_a_command_line_argument() -> None:
    """IF-4.5: no command takes a password as an argument. Each offers a file and standard
    input instead, and a hidden prompt on a terminal."""
    load_domain_modules()
    invoker = invoker_for(None)  # type: ignore[arg-type]
    cli = build_cli(catalog, invoker, invoker)
    runner = CliRunner()
    for arguments in (["login"], ["auth", "change-password"], ["accept"]):
        text = runner.invoke(cli, [*arguments, "--help"]).output
        assert "-file" in text
        assert "-stdin" in text
    refused = runner.invoke(cli, ["login", "--email", "a@example.com", "--password", PASSWORD])
    assert refused.exit_code == ExitCode.USAGE
    assert "No such option" in refused.output
    missing = runner.invoke(cli, ["login", "--email", "a@example.com", "--json"])
    assert missing.exit_code == ExitCode.USAGE
    assert PASSWORD not in missing.output


async def test_IF_4_1_login_stores_a_personal_token_and_logout_revokes_it(
    app: App, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """IF-4.1, IF-4.5, ACC-3: `squad login` reads the password from a file, keeps a
    personal token in a private file, never prints a credential, and ends its session.
    `squad logout` revokes the token on the server."""
    monkeypatch.setenv("NIGHTSQUAD_DATA_DIR", str(tmp_path / "cli"))
    monkeypatch.delenv("NIGHTSQUAD_TOKEN", raising=False)
    alice = await app.person("alice@example.com")
    password_file = tmp_path / "password"
    password_file.write_text(PASSWORD + "\n")
    from nightsquad.surfaces.cli.config import current_token
    from nightsquad.surfaces.cli.invoke import HttpInvoker
    from tests.support import api_client_factory

    invoker = OnLoop(HttpInvoker(api_client_factory(app.api), current_token))
    cli = build_cli(catalog, invoker, invoker)

    signed_in = await run_cli(
        cli, ["login", "--email", alice.email, "--password-file", str(password_file), "--json"]
    )
    assert signed_in.exit_code == 0, signed_in.output
    state = CliState.load()
    assert state.token is not None
    assert state.token.startswith("ns_pat_")
    assert (CliState.path().stat().st_mode & 0o077) == 0
    assert state.token not in signed_in.output
    assert "ns_ses_" not in signed_in.output
    assert json.loads(signed_in.stdout)["signed_in_as"] == "alice"

    who = await run_cli(cli, ["whoami", "--json"])
    assert json.loads(who.stdout)["email"] == alice.email
    changed = await run_cli(
        cli,
        [
            "settings",
            "change-mine",
            "--changes",
            "chat.brevity=short",
            "--changes",
            "agenda.days=7",
        ],
    )
    assert changed.exit_code == 0, changed.output
    assert "chat.brevity: short" not in changed.output
    assert "name=chat.brevity, value=short" in changed.output

    sessions = await app.ok("record.list_install", await app.admin(), type="session.ended")
    assert any(event["detail"]["cause"] == "sign-out" for event in sessions["items"])
    out = await run_cli(cli, ["logout"])
    assert out.exit_code == 0
    assert not CliState.path().exists()
    assert (await app.call("auth.whoami", state.token)).status_code == 401


def test_IF_4_8_nightsquad_chat_opens_the_terminal_chat_and_keeps_its_subcommands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IF-4.8, CHAT-1: `squad chat` with no subcommand opens the project chat in the
    terminal; `squad chat send` and the other chat commands still exist beside it."""
    from nightsquad.surfaces.cli.chat.app import ChatApp
    from nightsquad.surfaces.cli.chat.client import ChatClient

    opened: list[str] = []

    async def projects(self: ChatClient) -> list[dict[str, str]]:
        return [{"project_id": "p1", "name": "Atlas"}, {"project_id": "p2", "name": "Borealis"}]

    monkeypatch.setattr(ChatClient, "projects", projects)
    monkeypatch.setattr(ChatApp, "run", lambda self: opened.append(self.title or ""))  # pyright: ignore[reportUnknownLambdaType, reportUnknownMemberType, reportUnknownArgumentType]
    load_domain_modules()
    invoker = invoker_for(None)  # type: ignore[arg-type]
    cli = build_cli(catalog, invoker, invoker)
    runner = CliRunner()

    unclear = runner.invoke(cli, ["chat"])
    assert unclear.exit_code == ExitCode.USAGE
    assert "Atlas, Borealis" in unclear.output
    assert runner.invoke(cli, ["chat", "--project", "Borealis"]).exit_code == 0
    assert len(opened) == 1
    assert "Send a message" in runner.invoke(cli, ["chat", "send", "--help"]).output
    assert len(opened) == 1
