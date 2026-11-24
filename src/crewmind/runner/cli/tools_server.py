"""The agent API as MCP tools, for a command-line agent to mount (IF-6.1, LLM-8, P3).

It runs inside the sandbox beside the agent and speaks MCP over standard input and
output. Every tool is one agent API call made with the run token, so the server's rules
decide what happens exactly as they do for every other harness. It imports nothing from
the server.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, cast

import httpx
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from crewmind.runner.agent import TOOLS_PATH

SERVER_NAME = "crewmind"
CALL_TIMEOUT_SECONDS = 300


def refusal_text(refused: dict[str, Any]) -> str:
    """A refusal as the model should read it: what was refused, the rule, and what to do."""
    parts = [f"Refused: {refused.get('message', 'the server refused this call.')}"]
    if refused.get("rule"):
        parts.append(f"Rule: {refused['rule']}.")
    if refused.get("hint"):
        parts.append(str(refused["hint"]))
    return " ".join(parts)


STOPPED = "This run has been stopped. Make no more calls and end now."
"""The run token no longer works: the run was stopped, or it reached a cap."""


def _text(text: str, *, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=error)


def _answer(response: httpx.Response) -> types.CallToolResult:
    """An agent API answer as the model reads it. Every refusal, a bad argument included,
    is text it can act on, never an exception that ends the call."""
    if response.status_code == 401:
        return _text(STOPPED, error=True)
    if response.status_code >= 500:
        return _text(
            f"The crewmind server failed ({response.status_code}). Try again shortly.", error=True
        )
    try:
        body: Any = response.json()
    except ValueError:
        body = None
    if response.status_code >= 400:
        refused = cast(dict[str, Any], body) if isinstance(body, dict) else {}
        return _text(refusal_text(refused), error=True)
    return _text(json.dumps(body))


def build(client: httpx.AsyncClient) -> Server[Any]:
    """One MCP tool per agent API tool the run may use, listed from the server each time."""
    paths: dict[str, str] = {}

    async def fetch() -> list[dict[str, Any]] | None:
        """The run's tools, or None once its token no longer works."""
        response = await client.get(TOOLS_PATH)
        if response.status_code == 401:
            return None
        response.raise_for_status()
        listed = response.json()
        paths.update(listed["paths"])
        return list(listed["tools"])

    async def list_tools(
        _context: Any, _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    input_schema=tool.get("input_schema") or {"type": "object", "properties": {}},
                )
                for tool in await fetch() or []
            ]
        )

    async def call_tool(_context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        if not paths and await fetch() is None:
            return _text(STOPPED, error=True)
        if params.name not in paths:
            return _text(f"There is no tool named {params.name}.", error=True)
        return _answer(await client.post(paths[params.name], json=dict(params.arguments or {})))

    return Server(SERVER_NAME, on_list_tools=list_tools, on_call_tool=call_tool)


async def _main() -> int:
    headers = {"Authorization": f"Bearer {os.environ['CREWMIND_RUN_TOKEN']}"}
    async with httpx.AsyncClient(
        base_url=os.environ["CREWMIND_AGENT_API"], headers=headers, timeout=CALL_TIMEOUT_SECONDS
    ) as client:
        server = build(client)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
