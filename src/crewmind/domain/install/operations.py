"""Setting up, starting and checking an install (NFR-2, NFR-5, NFR-6, NFR-23, IF-4.2)."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import uvicorn
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from crewmind.catalog.caller import Authority, InstanceRole
from crewmind.catalog.define import Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.secret import OneTimeSecret
from crewmind.domain.accounts.model import LinkKind, PersonState
from crewmind.domain.accounts.people import create_invited, issue_link
from crewmind.domain.install.account_operations import IF_4_2
from crewmind.domain.install.config import NFR_6, Config, ConfigError, load_config
from crewmind.domain.install.process import clear_pid, running_server, write_pid
from crewmind.domain.secrets.store import MasterKey, ensure_master_key
from crewmind.storage.migrate import migrate
from crewmind.storage.models import Person


class SetupInput(BaseModel):
    admin_email: str | None = Field(None, description="Email address of the first admin.")
    slim: bool = Field(False, description="Set up a slim install on SQLite (NFR-23).")


class SetupReport(BaseModel):
    steps: list[str] = Field(description="What was done, or found already done.")
    setup_link: OneTimeSecret | None = Field(None, description="The first admin's setup link.")
    next: str


class UpInput(BaseModel):
    slim: bool = Field(False, description="Run one process on SQLite (NFR-23).")


class Stopped(BaseModel):
    stopped: bool = True


class Finding(BaseModel):
    check: str
    ok: bool
    detail: str
    fix: str | None = None


class DoctorReport(BaseModel):
    healthy: bool
    findings: list[Finding]


SetupStep = Callable[[Context, Config], Awaitable[str | None]]
setup_steps: list[SetupStep] = []
"""Later phases add their steps here: starter libraries (phase 7), Slack and email (phase 8)."""

DoctorCheck = Callable[[Config], Awaitable[Finding]]
doctor_checks: list[DoctorCheck] = []
"""Later phases add their checks here: Slack and email (phase 8)."""


def _config(slim: bool) -> Config:
    try:
        return load_config(slim=slim)
    except ConfigError as error:
        raise Refusal(
            "configuration_invalid",
            str(error),
            rule=NFR_6.id,
            hint="Fix the environment variable and run this again.",
        ) from None


def prepare(config: Config) -> list[str]:
    """Make the data directory, the master key and the schema exist. Safe to repeat (NFR-2)."""
    steps: list[str] = []
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.data_dir.chmod(0o700)
    steps.append(f"Data directory ready at {config.data_dir}.")
    created = ensure_master_key(config.master_key_file)
    steps.append(
        f"Master key {'created' if created else 'already present, left untouched'} at "
        f"{config.master_key_file}."
    )
    migrate(config.database_url)
    steps.append(f"Database schema is current ({config.database.value}).")
    return steps


@operation(
    "install.setup",
    summary="Set up this install: data directory, master key, database, first admin.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.REVERSIBLE,
)
async def setup(context: Context, payload: SetupInput) -> SetupReport:
    """NFR-2: idempotent. Checks prerequisites, creates the master key and never overwrites
    one, migrates, and creates the first admin with a setup link."""
    config = _config(payload.slim)
    steps = [f"Python {sys.version_info.major}.{sys.version_info.minor} found."]
    docker = shutil.which("docker")
    steps.append(
        "Docker found: agent runs will use containers."
        if docker
        else "Docker not found: needed from phase 2 to run agents in containers."
    )
    steps.extend(prepare(config))
    link: str | None = None
    admins = await context.session.scalar(
        select(func.count()).select_from(Person).where(Person.role == InstanceRole.ADMIN)
    )
    if admins:
        steps.append("An admin already exists; none was created.")
    elif payload.admin_email is None:
        steps.append("No admin yet. Run `crewmind bootstrap-admin --email <address>`.")
    else:
        person = await create_invited(context, payload.admin_email, "Admin", InstanceRole.ADMIN)
        assert person.state == PersonState.INVITED
        link, _ = await issue_link(context, person, LinkKind.INVITE)
        steps.append(f"First admin {person.email} created. Their setup link is below.")
    for step in setup_steps:
        done = await step(context, config)
        if done:
            steps.append(done)
    command = "crewmind up --slim" if payload.slim else "crewmind up"
    return SetupReport(
        steps=steps,
        setup_link=link,
        next=f"Start the server with `{command}`, then run `crewmind accept --link <link>`.",
    )


@operation(
    "install.up",
    summary="Start the server: the API, the MCP endpoint and the scheduler.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.REVERSIBLE,
)
async def up(context: Context, payload: UpInput) -> Stopped:
    """NFR-2, NFR-6, NFR-23: migrates on start and binds to localhost unless published
    with TLS. Slim mode is this one process on SQLite."""
    from crewmind.runtime import build_runtime
    from crewmind.server import create_app

    config = _config(payload.slim)
    record = running_server(config.data_dir)
    if record is not None:
        raise Refusal(
            "already_running",
            f"The server is already running from {config.data_dir} (pid {record['pid']}).",
            rule=IF_4_2.id,
            hint="Stop it first, or use another CREWMIND_DATA_DIR.",
        )
    prepare(config)
    app = create_app(build_runtime(config), run_runner=True)
    server = uvicorn.Server(
        uvicorn.Config(app, host=config.host, port=config.port, log_level="warning")
    )
    write_pid(config.data_dir)
    print(f"crewmind is up at {config.base_url} ({config.database.value})", flush=True)
    try:
        await server.serve()
    finally:
        clear_pid(config.data_dir)
    return Stopped()


async def _check_data_dir(config: Config) -> Finding:
    ok = config.data_dir.is_dir() and os.access(config.data_dir, os.W_OK)
    return Finding(
        check="data directory",
        ok=ok,
        detail=f"{config.data_dir} {'is writable' if ok else 'is missing or not writable'}.",
        fix=None if ok else "Run `crewmind setup`.",
    )


async def _check_master_key(config: Config) -> Finding:
    path: Path = config.master_key_file
    try:
        MasterKey.read(path)
    except Refusal:
        return Finding(
            check="master key",
            ok=False,
            detail=f"{path} is missing or unreadable.",
            fix="Restore it from a backup. On a new install, run `crewmind setup`.",
        )
    private = (path.stat().st_mode & 0o077) == 0
    return Finding(
        check="master key",
        ok=private,
        detail=f"{path} {'is readable only by its owner' if private else 'is readable by others'}.",
        fix=None if private else f"Run `chmod 600 {path}`.",
    )


async def _check_database(config: Config) -> Finding:
    from crewmind.runtime import build_runtime
    from crewmind.server import is_ready

    runtime = build_runtime(config)
    try:
        ready = await is_ready(runtime)
    finally:
        await runtime.close()
    return Finding(
        check="database",
        ok=ready,
        detail=f"The {config.database.value} database "
        + ("answers and its schema is current." if ready else "is unreachable or out of date."),
        fix=None if ready else "Check CREWMIND_DATABASE_URL, then run `crewmind setup`.",
    )


async def _check_server(config: Config) -> Finding:
    record = running_server(config.data_dir)
    return Finding(
        check="server",
        ok=record is not None,
        detail="The server is running." if record else "The server is not running.",
        fix=None if record else "Start it with `crewmind up`.",
    )


@operation(
    "install.doctor",
    summary="Check the whole install and print a fix for each finding.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.READ,
)
async def doctor(context: Context, payload: Empty) -> DoctorReport:
    """NFR-5: every finding comes with its fix."""
    try:
        config = load_config()
    except ConfigError as error:
        finding = Finding(
            check="configuration", ok=False, detail=str(error), fix="Fix the environment variable."
        )
        return DoctorReport(healthy=False, findings=[finding])
    checks = [_check_data_dir, _check_master_key, _check_database, _check_server, *doctor_checks]
    findings = [await check(config) for check in checks]
    return DoctorReport(healthy=all(finding.ok for finding in findings), findings=findings)
