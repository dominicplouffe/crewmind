"""One run on the Claude Code command-line agent (`claude -p`), with a subscription login
(LLM-2, LLM-8).

The login is the token `claude setup-token` prints. The agent's own tools are offered only
as the role grants them, the workspace's own settings are not loaded, and the agent API is
mounted as MCP tools.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from crewmind.runner.cli.base import Driver, Event, Failed, Final, Said, Setup, Start, Used, main
from crewmind.runner.cli.tools_server import SERVER_NAME

OWN_TOOLS = {
    "files": ("Read", "Write", "Edit", "Glob", "Grep"),
    "shell": ("Bash",),
    "web": ("WebSearch", "WebFetch"),
}
"""The agent's own tools, by the grant that allows each (LLM-8)."""

EFFORTS = {"low", "medium", "high", "max"}
TRANSIENT_STATUSES = (429, 500, 502, 503, 504, 529)


def _status_kind(status: Any) -> str | None:
    if status in (401, 403):
        return "auth"
    return "transient" if status in TRANSIENT_STATUSES else None


class ClaudeCode(Driver):
    name = "claude_code"
    label = "Claude Code"

    def prepare(self, setup: Setup) -> Start:
        own = [
            tool for grant, tools in OWN_TOOLS.items() if grant in setup.grants for tool in tools
        ]
        allowed = [*own, *(f"mcp__{SERVER_NAME}__{name}" for name in setup.tool_names)]
        servers = {"mcpServers": {SERVER_NAME: {"type": "stdio", **setup.tools_server()}}}
        argv = [
            "claude",
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--system-prompt-file",
            str(setup.write("system-prompt.md", setup.system_prompt)),
            "--tools",
            ",".join(own),
            "--allowedTools",
            ",".join(allowed),
            "--permission-mode",
            "bypassPermissions",
            "--mcp-config",
            str(setup.write("mcp.json", json.dumps(servers))),
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--no-session-persistence",
        ]
        if setup.names_a_model:
            argv += ["--model", setup.model]
        if setup.effort in EFFORTS:
            argv += ["--effort", setup.effort]
        env = setup.environment(
            CLAUDE_CODE_OAUTH_TOKEN=setup.login,
            CLAUDE_CONFIG_DIR=str(setup.home / "claude"),
            DISABLE_AUTOUPDATER="1",
            DISABLE_TELEMETRY="1",
            DISABLE_ERROR_REPORTING="1",
            CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
        )
        return Start(argv, env, stdin=setup.prompt)

    def parse(self, record: dict[str, Any]) -> list[Event]:
        kind = record.get("type")
        if kind == "assistant":
            blocks = (record.get("message") or {}).get("content") or []
            return [
                Said(str(block.get("text", "")))
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
        if kind != "result":
            return []
        usage = record.get("usage") or {}
        events: list[Event] = [
            Used(
                input=int(usage.get("input_tokens") or 0),
                output=int(usage.get("output_tokens") or 0),
                cache_write=int(usage.get("cache_creation_input_tokens") or 0),
                cache_read=int(usage.get("cache_read_input_tokens") or 0),
            )
        ]
        if record.get("is_error"):
            said = record.get("result")
            detail = said if isinstance(said, str) and said.strip() else str(record.get("subtype"))
            events.append(
                Failed(
                    f"Claude Code reported an error: {detail}",
                    _status_kind(record.get("api_error_status")),
                )
            )
        elif isinstance(record.get("result"), str):
            events.append(Final(record["result"]))
        return events


if __name__ == "__main__":
    sys.exit(main(ClaudeCode()))
