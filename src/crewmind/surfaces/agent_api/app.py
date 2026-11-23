"""The agent API over HTTP, generated from the operation catalog (IF-1.2, IF-6.1 to IF-6.3).

This adapter holds no business rules. Every call carries the run token. Every refusal is a
403 with the shared envelope and counts toward the run's refusal cap (IF-6.1, EXE-10).
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from crewmind.catalog.execute import Executor
from crewmind.catalog.operation import Operation
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.registry import Catalog
from crewmind.catalog.surfaces import Surface, exposed_on
from crewmind.domain.connections import mcp_calls
from crewmind.domain.connections.delivery import Masker
from crewmind.domain.execution import runs
from crewmind.domain.execution.agent import RunAuthenticator
from crewmind.domain.settings.service import SettingsService
from crewmind.gateway.protocol import CompletionRequest, ToolSpec
from crewmind.gateway.service import Gateway
from crewmind.storage.models import Run, RunStep

Masks = Callable[[str], Awaitable[Masker]]
"""A run's masker (CON-8): `model(payload)` returns the payload with given secrets masked."""

logger = logging.getLogger(__name__)

AGENT_PREFIX = "/agent/v1"
GATEWAY_PATH = "/gateway/v1/complete"
TOOL_CALL = "tool call"
HARNESS_ONLY = frozenset({"agent.context", "agent.environment", "agent.call_mcp_tool"})
MCP_CALL = "agent.call_mcp_tool"
MCP_PREFIX = f"{AGENT_PREFIX}/mcp"
"""Agent API calls the harness makes itself, never offered to the model as tools."""


def route_path(operation_name: str) -> str:
    return f"{AGENT_PREFIX}/{operation_name.replace('.', '/')}"


def tool_name(operation_name: str) -> str:
    return operation_name.replace(".", "_")


def bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


class ToolList(BaseModel):
    tools: list[ToolSpec]
    paths: dict[str, str]


def _endpoint(
    operation: Operation,
    executor: Executor,
    authenticator: RunAuthenticator,
    settings: SettingsService,
    masks: Masks | None,
) -> Callable[..., Awaitable[JSONResponse]]:
    async def endpoint(request: Request, payload: Any) -> JSONResponse:
        caller = await authenticator.authenticate(bearer(request))
        assert caller.run_id is not None
        now = executor.clock()
        if masks is not None:
            # CON-8: a given secret never enters the platform through what an agent sends.
            payload = (await masks(caller.run_id)).model(payload)
        try:
            result = await executor.execute(operation, caller, payload)
        except Refusal as refusal:
            async with executor.sessions() as session, session.begin():
                final = await runs.record_refusal(
                    session, settings, caller.run_id, operation.name, refusal, now
                )
                session.add(
                    _step(caller.run_id, operation, payload, final.envelope.model_dump(), now)
                )
            return JSONResponse(final.envelope.model_dump(), status_code=403)
        data = result.model_dump(mode="json")
        async with executor.sessions() as session, session.begin():
            await runs.note_success(session, caller.run_id, operation.name)
            if operation.name not in HARNESS_ONLY:
                session.add(_step(caller.run_id, operation, payload, {"ok": True}, now))
        return JSONResponse(data)

    parameters = [
        inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
        inspect.Parameter(
            "payload", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=operation.input
        ),
    ]
    endpoint.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    endpoint.__annotations__ = {"request": Request, "payload": operation.input}
    return endpoint


def _step(
    run_id: str, operation: Operation, payload: BaseModel, outcome: dict[str, Any], now: Any
) -> RunStep:
    return RunStep(
        run_id=run_id,
        kind=TOOL_CALL,
        data={
            "tool": operation.name,
            "arguments": payload.model_dump(mode="json"),
            "outcome": outcome,
        },
        at=now,
    )


