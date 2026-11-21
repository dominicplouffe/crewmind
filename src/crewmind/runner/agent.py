"""The vendor-neutral harness loop, run inside the sandbox (LLM-8).

It is transport only. It holds a run token and nothing else: it reaches models through
the gateway and acts through the agent API (P3). It imports nothing from the server.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

CONTEXT_PATH = "/agent/v1/agent/context"
TOOLS_PATH = "/agent/v1/tools"
GATEWAY_PATH = "/gateway/v1/complete"
POST_PATH = "/agent/v1/agent/post_message"
MAX_TURNS = 200
SHELL_TIMEOUT_SECONDS = 300
READ_LIMIT_BYTES = 64 * 1024  # ART-7: artifacts are read in 64 KB pages

LOCAL_TOOLS: dict[str, list[dict[str, Any]]] = {
    "files": [
        {
            "name": "read_file",
            "description": "Read a file in the workspace.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": "Write a file in the workspace.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
        {
            "name": "list_files",
            "description": "List the files in the workspace.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ],
    "shell": [
        {
            "name": "shell",
            "description": "Run a shell command in the workspace.",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        }
    ],
}


class Stop(Exception):
    """The run cannot continue: its token was revoked, or its cap was reached."""


def _inside(workspace: Path, relative: str) -> Path:
    target = (workspace / relative).resolve()
    if workspace.resolve() not in (target, *target.parents):
        raise ValueError(f"{relative} is outside the workspace")
    return target


def local_tool(workspace: Path, name: str, arguments: dict[str, Any]) -> str:
    """Run a tool the role grants inside the sandbox: files and shell."""
    try:
        if name == "read_file":
            return (
                _inside(workspace, arguments["path"])
                .read_bytes()[:READ_LIMIT_BYTES]
                .decode("utf-8", "replace")
            )
        if name == "write_file":
            target = _inside(workspace, arguments["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(arguments["content"], encoding="utf-8")
            return f"Wrote {arguments['path']}."
        if name == "list_files":
            files = sorted(
                str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.is_file()
            )
            return "\n".join(files) or "(the workspace is empty)"
        if name == "shell":
            done = subprocess.run(
                arguments["command"],
                shell=True,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=SHELL_TIMEOUT_SECONDS,
                check=False,
            )
            return f"exit {done.returncode}\n{done.stdout}{done.stderr}"[-READ_LIMIT_BYTES:]
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        return f"The tool failed: {error}"
    return f"There is no tool named {name}."


async def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(path, json=body)
    if response.status_code == 401:
        raise Stop("the run token no longer works")
    data: dict[str, Any] = response.json()
    if response.status_code == 403:
        return {"refused": data}
    response.raise_for_status()
    return data


async def agent_loop(client: httpx.AsyncClient, workspace: Path) -> str:
    """Drive one run to its end. Returns the model's final text."""
    pack = await _post(client, CONTEXT_PATH, {})
    if "refused" in pack:
        raise Stop(pack["refused"]["message"])
    listed = (await client.get(TOOLS_PATH)).json()
    paths: dict[str, str] = listed["paths"]
    local = [tool for grant in pack["local_tools"] for tool in LOCAL_TOOLS.get(grant, [])]
    local_names = {tool["name"] for tool in local}
    tools = [*listed["tools"], *local]
    messages: list[dict[str, Any]] = [{"role": "user", "content": pack["context_pack"]}]
    text = ""
    for _ in range(MAX_TURNS):
        answer = await _post(
            client,
            GATEWAY_PATH,
            {"system": pack["system_prompt"], "messages": messages, "tools": tools},
        )
        if "refused" in answer:
            raise Stop(answer["refused"]["message"])
        text = answer["text"]
        calls = answer["tool_calls"]
        messages.append({"role": "assistant", "content": text, "tool_calls": calls})
        if not calls:
            break
        for call in calls:
            if call["name"] in local_names:
                result = await asyncio.to_thread(
                    local_tool, workspace, call["name"], call["arguments"]
                )
            elif call["name"] in paths:
                result = json.dumps(await _post(client, paths[call["name"]], call["arguments"]))
            else:
                result = f"There is no tool named {call['name']}."
            messages.append({"role": "tool", "content": result, "tool_call_id": call["id"]})
        if answer.get("warning"):
            messages.append({"role": "user", "content": answer["warning"]})
    if pack["run_kind"] == "chat" and text.strip():
        most = pack["message_max"]
        outcome = await _post(client, POST_PATH, {"body": fit_in_a_message(text, most)})
        if outcome.get("posted") is False and outcome.get("held_until") is None:
            # MSG-12: the platform sent the reply back once. Ask the model to rewrite it,
            # then post what comes back; the second version is always posted.
            messages.append({"role": "user", "content": outcome["feedback"]})
            answer = await _post(
                client, GATEWAY_PATH, {"system": pack["system_prompt"], "messages": messages}
            )
            if "refused" not in answer and answer["text"].strip():
                text = answer["text"]
            await _post(client, POST_PATH, {"body": fit_in_a_message(text, most)})
    return text


CUT_NOTE = "\n\n(Cut here: the reply was too long for one message. Ask for the rest.)"


def fit_in_a_message(text: str, most: int) -> str:
    """MSG-1, CHAT-3: a reply longer than a message may be is cut and says so, so the
    person always gets an answer instead of a refused post."""
    return text if len(text) <= most else text[: most - len(CUT_NOTE)] + CUT_NOTE


WARM_FLAG = "--warm"
DONE = "done "
"""A warm process handles one chat run per line of standard input (the run's token) and
answers each with `done <exit code>` (MSG-11)."""


async def _one_run(api: str, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=api, headers=headers, timeout=None) as client:
        try:
            await agent_loop(client, Path.cwd())
        except Stop as stop:
            print(f"stopped: {stop}", file=sys.stderr)
            return 0
        except Exception as error:
            print(f"failed: {error}", file=sys.stderr)
            return 1
    return 0


async def _main() -> int:
    api = os.environ["CREWMIND_AGENT_API"]
    if WARM_FLAG not in sys.argv:
        return await _one_run(api, os.environ["CREWMIND_RUN_TOKEN"])
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line.strip():
            return 0
        print(f"{DONE}{await _one_run(api, line.strip())}", flush=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
