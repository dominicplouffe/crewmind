"""The MCP server, with one tool per operation generated from the catalog (IF-1.2, section 9.5).

This adapter holds no business rules. `projects.hold` is the tool `projects_hold`. A client
sees and calls only the tools its scopes grant; any other tool answers as unknown (IF-5.2).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from mcp import Client
from mcp.server.lowlevel import Server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    GetPromptRequestParams,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    Prompt,
    PromptMessage,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)
from pydantic import ValidationError

from crewmind.catalog.caller import ANONYMOUS, Caller
from crewmind.catalog.execute import Executor
from crewmind.catalog.operation import CatalogError, Operation, Reversibility
from crewmind.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from crewmind.catalog.registry import Catalog
from crewmind.catalog.surfaces import Surface, exposed_on
from crewmind.surfaces.mcp import budget, confirm, resources
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


DETAIL, CONFIRM = "detail", "confirm"
"""Two arguments every tool accepts beside its own: how much to return (IF-5.7), and the
confirm token of an irreversible write (IF-5.3)."""


def _schema(operation: Operation) -> dict[str, Any]:
    schema = dict(operation.input.model_json_schema())
    extra: dict[str, Any] = {
        DETAIL: {
            "type": "string",
            "enum": ["summary", "full"],
            "description": "How much to return. Default: summary.",
        }
    }
    if operation.reversibility is Reversibility.IRREVERSIBLE:
        extra[CONFIRM] = {
            "type": "string",
            "description": "The confirm token from this tool's preview. Leave out to preview.",
        }
    schema["properties"] = {**schema.get("properties", {}), **extra}
    return schema


def _text(uri: str, text: str, mime: str = "application/json") -> ReadResourceResult:
    return ReadResourceResult(contents=[TextResourceContents(uri=uri, mime_type=mime, text=text)])


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
                Tool(name=name, description=operation.summary, input_schema=_schema(operation))
                for name, operation in granted(await caller_of(context)).items()
            ]
        )

    async def run(caller: Caller, name: str, arguments: dict[str, Any]) -> CallToolResult:
        operation = granted(caller).get(name)
        if operation is None:
            return _unknown(name)
        own = {key: value for key, value in arguments.items() if key not in (DETAIL, CONFIRM)}
        try:
            payload = operation.input.model_validate(own)
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
            if operation.reversibility is Reversibility.IRREVERSIBLE:
                token = arguments.get(CONFIRM)
                async with executor.sessions() as session, session.begin():
                    if token is None:
                        made = await confirm.issue(session, caller, name, own, executor.clock())
                        preview = {
                            "confirm_required": True,
                            "tool": name,
                            "what_it_does": operation.summary,
                            "arguments": own,
                            CONFIRM: made,
                            "expires_in_seconds": int(confirm.LIFE.total_seconds()),
                            "next": "This cannot be undone. Call the tool again with the same "
                            "arguments and this confirm token to do it.",
                        }
                        return CallToolResult(
                            content=[TextContent(text=json.dumps(preview))],
                            structured_content=preview,
                        )
                    await confirm.spend(session, caller, name, own, str(token), executor.clock())
            result = await executor.execute(operation, caller, payload)
        except Refusal as refusal:
            return _refused(refusal.envelope)
        data = budget.fit(for_ai_client(result), full=arguments.get(DETAIL) == "full")
        return CallToolResult(content=[TextContent(text=json.dumps(data))], structured_content=data)

    async def call_tool(context: Any, params: CallToolRequestParams) -> CallToolResult:
        return await run(await caller_of(context), params.name, dict(params.arguments or {}))

    async def list_resources(context: Any, _: PaginatedRequestParams | None) -> ListResourcesResult:
        caller = await caller_of(context)
        if not caller.mcp_scopes:
            return ListResourcesResult(resources=[])
        found = [
            Resource(name="desk", uri=resources.DESK, description="What waits on you."),
            *(
                Resource(name=uri.rsplit("/", 1)[-1], uri=uri, description=title)
                for uri, (title, _) in resources.DOCUMENTS.items()
            ),
        ]
        listed = await run(caller, "projects_list", {})
        content = cast(dict[str, Any], listed.structured_content or {})
        rows = cast(list[dict[str, Any]], content.get("items", []))
        for project in rows:
            found.append(
                Resource(
                    name=str(project["name"]),
                    uri=f"{resources.PROJECT}{project['project_id']}",
                    description=f"Project {project['name']}: its state and plan.",
                )
            )
        return ListResourcesResult(resources=found)

    async def read_resource(context: Any, params: ReadResourceRequestParams) -> ReadResourceResult:
        caller = await caller_of(context)
        uri = str(params.uri)
        if not caller.mcp_scopes:
            return _text(uri, "{}")
        if uri in resources.DOCUMENTS:
            return _text(uri, resources.document(uri), "text/markdown")
        if uri == resources.DESK:
            return _text(uri, json.dumps((await run(caller, "desk_show", {})).structured_content))
        if uri.startswith(resources.PROJECT):
            project = {"project_id": uri.removeprefix(resources.PROJECT)}
            status = await run(caller, "projects_status", project)
            plan = await run(caller, "plan_show", project)
            body = {"status": status.structured_content, "plan": plan.structured_content}
            return _text(uri, json.dumps(body))
        return _text(uri, json.dumps({"code": "unknown_resource"}))

    async def list_prompts(context: Any, _: PaginatedRequestParams | None) -> ListPromptsResult:
        return ListPromptsResult(
            prompts=[
                Prompt(name=name, description=title)
                for name, (title, _) in resources.PROMPTS.items()
            ]
        )

    async def get_prompt(context: Any, params: GetPromptRequestParams) -> GetPromptResult:
        title, text = resources.PROMPTS[params.name]
        return GetPromptResult(
            description=title,
            messages=[PromptMessage(role="user", content=TextContent(text=text))],
        )

    return Server(
        "crewmind",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
        on_list_prompts=list_prompts,
        on_get_prompt=get_prompt,
    )


async def exposed_operations(server: Server[Any], catalog: Catalog) -> set[str]:
    """The operation names the server actually lists, read through a real MCP client.

    A tool that maps to no operation is returned under its tool name, so the conformance
    check reports it as unknown.
    """
    by_tool = {tool_name(operation.name): operation.name for operation in catalog}
    async with Client(server) as client:
        listed = await client.list_tools()
    return {by_tool.get(tool.name, tool.name) for tool in listed.tools}
