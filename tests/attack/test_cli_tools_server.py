"""The agent API as MCP tools, as a command-line agent sees it (IF-6.1, LLM-8, P3).

The tools server runs inside the sandbox beside a vendor's command-line agent. It holds
only the run token: every tool is one agent API call, so the server's own rules decide."""

from __future__ import annotations

import httpx
import pytest
from mcp import Client
from mcp.types import TextContent

from crewmind.domain.execution import runs
from crewmind.runner.cli.tools_server import build
from tests.support import App, LiveRun, live_run, running_project


def run_client(app: App, run: LiveRun) -> httpx.AsyncClient:
    """What the sandbox holds: the agent API address and the run token, nothing else."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app.api),
        base_url=app.runtime.config.base_url,
        headers={"Authorization": f"Bearer {run.token}"},
    )


def text_of(result: object) -> str:
    content = getattr(result, "content", [])
    return " ".join(part.text for part in content if isinstance(part, TextContent))


@pytest.mark.attack("LLM-8")
async def test_LLM_8_a_command_line_agent_gets_the_agent_api_as_mcp_tools(app: App) -> None:
    """IF-6.1, LLM-8, P3: the tools listed are the run's own agent API tools, with their
    schemas; a call goes through the agent API with the run token and its answer comes back.
    A refusal, a bad argument and an unknown tool each come back as an error the model can
    read and act on, never an exception."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    run = await live_run(app, project)
    async with run_client(app, run) as http, Client(build(http)) as client:
        listed = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert {"agent_whoami", "agent_post_message", "agent_complete_task"} <= set(listed)
        assert listed["agent_post_message"].input_schema["required"] == ["body"]

        whoami = await client.call_tool("agent_whoami", {})
        assert not whoami.is_error, text_of(whoami)
        assert "CEO" in text_of(whoami)
        posted = await client.call_tool("agent_post_message", {"body": "Starting on the plan."})
        assert not posted.is_error, text_of(posted)

        refused = await client.call_tool(
            "agent_complete_task", {"task_id": 999, "evidence": "It is done."}
        )
        assert refused.is_error
        assert text_of(refused).startswith("Refused: There is no task 999")

        malformed = await client.call_tool("agent_complete_task", {"task_id": "first"})
        assert malformed.is_error
        assert "The input is not valid" in text_of(malformed)

        unknown = await client.call_tool("drop_database", {})
        assert unknown.is_error
        assert "There is no tool named drop_database" in text_of(unknown)


@pytest.mark.attack("LLM-8")
@pytest.mark.parametrize("listed_first", [True, False])
async def test_LLM_8_a_stopped_run_is_told_to_end(app: App, listed_first: bool) -> None:
    """LLM-8, INV-4: once the run ends its token stops working. Whether or not the agent
    listed its tools first, its next call tells it to make no more calls and end, rather
    than an error it might retry."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    run = await live_run(app, project)
    async with run_client(app, run) as http, Client(build(http)) as client:
        if listed_first:
            await client.list_tools()
        async with app.runtime.sessions() as session, session.begin():
            await runs.finish(session, run.run_id, run.runner_id, app.runtime.clock(), failed=False)
        stopped = await client.call_tool("agent_post_message", {"body": "One more thing."})
        if not listed_first:
            assert (await client.list_tools()).tools == []
    assert stopped.is_error
    assert "This run has been stopped" in text_of(stopped)
