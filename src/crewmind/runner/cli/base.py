"""One run on a vendor's command-line agent, inside the sandbox (LLM-8, LLM-9, EXE-13).

Every such agent is driven the same way: get the context pack, give the agent the system
prompt, the pack, the agent API as MCP tools and its login, read what it prints line by
line, tell the server what it used, and post the reply of a chat run. A driver adds only
what differs between agents: the command, its files, and how to read its lines.

The agent calls its own provider with its own login, so the model gateway is not in the
path. That is the weaker boundary SECURITY.md states: usage is what the agent reports, and
the login is inside the sandbox. Everything the agent does to the project still goes
through the agent API, under the same rules as every other harness (P3).

This module imports nothing from the server.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from crewmind.runner.agent import CONTEXT_PATH, POST_PATH, TOOLS_PATH, fit_in_a_message

REPORT_PATH = "/gateway/v1/report"
DEFAULT_MODEL = "default"
"""A lineup entry that means: leave the model to the agent (LLM-4)."""
LINE_LIMIT_BYTES = 32 * 1024**2
"""The longest line an agent may print: one line can carry a whole file it read."""
ERROR_TAIL_CHARACTERS = 1500

AUTH_SIGNS = re.compile(
    r"\b401\b|\b403\b|unauthori[sz]ed|authenticat|not logged in|log ?in again|invalid.{0,20}"
    r"(token|api key|credential)|expired.{0,20}(token|login|session)|oauth",
    re.IGNORECASE,
)
TRANSIENT_SIGNS = re.compile(
    r"\b429\b|\b5\d\d\b|rate.?limit|usage limit|quota|overloaded|capacity|timed? ?out|"
    r"temporar|unavailable|connection|network",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Said:
    """Text the model wrote."""

    text: str


@dataclass(frozen=True)
class Used:
    """Tokens of one or more model calls, as the agent states them."""

    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0


@dataclass(frozen=True)
class Failed:
    """The agent says it failed. `kind` is auth or transient when the agent makes it clear."""

    detail: str
    kind: str | None = None


@dataclass(frozen=True)
class Final:
    """The agent's own statement of its final answer."""

    text: str


Event = Said | Used | Failed | Final


@dataclass(frozen=True)
class Setup:
    """Everything a driver is given to start its agent."""

    system_prompt: str
    prompt: str
    model: str
    effort: str
    grants: frozenset[str]
    tool_names: tuple[str, ...]
    workspace: Path
    home: Path
    login: str
    api: str
    token: str

    @property
    def names_a_model(self) -> bool:
        return bool(self.model) and self.model != DEFAULT_MODEL

    def tools_server(self) -> dict[str, Any]:
        """How to start the agent API tool server, in the words MCP settings use."""
        return {
            "command": sys.executable,
            "args": ["-I", "-m", "crewmind.runner.cli.tools_server"],
            "env": {
                "CREWMIND_RUN_TOKEN": self.token,
                "CREWMIND_AGENT_API": self.api,
                "PATH": os.environ.get("PATH", os.defpath),
            },
        }

    def write(self, name: str, text: str) -> Path:
        """A file in the run's private directory, readable by this user only."""
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)
        return path

    def environment(self, **extra: str) -> dict[str, str]:
        """The agent's environment, built from nothing. It never holds the run token: the
        agent reaches the project only through the tool server."""
        return {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "NO_COLOR": "1",
            **extra,
        }


@dataclass(frozen=True)
class Start:
    argv: list[str]
    env: dict[str, str]
    stdin: str = ""


class Driver:
    """What differs between command-line agents."""

    name = ""
    label = ""

    def prepare(self, setup: Setup) -> Start:
        raise NotImplementedError

    def parse(self, record: dict[str, Any]) -> list[Event]:
        raise NotImplementedError

    def renewed_login(self, setup: Setup) -> str | None:
        """The login as the agent left it, when it renewed it during the run."""
        return None


def kind_of_failure(detail: str) -> str | None:
    """Whether a failure reads as a refused login or as one that will pass (LLM-11)."""
    if AUTH_SIGNS.search(detail):
        return "auth"
    if TRANSIENT_SIGNS.search(detail):
        return "transient"
    return None


@dataclass
class _Outcome:
    texts: list[str] = field(default_factory=list[str])
    final: str | None = None
    failure: Failed | None = None
    stopped: str = ""

    @property
    def reply(self) -> str:
        return (self.final if self.final is not None else (self.texts or [""])[-1]).strip()


