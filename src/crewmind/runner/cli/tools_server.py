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
from typing import Any

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


def build(client: httpx.AsyncClient) -> Server[Any, Any]:
    server: Server[Any, Any] = Server(SERVER_NAME)
    paths: dict[str, str] = {}

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:  # pyright: ignore[reportUnusedFunction]
        listed = (await client.get(TOOLS_PATH)).json()
        paths.update(listed["paths"])
        return [
            types.Tool(
                name=tool["name"],
                description=tool.get("description", ""),
                inputSchema=tool.get("input_schema") or {"type": "object", "properties": {}},
            )
            for tool in listed["tools"]
        ]

    @server.call_tool()
    async def call_tool(  # pyright: ignore[reportUnusedFunction]
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        if not paths:
            await list_tools()
        if name not in paths:
            return [types.TextContent(type="text", text=f"There is no tool named {name}.")]
        response = await client.post(paths[name], json=arguments or {})
        if response.status_code == 401:
            # The run token no longer works: the run was stopped, or it reached a cap.
            text = "This run has been stopped. Make no more calls and end now."
        elif response.status_code == 403:
            text = refusal_text(response.json())
        else:
            response.raise_for_status()
            text = json.dumps(response.json())
        return [types.TextContent(type="text", text=text)]

    return server


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
