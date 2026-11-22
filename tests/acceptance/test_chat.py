"""The phase 2 chat loop as real processes (EXE-12, MSG-11, CHAT-2, LLM-8, IF-6.1).

`crewmind up --slim` with sandboxes as separate processes and the mock provider: a person
sends a chat message with the real command, and the CEO's reply comes back from an agent
process that reached the server only through the agent API and the model gateway.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from tests.acceptance.test_slim import Install
from tests.support import PASSWORD

REPLY = "The plan has two steps: research, then a draft."
REPLY_LIMIT_SECONDS = 60


Items = list[dict[str, Any]]


def wait_for(read: Callable[[], Items], wanted: Callable[[Items], Any], what: str) -> Any:
    limit = time.monotonic() + REPLY_LIMIT_SECONDS
    while time.monotonic() < limit:
        found = wanted(read())
        if found:
            return found
        time.sleep(0.5)
    raise AssertionError(f"no {what} within {REPLY_LIMIT_SECONDS} seconds")


def warm_processes(server_pid: int) -> list[str]:
    """The warm agent processes the server has started."""
    found = subprocess.run(
        ["pgrep", "-P", str(server_pid), "-f", "crewmind.runner.agent --warm"],
        capture_output=True,
        text=True,
        check=False,
    )
    return found.stdout.split()


def first_reply(items: Items) -> dict[str, Any] | None:
    return next((item for item in items if item["author_kind"] == "agent"), None)


def all_finished(items: Items) -> Items | None:
    return items if items and items[0]["state"] == "finished" else None


def test_EXE_12_a_chat_message_is_answered_by_an_agent_in_its_own_process(
    tmp_path: Path,
) -> None:
    """EXE-12, MSG-11, CHAT-2, LLM-8, INV-6: the reply is threaded to the question, the run
    finished, its tokens are in the ledger, the web app's start page is served, and no
    install secret is in the agent's working directory."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "CEO.chat.json").write_text(json.dumps([{"text": REPLY}]))
    install = Install(tmp_path / "data")
    install.env["CREWMIND_SANDBOX_MODE"] = "unisolated"
    install.env["CREWMIND_MOCK_SCRIPT_DIR"] = str(scripts)
    try:
        setup = install.run("setup", "--slim", "--admin-email", "dom@example.com")
        install.start("--slim")
        password = f"{PASSWORD}\n"
        install.run("accept", "--link", setup["setup_link"], "--password-stdin", stdin=password)
        install.run("login", "--email", "dom@example.com", "--password-stdin", stdin=password)
        project = install.run(
            "projects", "create", "--name", "Atlas", "--type", "deliver", "--goal", "Ship it."
        )["project_id"]
        install.run("projects", "start", "--project-id", project)
        asked = install.run("chat", "send", "--project-id", project, "--body", "What is the plan?")

        def history() -> Items:
            return install.run("chat", "history", "--project-id", project)["items"]

        def runs_now() -> Items:
            return install.run("runs", "list", "--project-id", project)["items"]

        reply = wait_for(history, first_reply, "reply from the CEO")
        assert reply["body"] == REPLY
        assert reply["reply_to"] == asked["id"]
        runs = wait_for(runs_now, all_finished, "finished run")
        # Starting the project ran the CEO's first planning run too (SPD-3).
        assert "chat" in [run["kind"] for run in runs]
        assert install.run("budget", "show", "--project-id", project)["spent"] > 0

        # MSG-11: the next reply comes from the same warm agent process.
        assert install.server is not None
        first_warm = warm_processes(install.server.pid)
        assert len(first_warm) == 1
        install.run("chat", "send", "--project-id", project, "--body", "And after that?")
        wait_for(
            history,
            lambda items: [m for m in items if m["author_kind"] == "agent"][1:],
            "second reply",
        )
        assert warm_processes(install.server.pid) == first_warm

        page = httpx.get(f"{install.url}/accept/anything")
        assert "content-security-policy" in page.headers

        key = (install.data_dir / "master.key").read_text().strip()
        for file in (install.data_dir / "workspaces").rglob("*"):
            if file.is_file():
                assert key not in file.read_text(errors="ignore")
    finally:
        install.stop()
