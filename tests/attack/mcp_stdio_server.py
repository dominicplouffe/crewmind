"""A tiny MCP server spoken over standard input and output, for the command-server tests.
It reports only facts about its environment, never a value."""

from __future__ import annotations

import os

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("notes tools", version="0.1")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def token_length() -> int:
    """The length of the BLOG_TOKEN it was given."""
    return len(os.environ.get("BLOG_TOKEN", ""))


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def environment_names() -> str:
    """The names of the environment variables it can see."""
    return ",".join(sorted(os.environ))


@server.tool()
def write_note(text: str) -> str:
    """Write a note."""
    return f"noted {text}"


if __name__ == "__main__":
    server.run("stdio")
