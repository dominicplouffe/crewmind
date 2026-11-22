"""`crewmind chat`: the project chat in the terminal (IF-4.8, CHAT-3, CHAT-4, CHAT-18).

A client of the same operations as the app: streaming replies, slash commands, `@`
mentions, file attachment by path, Esc to interrupt, and the Now / Next / Waiting header.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any, ClassVar

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import Input, RichLog, Static

from crewmind.surfaces.cli.chat.client import ChatClient, ChatError

HEADER_REFRESH_SECONDS = 5
ATTACH = "/attach"


def header_text(header: dict[str, Any]) -> str:
    """CHAT-18: Now, Next, Waiting on you, and the budget against the wall."""
    now = ", ".join(f"{w['seat']} is {w['doing']}" for w in header["now"]) or "nobody is working"
    upcoming = " ".join(header["next"]) or "nothing scheduled"
    holds = "".join(f" | held: {h['reason']} (lifts by {h['lifts']})" for h in header["holds"])
    return (
        f"[b]{header['state']}[/b]{escape(holds)}\n"
        f"Now: {escape(now)}\nNext: {escape(upcoming)}\n"
        f"Waiting on you: {header['waiting_on_you']} | Budget: {escape(header['budget'])}"
    )


def message_text(message: dict[str, Any]) -> str:
    author = escape(message["author"])
    body = escape(message["body"])
    if message["kind"] == "status":
        return f"[dim]· {body}[/dim]"
    colour = "cyan" if message["author_kind"] == "person" else "green"
    return f"[b {colour}]{author}[/b {colour}]: {body}"


class ChatApp(App[None]):
    """One project's chat. Type a message and press Enter. `/help` lists the commands."""

    CSS = """
    #header { height: 4; padding: 0 1; background: $surface; }
    #log { height: 1fr; padding: 0 1; }
    #typing { height: 1; padding: 0 1; color: $text-muted; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "interrupt", "Interrupt the reply"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, client: ChatClient, project_id: str, project_name: str) -> None:
        super().__init__()
        self._client = client
        self._project_id = project_id
        self.title = f"crewmind: {project_name}"
        self._seen: set[int] = set()
        self._replying: dict[str, str] = {}
        self._tasks: list[asyncio.Task[None]] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="header")
        yield RichLog(id="log", wrap=True, markup=True)
        yield Static("", id="typing")
        yield Input(placeholder="Message the CEO, @name an agent, or type /help", id="input")

    async def on_mount(self) -> None:
        last = 0
        for message in await self._client.history(self._project_id):
            self._show(message)
            last = message["id"]
        await self._refresh_header()
        self._tasks = [
            asyncio.create_task(self._follow(last)),
            asyncio.create_task(self._tick_header()),
        ]
        self.query_one(Input).focus()

    async def on_unmount(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    def _note(self, text: str) -> None:
        self.query_one("#log", RichLog).write(f"[yellow]{escape(text)}[/yellow]")

    def _show(self, message: dict[str, Any]) -> None:
        if message["id"] in self._seen:
            return
        self._seen.add(message["id"])
        self.query_one("#log", RichLog).write(message_text(message))

    def _show_typing(self) -> None:
        lines = [f"{seat}: {text}" for seat, text in self._replying.items()]
        self.query_one("#typing", Static).update(escape(" | ".join(lines))[-200:])

    async def _refresh_header(self) -> None:
        with contextlib.suppress(ChatError, OSError):
            header = await self._client.header(self._project_id)
            self.query_one("#header", Static).update(header_text(header))
            self._live_runs = header.get("now", [])

    async def _tick_header(self) -> None:
        while True:
            await asyncio.sleep(HEADER_REFRESH_SECONDS)
            await self._refresh_header()

    async def _follow(self, after_message: int) -> None:
        """Show messages as they arrive, and the words of a reply as they are produced."""
        async for kind, data in self._client.stream(self._project_id, after_message):
            if kind == "reply":
                self._replying[data["seat"]] = self._replying.get(data["seat"], "") + data["text"]
                self._reply_run = data["run_id"]
                self._show_typing()
            elif kind == "message":
                self._replying.pop(data["author"], None)
                self._show_typing()
                self._show(data)
            elif kind == "change":
                await self._refresh_header()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        try:
            if text.startswith(ATTACH):
                path = Path(text[len(ATTACH) :].strip())
                done = await self._client.attach(self._project_id, path)
                self._note(f"Uploaded {done['name']} ({done['size']:,} bytes).")
            elif text.startswith("/"):
                done = await self._client.command(self._project_id, text)
                self._note(self._summary(done))
            else:
                self._show(await self._client.send(self._project_id, text))
        except (ChatError, OSError) as error:
            self._note(str(error))
        await self._refresh_header()

    def _summary(self, done: dict[str, Any]) -> str:
        result = done["result"]
        if "commands" in result:
            lines = [f"{name}: {what}" for name, what in result["commands"].items()]
            return "\n".join([*lines, f"{ATTACH} <path>: upload a file from this computer."])
        if "state" in result:
            return f"{done['command']}: the project is {result['state']}."
        if "summary" in result:
            return f"{done['command']}: {result['summary']}."
        return f"{done['command']} done."

    async def action_interrupt(self) -> None:
        """CHAT-4: Esc interrupts the reply in progress."""
        run_id = getattr(self, "_reply_run", None)
        if run_id is None:
            self._note("No reply is in progress.")
            return
        try:
            await self._client.interrupt(self._project_id, run_id)
            self._replying.clear()
            self._show_typing()
            self._note("Reply interrupted.")
        except ChatError as error:
            self._note(str(error))
