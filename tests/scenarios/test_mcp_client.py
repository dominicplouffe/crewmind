"""An MCP client steers a project end to end (phase 6 exit demo; IF-5.2, IF-5.3, IF-5.4)."""

from __future__ import annotations

from typing import Any

from tests.attack.test_mcp import client_for, mcp_caller
from tests.attack.test_planning import CHAIRMAN_HOLDS, plan, propose
from tests.attack.work_support import Squad
from tests.support import App


async def test_IF_5_2_a_client_with_steer_and_create_runs_a_project(app: App) -> None:
    """IF-5.2, IF-5.3, IF-5.4, HUM-1: through MCP alone, a client with the steer and create
    scopes creates a project, starts it, asks the CEO a question and gets the answer,
    decides a waiting item, and stops a project only on the second call. Each write is
    recorded as the person acting through the client."""
    squad = await Squad.start(app, settings=CHAIRMAN_HOLDS)
    wanted = await propose(squad)
    owner = squad.owner
    minted = await app.ok(
        "mcp_clients.mint", owner, client_name="Desk client", scopes=["steer", "create"]
    )
    async with client_for(app, await mcp_caller(app, minted["token"])) as client:

        async def call(tool: str, **arguments: Any) -> dict[str, Any]:
            result = await client.call_tool(tool, arguments)
            assert result.structured_content is not None, tool
            assert "code" not in result.structured_content, result.structured_content
            return result.structured_content

        waiting = (await call("items_list", project_id=squad.project))["items"]
        item = next(entry for entry in waiting if entry["kind"] == "proposed scope")
        decided = await call(
            "items_decide", project_id=squad.project, item_id=item["id"], action="accept"
        )
        assert (decided["state"], decided["outcome"]) == ("decided", "accept")
        assert (await plan(squad))[wanted]["state"] == "accepted"

        created = await call(
            "projects_create", name="Second site", type="deliver", goal="Publish a second site."
        )
        project = created["project_id"]
        app.script("CEO/work", {"text": "Planning."})
        app.script("CEO/chat", {"text": "The plan is one page."})
        assert (await call("projects_start", project_id=project))["state"] == "running"
        asked = await call("chat_send", project_id=project, body="What is the plan?")
        await app.work()
        history = (await call("chat_history", project_id=project))["items"]
        answer = next(line for line in history if line["reply_to"] == asked["id"])
        assert "The plan is one page." in str(answer["body"])

        preview = await call("projects_stop", project_id=project)
        assert preview["confirm_required"] is True
        assert (await call("projects_status", project_id=project))["state"] == "running"
        stopped = await call("projects_stop", project_id=project, confirm=preview["confirm"])
        assert stopped["state"] == "stopped"

    owner = await app.login(owner.email)
    events = await app.events(owner, project)
    by_client = {event["type"] for event in events if event["via"] == "mcp:Desk client"}
    assert {"project.created", "project.state_changed", "message.posted"} <= by_client
    decision = [
        event
        for event in await app.events(owner, squad.project)
        if event["type"] == "item.state_changed" and event["after"]["state"] == "decided"
    ]
    assert [(e["actor"], e["via"]) for e in decision] == [(owner.person_id, "mcp:Desk client")]
