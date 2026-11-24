"""`squad chat` in the terminal (IF-4.8, CHAT-3, CHAT-4, CHAT-18)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Input, RichLog, Static

from nightsquad.surfaces.cli.chat.app import ChatApp, header_text, message_text
from nightsquad.surfaces.cli.chat.client import ChatClient, ChatError
from tests.support import App, api_client_factory, running_project


class Recording(ChatClient):
    """The real client against the test app, with a hand-fed stream."""

    def __init__(self, app: App, token: str) -> None:
        super().__init__(api_client_factory(app.api), token)
        self.live: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def stream(
        self, project_id: str, after_message: int
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        while True:
            yield await self.live.get()


def text_of(chat: ChatApp, selector: str) -> str:
    widget = chat.query_one(selector)
    if isinstance(widget, RichLog):
        return "\n".join(line.text for line in widget.lines)
    assert isinstance(widget, Static)
    return str(widget.render())


async def test_IF_4_8_the_terminal_chat_sends_streams_and_runs_commands(
    app: App, tmp_path: Path
) -> None:
    """IF-4.8, CHAT-3, CHAT-4, CHAT-18: the terminal chat shows the header, sends a
    message, shows a reply's words as they stream and the reply when stored, runs slash
    commands, attaches a file by path, and reports a refusal in the server's words."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    client = Recording(app, owner.token)
    chat = ChatApp(client, project, "Atlas")
    async with chat.run_test() as pilot:
        assert "running" in text_of(chat, "#header")
        assert "Budget: 0 of 20,000,000 tokens used" in text_of(chat, "#header")

        chat.query_one(Input).value = "Is the plan ready?"
        await pilot.press("enter")
        await pilot.pause()
        assert "owner: Is the plan ready?" in text_of(chat, "#log")
        for word in ("The ", "plan ", "is ready."):
            await client.live.put(("reply", {"seat": "CEO", "run_id": "r1", "text": word}))
        await pilot.pause(0.1)
        assert "CEO: The plan is ready." in text_of(chat, "#typing")

        app.script("CEO/chat", {"text": "The plan is ready."})
        await app.work()
        stored = (await app.ok("chat.history", owner, project_id=project))["items"][-1]
        await client.live.put(("message", stored))
        await pilot.pause(0.1)
        assert "CEO: The plan is ready." in text_of(chat, "#log")
        assert text_of(chat, "#typing") == ""

        chat.query_one(Input).value = "/hold"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert "/hold: the project is held." in text_of(chat, "#log")
        assert "held: chairman" in text_of(chat, "#header")

        note = tmp_path / "notes.txt"
        note.write_text("remember the llamas")
        chat.query_one(Input).value = f"/attach {note}"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert "Uploaded notes.txt (19 bytes)." in text_of(chat, "#log")

        chat.query_one(Input).value = "/quality superb"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert "could not be understood" in text_of(chat, "#log")

        await pilot.press("escape")
        await pilot.pause(0.1)
        assert "There is no run with that id." in text_of(chat, "#log")
    listed = await app.ok("artifacts.list", owner, project_id=project, kind="upload")
    assert [item["name"] for item in listed["items"]] == ["notes.txt"]


def test_CHAT_18_the_header_and_messages_are_plain_and_cannot_inject_markup() -> None:
    """CHAT-18, P4, P18, EXE-18: the header says Now (by the agent's name), Next, Waiting on
    you and the budget. Text an agent wrote is shown as text, never as terminal markup."""
    header = {
        "state": "paused",
        "now": [{"seat": "CEO", "name": "Maya", "run_kind": "chat", "doing": "thinking"}],
        "next": ["1 run(s) queued."],
        "waiting_on_you": 2,
        "budget": "5 of 10 tokens used (50%)",
        "holds": [{"reason": "budget_wall", "lifts": "a budget raise"}],
    }
    shown = header_text(header)
    assert "Now: Maya is thinking" in shown
    assert "Waiting on you: 2 | Budget: 5 of 10 tokens used (50%)" in shown
    assert "held: budget_wall (lifts by a budget raise)" in shown
    hostile = {
        "author": "CEO",
        "author_kind": "agent",
        "kind": "message",
        "body": "[b red]ALERT[/b red]",
    }
    assert "\\[b red]ALERT" in message_text(hostile)


async def test_IF_4_8_the_chat_client_reports_refusals_in_the_servers_words(app: App) -> None:
    """IF-1.4, IF-4.8: a refusal reaches the terminal with its sentence and its hint."""
    owner = await app.person("owner@example.com")
    client = ChatClient(api_client_factory(app.api), owner.token)
    with pytest.raises(ChatError, match=r"There is no project with that id\."):
        await client.send("0" * 32, "hello")
    assert await client.projects() == []