class _Run:
    def __init__(self, driver: Driver, client: httpx.AsyncClient, setup: Setup) -> None:
        self._driver = driver
        self._client = client
        self._setup = setup
        self._unreported = ""
        self.outcome = _Outcome()

    async def report(self, **body: Any) -> dict[str, Any]:
        response = await self._client.post(REPORT_PATH, json=body)
        if response.status_code != 200:
            return {"stop": response.status_code == 401, "reason": "the run was stopped"}
        return dict(response.json())

    async def _take(self, event: Event, process: asyncio.subprocess.Process) -> None:
        if isinstance(event, Said):
            if event.text.strip():
                self.outcome.texts.append(event.text)
                self._unreported += event.text
        elif isinstance(event, Final):
            self.outcome.final = event.text
        elif isinstance(event, Failed):
            self.outcome.failure = event
        else:
            usage = {
                "input": event.input,
                "output": event.output,
                "cache_write": event.cache_write,
                "cache_read": event.cache_read,
            }
            told = await self.report(usage=usage, text=self._unreported)
            self._unreported = ""
            if told.get("stop") and process.returncode is None:
                # GOV-6: the cap is a stop. The agent is ended here, not asked to end.
                self.outcome.stopped = str(told.get("reason", ""))
                process.terminate()

    async def drive(self, start: Start) -> None:
        process = await asyncio.create_subprocess_exec(
            *start.argv,
            cwd=self._setup.workspace,
            env=start.env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=LINE_LIMIT_BYTES,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        errors = asyncio.create_task(process.stderr.read())
        process.stdin.write(start.stdin.encode())
        with contextlib.suppress(ConnectionError):
            await process.stdin.drain()
        process.stdin.close()
        async for line in process.stdout:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                for event in self._driver.parse(record):  # pyright: ignore[reportUnknownArgumentType]
                    await self._take(event, process)
        code = await process.wait()
        said = (await errors).decode("utf-8", "replace")
        if self._unreported:
            await self.report(text=self._unreported)
        if self.outcome.failure is None and code != 0 and not self.outcome.stopped:
            tail = said[-ERROR_TAIL_CHARACTERS:].strip() or "it printed no reason"
            self.outcome.failure = Failed(f"{self._driver.label} ended with exit {code}: {tail}")


def _private_home() -> Path:
    """A directory of this run's own: in the sandbox's in-memory private directory when
    there is one (EXE-13), else in the system's temporary directory."""
    return Path(tempfile.mkdtemp(prefix="agent-", dir=os.environ.get("CREWMIND_PRIVATE_DIR")))


async def _post_reply(client: httpx.AsyncClient, text: str, most: int) -> None:
    """A chat run's answer goes to the chat as one message (CHAT-3). When the platform
    sends it back once for rewriting (MSG-12), it is posted again as it is: the second
    version is always posted, and this harness has no further model turn to rewrite in."""
    body = {"body": fit_in_a_message(text, most)}
    outcome = (await client.post(POST_PATH, json=body)).json()
    if outcome.get("posted") is False and outcome.get("held_until") is None:
        await client.post(POST_PATH, json=body)


async def run(driver: Driver) -> int:
    """Drive one run to its end. Returns the harness's exit code: 0 is a normal end."""
    api = os.environ["CREWMIND_AGENT_API"]
    token = os.environ["CREWMIND_RUN_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    home = _private_home()
    try:
        async with httpx.AsyncClient(base_url=api, headers=headers, timeout=None) as client:
            answer = await client.post(CONTEXT_PATH, json={})
            if answer.status_code in (401, 403):
                return 0
            pack = answer.json()
            listed = (await client.get(TOOLS_PATH)).json()
            setup = Setup(
                system_prompt=pack["system_prompt"],
                prompt=pack["context_pack"],
                model=os.environ.get("CREWMIND_MODEL", ""),
                effort=os.environ.get("CREWMIND_EFFORT", ""),
                grants=frozenset(pack["local_tools"]),
                tool_names=tuple(tool["name"] for tool in listed["tools"]),
                workspace=Path.cwd(),
                home=home,
                login=os.environ.get("CREWMIND_HARNESS_LOGIN", ""),
                api=api,
                token=token,
            )
            running = _Run(driver, client, setup)
            start = driver.prepare(setup)
            if shutil.which(start.argv[0], path=start.env.get("PATH")) is None:
                missing = (
                    f"{driver.label} is not installed where agents run: there is no "
                    f"`{start.argv[0]}` command."
                )
                await running.report(detail=missing)
                print(missing, file=sys.stderr)
                return 1
            await running.drive(start)
            outcome = running.outcome
            renewed = driver.renewed_login(setup)
            if renewed and renewed != setup.login:
                await running.report(login=renewed)
            if outcome.failure is not None:
                kind = outcome.failure.kind or kind_of_failure(outcome.failure.detail)
                await running.report(failure=kind, detail=outcome.failure.detail[:2000])
                print(outcome.failure.detail, file=sys.stderr)
                return 1
            if pack["run_kind"] == "chat" and outcome.reply:
                await _post_reply(client, outcome.reply, pack["message_max"])
            return 0
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main(driver: Driver) -> int:
    return asyncio.run(run(driver))
