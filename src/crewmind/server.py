"""The server process: the API, the MCP endpoint and the scheduler (section 10, NFR-5)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from collections.abc import AsyncGenerator

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import text
from sqlalchemy.engine import Connection
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from crewmind.catalog.caller import CallerKind
from crewmind.catalog.execute import unauthenticated
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.registry import catalog
from crewmind.jobs.dispatcher import Dispatcher
from crewmind.jobs.scheduler import Scheduler
from crewmind.runner.sandbox import ContainerSandbox, Sandbox, UnisolatedSandbox
from crewmind.runner.supervisor import Runner
from crewmind.runtime import Runtime
from crewmind.storage.migrate import alembic_config
from crewmind.surfaces.agent_api.app import add_agent_api
from crewmind.surfaces.api.app import STATUS_BY_KIND, build_api
from crewmind.surfaces.mcp.server import CALLER_STATE, build_mcp

MCP_PATH = "/mcp"
RUNNER_WORKERS = 4
"""Runs one runner executes at once. A project's own limit is `run.concurrency`."""

logger = logging.getLogger(__name__)


def _schema_is_current(connection: Connection) -> bool:
    head = ScriptDirectory.from_config(alembic_config(connection.engine.url)).get_current_head()
    return MigrationContext.configure(connection).get_current_revision() == head


async def is_ready(runtime: Runtime) -> bool:
    """NFR-5: ready means the database answers and its schema is current."""
    try:
        async with runtime.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            return await connection.run_sync(_schema_is_current)
    except Exception:
        return False


class McpAuthentication:
    """Authenticates every MCP request with the client's own bearer token (IF-5.1). A
    request without a valid MCP token is refused before it reaches the MCP server."""

    def __init__(self, app: ASGIApp, runtime: Runtime) -> None:
        self._app = app
        self._runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(MCP_PATH):
            await self._app(scope, receive, send)
            return
        headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
        header = headers.get("authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else None
        try:
            caller = await self._runtime.authenticator.authenticate(token, on_mcp=True)
            if caller.kind is not CallerKind.PERSON:
                raise unauthenticated()
        except Refusal as refusal:
            envelope = refusal.envelope
            response = JSONResponse(
                envelope.model_dump(), status_code=STATUS_BY_KIND[envelope.kind]
            )
            await response(scope, receive, send)
            return
        scope[CALLER_STATE] = caller
        await self._app(scope, receive, send)


def build_sandbox(runtime: Runtime) -> Sandbox:
    """The sandbox mode the install is configured for (EXE-12)."""
    config = runtime.config
    if config.sandbox_mode == "unisolated":
        return UnisolatedSandbox()
    if config.sandbox_mode == "container":
        return ContainerSandbox(
            image="crewmind-agent",
            install_id=hashlib.sha256(str(config.data_dir).encode()).hexdigest()[:12],
            cpus=config.sandbox_cpus,
            memory_bytes=config.sandbox_memory,
        )
    raise ValueError(f"sandbox mode {config.sandbox_mode} is not available yet")


def build_runner(runtime: Runtime, sandbox: Sandbox, workers: int = RUNNER_WORKERS) -> Runner:
    return Runner(
        runtime.sessions,
        runtime.settings,
        runtime.clock,
        sandbox,
        api_url=runtime.config.agent_api,
        workspaces=runtime.config.data_dir / "workspaces",
        workers=workers,
    )


def create_app(
    runtime: Runtime, *, run_scheduler: bool = True, run_runner: bool = False
) -> FastAPI:
    """The whole server as one ASGI app. With `run_runner`, one runner works in this
    process, as slim mode needs (NFR-23)."""
    mcp_server = build_mcp(catalog, runtime.executor)
    mcp_app = mcp_server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        tasks: list[asyncio.Task[None]] = []
        if run_scheduler:
            scheduler = Scheduler(runtime.sessions, runtime.clock, runtime.settings)
            dispatcher = Dispatcher(runtime.sessions, runtime.settings, runtime.clock)
            tasks += [asyncio.create_task(scheduler.run()), asyncio.create_task(dispatcher.run())]
        if run_runner:
            try:
                runner = build_runner(runtime, build_sandbox(runtime))
            except Exception as error:
                logger.error("no runner started: the sandbox is unavailable (%s)", error)
            else:
                tasks.append(asyncio.create_task(runner.run()))
        async with mcp_server.session_manager.run():
            yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await runtime.close()

    app = build_api(
        catalog, runtime.executor, runtime.authenticator, base_url=runtime.config.base_url
    )
    app.router.lifespan_context = lifespan
    add_agent_api(
        app, catalog, runtime.executor, runtime.run_authenticator, runtime.gateway, runtime.settings
    )

    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    async def readyz() -> JSONResponse:
        ready = await is_ready(runtime)
        return JSONResponse(
            {"status": "ready" if ready else "not ready"}, status_code=200 if ready else 503
        )

    app.add_api_route("/healthz", healthz, methods=["GET"], include_in_schema=False)
    app.add_api_route("/readyz", readyz, methods=["GET"], include_in_schema=False)
    app.router.routes.append(Mount("", app=McpAuthentication(mcp_app, runtime)))
    return app
