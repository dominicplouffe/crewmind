"""Setting up, starting and checking an install (NFR-2, NFR-5, NFR-6, NFR-23, IF-4.2)."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import uvicorn
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from nightsquad.catalog.caller import Authority, InstanceRole
from nightsquad.catalog.define import Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.secret import OneTimeSecret
from nightsquad.domain.accounts.model import LinkKind, PersonState
from nightsquad.domain.accounts.people import create_invited, issue_link
from nightsquad.domain.install import old_name
from nightsquad.domain.install.account_operations import IF_4_2
from nightsquad.domain.install.config import NFR_6, Config, ConfigError, load_config
from nightsquad.domain.install.process import clear_pid, running_server, write_pid
from nightsquad.domain.secrets.store import MasterKey, ensure_master_key
from nightsquad.storage.migrate import migrate
from nightsquad.storage.models import Person


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
    steps.append(
        "Agents run in containers. `squad doctor` checks that they can."
        if config.sandbox_mode == "container"
        else "Agents run as plain processes of this user: for development only."
    )
    steps.extend(prepare(config))
    link: str | None = None
    admins = await context.session.scalar(
        select(func.count()).select_from(Person).where(Person.role == InstanceRole.ADMIN)
    )
    if admins:
        steps.append("An admin already exists; none was created.")
    elif payload.admin_email is None:
        steps.append("No admin yet. Run `squad bootstrap-admin --email <address>`.")
    else:
        person = await create_invited(context, payload.admin_email, "Admin", InstanceRole.ADMIN)
        assert person.state == PersonState.INVITED
        link, _ = await issue_link(context, person, LinkKind.INVITE)
        steps.append(f"First admin {person.email} created. Their setup link is below.")
    for step in setup_steps:
        done = await step(context, config)
        if done:
            steps.append(done)
    command = "squad up --slim" if payload.slim else "squad up"
    return SetupReport(
        steps=steps,
        setup_link=link,
        next=f"Start the server with `{command}`, then run `squad accept --link <link>`.",
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
    from nightsquad.runtime import build_runtime
    from nightsquad.server import create_app

    config = _config(payload.slim)
    record = running_server(config.data_dir)
    if record is not None:
        raise Refusal(
            "already_running",
            f"The server is already running from {config.data_dir} (pid {record['pid']}).",
            rule=IF_4_2.id,
            hint="Stop it first, or use another NIGHTSQUAD_DATA_DIR.",
        )
    prepare(config)
    app = create_app(build_runtime(config), run_runner=True)
    server = uvicorn.Server(
        uvicorn.Config(app, host=config.host, port=config.port, log_level="warning")
    )
    write_pid(config.data_dir)
    print(f"nightsquad is up at {config.base_url} ({config.database.value})", flush=True)
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
        fix=None if ok else "Run `squad setup`.",
    )


async def _check_old_name(config: Config) -> Finding:
    """NFR-5: settings or data still under the name used before ADR-0011."""
    found = old_name.leftovers(config)
    return Finding(
        check="old name",
        ok=not found,
        detail=" ".join(found) if found else "Nothing is left from before the rename.",
        fix="Move each one as the detail says, then run doctor again." if found else None,
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
            fix="Restore it from a backup. On a new install, run `squad setup`.",
        )
    private = (path.stat().st_mode & 0o077) == 0
    return Finding(
        check="master key",
        ok=private,
        detail=f"{path} {'is readable only by its owner' if private else 'is readable by others'}.",
        fix=None if private else f"Run `chmod 600 {path}`.",
    )


async def _check_database(config: Config) -> Finding:
    from nightsquad.runtime import build_runtime
    from nightsquad.server import is_ready

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
        fix=None if ready else "Check NIGHTSQUAD_DATABASE_URL, then run `squad setup`.",
    )


async def _check_server(config: Config) -> Finding:
    record = running_server(config.data_dir)
    return Finding(
        check="server",
        ok=record is not None,
        detail="The server is running." if record else "The server is not running.",
        fix=None if record else "Start it with `squad up`.",
    )


def _container_findings(config: Config) -> tuple[bool, str, str | None]:
    """Whether container sandboxes can run here: the runtime answers, the agent image is
    built, and a container can reach the agent API (EXE-12)."""
    from nightsquad.runner import containers
    from nightsquad.runtime import SANDBOX_IMAGE

    try:
        client = containers.docker_client()
        client.ping()
    except Exception:
        return (
            False,
            "Agents run in containers, and no container runtime answers.",
            "Start Docker and make sure this user may use it.",
        )
    if not client.images.list(name=SANDBOX_IMAGE):
        return (
            False,
            f"Agents run in containers, and the {SANDBOX_IMAGE} image is not built.",
            f"Run `docker build -f deploy/agent.Dockerfile -t {SANDBOX_IMAGE} .` in the "
            "source checkout, or install with `deploy/deploy_single_server.sh`.",
        )
    in_container = containers.own_container(client) is not None
    if containers.is_loopback_url(config.agent_api) and not in_container:
        return (
            False,
            f"Agents run in containers, and a container cannot reach {config.agent_api}: "
            "that address is this machine's own.",
            "Install with `deploy/deploy_single_server.sh`, or set NIGHTSQUAD_AGENT_API_URL to an "
            "address containers can reach (on Docker Desktop, "
            f"http://host.docker.internal:{config.port}).",
        )
    return True, f"Agents run in containers from the {SANDBOX_IMAGE} image.", None


async def _check_sandbox(config: Config) -> Finding:
    """EXE-12, P12: says which sandbox mode runs agents, and what it does not contain."""
    if config.sandbox_mode == "container":
        ok, detail, fix = await asyncio.to_thread(_container_findings, config)
        return Finding(check="sandbox", ok=ok, detail=detail, fix=fix)
    return Finding(
        check="sandbox",
        ok=True,
        detail="Agents run as plain processes of this user, with no isolation: "
        "for development only.",
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
    checks = [
        _check_data_dir,
        _check_old_name,
        _check_master_key,
        _check_database,
        _check_server,
        _check_sandbox,
        *doctor_checks,
    ]
    findings = [await check(config) for check in checks]
    return DoctorReport(healthy=all(finding.ok for finding in findings), findings=findings)
