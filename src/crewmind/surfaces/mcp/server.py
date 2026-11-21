"""The MCP server, with one tool per operation generated from the catalog (IF-1.2, section 9.5).

This adapter holds no business rules. `projects.hold` is the tool `projects_hold`. A client
sees and calls only the tools its scopes grant; any other tool answers as unknown (IF-5.2).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp import Client
from mcp.server.lowlevel import Server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from pydantic import ValidationError

from crewmind.catalog.caller import ANONYMOUS, Caller
from crewmind.catalog.execute import Executor
from crewmind.catalog.operation import CatalogError, Operation
from crewmind.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from crewmind.catalog.registry import Catalog
from crewmind.catalog.surfaces import Surface, exposed_on
from crewmind.surfaces.mcp.untrusted import for_ai_client

CallerOf = Callable[[Any], Awaitable[Caller]]
"""Finds the caller behind an MCP request context."""

CALLER_STATE = "crewmind_caller"


async def caller_from_http(context: Any) -> Caller:
    """The caller the HTTP layer authenticated and attached to the request (IF-5.1)."""
    request = getattr(context, "request", None)
    if request is None:
        return ANONYMOUS
    caller = request.scope.get(CALLER_STATE, ANONYMOUS)
    assert isinstance(caller, Caller)
    return caller


def tool_name(operation_name: str) -> str:
    return operation_name.replace(".", "_")


def _tools(catalog: Catalog) -> dict[str, Operation]:
    tools: dict[str, Operation] = {}
    for operation in catalog:
        if not exposed_on(operation, Surface.MCP):
            continue
        name = tool_name(operation.name)
        if name in tools:
            raise CatalogError(
                f"operations {tools[name].name} and {operation.name} share the MCP tool name {name}"
            )
        tools[name] = operation
    return tools


def _refused(envelope: ErrorEnvelope) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(text=envelope.model_dump_json())],
        structured_content=envelope.model_dump(mode="json"),
        is_error=True,
    )


def _unknown(name: str) -> CallToolResult:
    return _refused(
        ErrorEnvelope(
            kind=RefusalKind.NOT_FOUND,
            code="unknown_tool",
            message=f"There is no tool named {name}.",
        )
    )


def build_mcp(
    catalog: Catalog, executor: Executor, caller_of: CallerOf = caller_from_http
) -> Server[Any]:
    """Build the MCP server with one tool per operation that belongs on it."""
    tools = _tools(catalog)

    def granted(caller: Caller) -> dict[str, Operation]:
        return {
            name: operation
            for name, operation in tools.items()
            if operation.mcp_scope in caller.mcp_scopes
        }

    async def list_tools(context: Any, _: PaginatedRequestParams | None) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                Tool(
                    name=name,
                    description=operation.summary,
                    input_schema=operation.input.model_json_schema(),
                )
                for name, operation in granted(await caller_of(context)).items()
            ]
        )

    async def call_tool(context: Any, params: CallToolRequestParams) -> CallToolResult:
        caller = await caller_of(context)
        operation = granted(caller).get(params.name)
        if operation is None:
            return _unknown(params.name)
        try:
            payload = operation.input.model_validate(params.arguments or {})
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
                for problem in error.errors()
            )
            return _refused(
                ErrorEnvelope(
                    kind=RefusalKind.INVALID,
                    code="invalid_input",
                    message=f"The input is not valid: {problems}",
                    hint="Check the operation's input schema.",
                )
            )
        try:
            result = await executor.execute(operation, caller, payload)
        except Refusal as refusal:
            return _refused(refusal.envelope)
        data = for_ai_client(result)
        return CallToolResult(content=[TextContent(text=json.dumps(data))], structured_content=data)

    return Server("crewmind", on_list_tools=list_tools, on_call_tool=call_tool)


async def exposed_operations(server: Server[Any], catalog: Catalog) -> set[str]:
    """The operation names the server actually lists, read through a real MCP client.

    A tool that maps to no operation is returned under its tool name, so the conformance
    check reports it as unknown.
    """
    by_tool = {tool_name(operation.name): operation.name for operation in catalog}
    async with Client(server) as client:
        listed = await client.list_tools()
    return {by_tool.get(tool.name, tool.name) for tool in listed.tools}
