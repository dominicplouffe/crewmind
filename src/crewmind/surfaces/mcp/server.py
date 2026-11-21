"""The MCP server, with one tool per operation generated from the catalog (IF-1.2, section 9.5).

This adapter holds no business rules. `projects.hold` is the tool `projects_hold`.
"""

from __future__ import annotations

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

from crewmind.catalog.operation import CatalogError, Operation
from crewmind.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from crewmind.catalog.registry import Catalog
from crewmind.catalog.surfaces import Surface, exposed_on


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


def build_mcp(catalog: Catalog) -> Server[Any]:
    """Build the MCP server with one tool per operation that belongs on it."""
    tools = _tools(catalog)

    async def list_tools(_: Any, __: PaginatedRequestParams | None) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                Tool(
                    name=name,
                    description=operation.summary,
                    input_schema=operation.input.model_json_schema(),
                    output_schema=operation.output.model_json_schema(),
                )
                for name, operation in tools.items()
            ]
        )

    async def call_tool(_: Any, params: CallToolRequestParams) -> CallToolResult:
        operation = tools.get(params.name)
        if operation is None:
            return _refused(
                ErrorEnvelope(
                    kind=RefusalKind.NOT_FOUND,
                    code="unknown_tool",
                    message=f"There is no tool named {params.name}.",
                )
            )
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
            result = await operation.handler(payload)
        except Refusal as refusal:
            return _refused(refusal.envelope)
        return CallToolResult(
            content=[TextContent(text=result.model_dump_json())],
            structured_content=result.model_dump(mode="json"),
        )

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