def add_agent_api(
    app: FastAPI,
    catalog: Catalog,
    executor: Executor,
    authenticator: RunAuthenticator,
    gateway: Gateway,
    settings: SettingsService,
    masks: Masks | None = None,
) -> None:
    """Add the agent API routes and the model gateway route to the server. With `masks`,
    every request an agent sends is masked before anything reads it (CON-8)."""
    router = app
    exposed = [operation for operation in catalog if exposed_on(operation, Surface.AGENT_API)]
    for operation in exposed:
        router.add_api_route(
            route_path(operation.name),
            _endpoint(operation, executor, authenticator, settings, masks),
            methods=["POST"],
            response_model=operation.output,
            operation_id=f"agent:{operation.name}",
            summary=operation.summary,
            include_in_schema=False,
        )

    async def tools(request: Request) -> ToolList:
        """The tools this run's agent may call, as the model sees them: the catalog's agent
        operations, then the allowed tools of the MCP servers granted to its role (CON-13)."""
        caller = await authenticator.authenticate(bearer(request))
        offered = [
            operation
            for operation in exposed
            if operation.name not in HARNESS_ONLY
            and not (operation.authority.value == "agent_ceo" and caller.seat_kind != "ceo")
        ]
        listed = ToolList(
            tools=[
                ToolSpec(
                    name=tool_name(operation.name),
                    description=operation.summary,
                    input_schema=operation.input.model_json_schema(),
                )
                for operation in offered
            ],
            paths={tool_name(operation.name): route_path(operation.name) for operation in offered},
        )
        assert caller.run_id is not None
        async with executor.sessions() as session:
            run = await session.get(Run, caller.run_id)
            mcp_tools = await mcp_calls.offered(session, run) if run is not None else []
        for item in mcp_tools:
            listed.tools.append(
                ToolSpec(
                    name=item.name,
                    description=f"[MCP server {item.connection.name}] {item.tool.description}",
                    input_schema=item.tool.input_schema or {"type": "object", "properties": {}},
                )
            )
            listed.paths[item.name] = (
                f"{MCP_PREFIX}/{item.connection.id}/{quote(item.tool.name, safe='')}"
            )
        return listed

    async def complete(request: Request, payload: CompletionRequest) -> JSONResponse:
        """The model gateway. A refusal here is the per-run cap (GOV-6). The request is
        masked first, so a given secret never reaches the provider or the trace (CON-8)."""
        if masks is not None:
            try:
                caller = await authenticator.authenticate(bearer(request))
            except Refusal:
                caller = None
            if caller is not None and caller.run_id is not None:
                payload = (await masks(caller.run_id)).model(payload)
        try:
            response = await gateway.complete(bearer(request), payload)
        except Refusal as refusal:
            status = 401 if refusal.envelope.kind is RefusalKind.UNAUTHENTICATED else 403
            return JSONResponse(refusal.envelope.model_dump(), status_code=status)
        except Exception as error:
            logger.warning("gateway: the provider call failed: %s", error)
            return JSONResponse(
                {"code": "provider_failed", "message": f"The model provider failed: {error}"},
                status_code=502,
            )
        return JSONResponse(response.model_dump(mode="json"))

    if MCP_CALL in catalog:
        call = _endpoint(catalog.get(MCP_CALL), executor, authenticator, settings, masks)

        async def mcp_tool(request: Request, server: str, tool: str) -> JSONResponse:
            """CON-13: an MCP tool call as the model makes it, adapted to agent.call_mcp_tool. The
            body is the tool's own arguments."""
            try:
                body = await request.json()
            except ValueError:
                body = {}
            arguments: dict[str, Any] = (
                {str(key): value for key, value in cast(dict[Any, Any], body).items()}
                if isinstance(body, dict)
                else {}
            )
            payload = mcp_calls.CallInput(server=server, tool=tool, arguments=arguments)
            return await call(request, payload)

        router.add_api_route(
            f"{MCP_PREFIX}/{{server}}/{{tool}}", mcp_tool, methods=["POST"], include_in_schema=False
        )

    router.add_api_route(f"{AGENT_PREFIX}/tools", tools, methods=["GET"], include_in_schema=False)
    router.add_api_route(GATEWAY_PATH, complete, methods=["POST"], include_in_schema=False)


def exposed_operations(app: FastAPI) -> set[str]:
    """The operation names the agent API actually serves."""
    names: set[str] = set()
    for route in app.routes:
        if (
            isinstance(route, APIRoute)
            and route.path.startswith(f"{AGENT_PREFIX}/")
            # MCP tool calls are adapted to agent.call_mcp_tool, which has its own route.
            and not route.path.startswith(f"{MCP_PREFIX}/")
        ):
            name = route.path.removeprefix(f"{AGENT_PREFIX}/").replace("/", ".")
            if name != "tools":
                names.add(name)
    return names
