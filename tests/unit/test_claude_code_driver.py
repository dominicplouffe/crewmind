"""The Claude Code driver: how it starts the agent and reads what it prints (LLM-2, LLM-8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from crewmind.runner.cli.base import Failed, Final, Said, Setup, Used
from crewmind.runner.cli.claude import ClaudeCode
from crewmind.runner.cli.tools_server import SERVER_NAME


def setup(tmp_path: Path, **changes: Any) -> Setup:
    values: dict[str, Any] = {
        "system_prompt": "You are the CEO.",
        "prompt": "Begin.",
        "model": "",
        "effort": "high",
        "grants": frozenset({"files"}),
        "tool_names": ("agent_whoami", "agent_post_message"),
        "workspace": tmp_path / "workspace",
        "home": tmp_path / "home",
        "login": "sk-ant-oat-login-0451",
        "api": "http://127.0.0.1:9",
        "token": "run-token-0451",
    }
    return Setup(**{**values, **changes})


USAGE = {
    "input_tokens": 10,
    "output_tokens": 20,
    "cache_creation_input_tokens": 3,
    "cache_read_input_tokens": 4,
}


@pytest.mark.parametrize(
    ("record", "events"),
    [
        (
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Hello."},
                {"type": "tool_use", "name": "Read"},
                {"type": "text", "text": "Done."},
            ]}},
            [Said("Hello."), Said("Done.")],
        ),
        ({"type": "assistant", "message": "not an object"}, []),
        ({"type": "assistant", "message": {"content": ["text", 3, None]}}, []),
        ({"type": "system", "subtype": "init"}, []),
        (
            {"type": "result", "usage": USAGE, "result": "All set."},
            [Used(input=10, output=20, cache_write=3, cache_read=4), Final("All set.")],
        ),
        ({"type": "result", "usage": "garbled"}, [Used()]),
        (
            {"type": "result", "usage": {}, "is_error": True, "result": "Invalid login",
             "api_error_status": 401},
            [Used(), Failed("Claude Code reported an error: Invalid login", "auth")],
        ),
        (
            {"type": "result", "is_error": True, "subtype": "error_max_turns",
             "api_error_status": 529},
            [Used(), Failed("Claude Code reported an error: error_max_turns", "transient")],
        ),
    ],
)  # fmt: skip
def test_LLM_8_claude_code_output_is_read_into_events(
    record: dict[str, Any], events: list[object]
) -> None:
    """LLM-8, LLM-9: what Claude Code prints becomes text, usage to report, a final answer
    or a failure with its kind. Anything malformed is skipped, never a crash."""
    assert ClaudeCode().parse(record) == events


def test_LLM_8_claude_code_gets_only_granted_tools_and_never_the_run_token(
    tmp_path: Path,
) -> None:
    """LLM-8, P3, INV-6: the agent's own tools are only those its grants allow, its agent API
    tools come through the tools server, its own settings are not loaded, and the run token
    reaches only the tools server, never the agent's environment."""
    start = ClaudeCode().prepare(setup(tmp_path))
    argv = start.argv
    assert argv[argv.index("--tools") + 1] == "Read,Write,Edit,Glob,Grep"
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert "Bash" not in allowed
    assert f"mcp__{SERVER_NAME}__agent_whoami" in allowed
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in argv
    assert "--model" not in argv
    assert start.env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat-login-0451"
    assert "run-token-0451" not in " ".join(start.env.values())
    config = (tmp_path / "home" / "mcp.json").read_text(encoding="utf-8")
    assert "run-token-0451" in config
    assert oct((tmp_path / "home" / "mcp.json").stat().st_mode & 0o777) == "0o600"


async def test_LLM_8_the_tools_server_starts_as_claude_code_starts_it(tmp_path: Path) -> None:
    """LLM-8: the tools server starts from the command the driver gives Claude Code, in a
    process of its own with only the variables it is given, and answers MCP's handshake."""
    command = setup(tmp_path).tools_server()
    parameters = StdioServerParameters(
        command=command["command"], args=command["args"], env=command["env"]
    )
    async with Client(stdio_client(parameters)) as client:
        info = client.server_info
        assert info is not None
        assert info.name == SERVER_NAME
