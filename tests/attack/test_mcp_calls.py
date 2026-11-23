"""Attacks on MCP tools in runs: offered by grant and permission, denied calls never leave
crewmind, access asked for and decided by the person, changes done once, limits and
records (CON-13, CON-14, INT-4, WRK-16, IF-5.6)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import func, select

from crewmind.domain.secrets.store import ensure_master_key
from crewmind.gateway.protocol import CompletionRequest
from crewmind.storage.models import LedgerLine, RunRefusal, RunStep, SideEffect
from tests.attack import mcp_support
from tests.attack.harness import assert_refused
from tests.attack.mcp_support import URL, serving
from tests.attack.test_mcp import client_for, mcp_caller
from tests.support import Actor, App, agent_call, live_run, running_project, wake


@pytest.fixture(autouse=True)
def master_key(app: App) -> None:
    ensure_master_key(app.runtime.config.master_key_file)
    mcp_support.created.clear()


async def blog_server(app: App, owner: Actor, project: str, roles: list[str] | None = None) -> str:
    added = await app.ok(
        "connections.add_mcp_server", owner, name="blog", description="The blog's tools.",
        url=URL, project_id=project, roles=roles or ["*"],
    )  # fmt: skip
    return str(added["id"])


async def mcp_call(app: App, token: str, server: str, tool: str, **arguments: Any) -> Any:
    async with app.client() as client:
        return await client.post(
            f"/agent/v1/mcp/{server}/{tool}",
            json=arguments,
            headers={"Authorization": f"Bearer {token}"},
        )


async def steps(app: App, kind: str = "mcp call") -> list[dict[str, Any]]:
    async with app.runtime.sessions() as session:
        return [
            row.data for row in await session.scalars(select(RunStep).where(RunStep.kind == kind))
        ]


@pytest.mark.attack("CON-13")
async def test_CON_13_an_agent_uses_an_allowed_tool_and_its_answer_comes_back_as_data(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CON-13, CON-16: the run is offered only the allowed tools of the servers granted to
    it; the call goes through crewmind; the answer reaches the model; the trace names the
    server, tool, arguments, outcome, time and size; the ledger counts it."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    sent: list[CompletionRequest] = []
    complete = app.runtime.mock.complete

    async def recording(request: CompletionRequest, **kwargs: Any) -> Any:
        sent.append(request)
        return await complete(request, **kwargs)

    monkeypatch.setattr(app.runtime.mock, "complete", recording)
    async with serving():
        await blog_server(app, owner, project)
        app.script(
            "CEO", {"tools": [{"name": "mcp_blog_list_posts", "arguments": {}}]}, {"text": "done"}
        )
        await wake(app, project)
        await app.work()
    offered = {tool.name for tool in sent[0].tools}
    assert "mcp_blog_list_posts" in offered
    assert "mcp_blog_create_post" not in offered
    assert "agent_call_mcp_tool" not in offered
    said = json.dumps([request.model_dump(mode="json") for request in sent[1:]])
    assert "post one" in said
    [step] = await steps(app)
    assert (step["server"], step["tool"], step["outcome"]) == ("blog", "list_posts", "ok")
    assert step["bytes"] > 0
    async with app.runtime.sessions() as session:
        counted = await session.scalar(
            select(func.count()).select_from(LedgerLine).where(LedgerLine.kind == "mcp call")
        )
    assert counted == 1


@pytest.mark.attack("INT-4")
@pytest.mark.attack("CON-14")
async def test_INT_4_a_denied_tool_never_reaches_the_server_until_the_person_allows_it(
    app: App,
) -> None:
    """INT-4, CON-14, HUM-2, WRK-16, IF-5.6: a denied call is refused here, counted as a
    refusal and never sent; the agent asks for access; a model client cannot approve it;
    the chairman can; the change is then made once, and asking again does not redo it."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    async with serving() as gate:
        server = await blog_server(app, owner, project)
        run = await live_run(app, project)
        before = len(gate.seen)
        denied = await mcp_call(app, run.token, server, "create_post", title="Hello")
        assert_refused(denied, rule="INT-4", code="mcp_tool_denied")
        assert "agent_request_access" in denied.json()["hint"]
        assert len(gate.seen) == before
        async with app.runtime.sessions() as session:
            refusals = await session.scalar(select(func.count()).select_from(RunRefusal))
        assert refusals == 1

        asked = await agent_call(
            app, run.token, "agent.request_access", server="blog", tool="create_post",
            why="To publish the first post the plan asks for.",
        )  # fmt: skip
        assert asked.status_code == 200, asked.text
        item = asked.json()["item_id"]
        minted = await app.ok("mcp_clients.mint", owner, client_name="Helper", scopes=["steer"])
        async with client_for(app, await mcp_caller(app, minted["token"])) as client:
            tried = await client.call_tool(
                "items_decide", {"project_id": project, "item_id": item, "action": "approve"}
            )
        assert tried.is_error
        await app.ok("items.decide", owner, project_id=project, item_id=item, action="approve")

        first = await mcp_call(app, run.token, server, "create_post", title="Hello")
        assert first.status_code == 200, first.text
        assert first.json()["content"] == "created Hello"
        again = await mcp_call(app, run.token, server, "create_post", title="Hello")
        assert again.json()["done_before"] is True
    assert mcp_support.created == ["Hello"]
    async with app.runtime.sessions() as session:
        effects = list(await session.scalars(select(SideEffect)))
    assert [(effect.state, effect.fired) for effect in effects] == [("finished", True)]


@pytest.mark.attack("CON-13")
async def test_CON_13_limits_grants_and_size_hold(app: App) -> None:
    """CON-13, CON-4: a server not granted to the run's role is refused; an answer over the
    size limit is cut and says so; a run past its call limit is refused."""
    owner = await app.person("owner@example.com")
    project = await running_project(
        app, owner, **{"mcp.max_calls_per_run": 2, "mcp.result_max_bytes": 4096}
    )
    async with serving():
        server = await blog_server(app, owner, project)
        run = await live_run(app, project)
        big = (await mcp_call(app, run.token, server, "export_posts")).json()
        assert big["cut"] is True
        assert "[cut here" in big["content"]
        assert len(big["content"].encode()) < 4300
        await mcp_call(app, run.token, server, "list_posts")
        over = await mcp_call(app, run.token, server, "list_posts")
        assert_refused(over, rule="CON-13", code="mcp_run_limit")
        await app.ok("connections.detach", owner, project_id=project, connection="blog")
        gone = await mcp_call(app, run.token, server, "list_posts")
        assert_refused(gone, rule="INT-4", code="mcp_server_not_granted")
