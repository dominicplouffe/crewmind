"""Slim mode end to end, as a real process (NFR-23, NFR-2, NFR-5, IF-4.1, IF-4.5).

Starts `crewmind up --slim` and drives the phase 1 exit demo with the real `crewmind`
command and a real MCP client over HTTP.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import sqlalchemy
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from crewmind.storage.engine import sync_url
from tests.support import PASSWORD

START_LIMIT_SECONDS = 5  # NFR-23
IDLE_MEMORY_LIMIT_MB = 400  # NFR-23


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Install:
    def __init__(self, data_dir: Path) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {
            **os.environ,
            "CREWMIND_DATA_DIR": str(data_dir),
            "CREWMIND_PORT": str(self.port),
            "CREWMIND_API": self.url,
            # The same on a machine with Docker and on one without: a test of container
            # mode names it.
            "CREWMIND_SANDBOX_MODE": "unisolated",
            # A real server process cannot be told that this host has no container
            # runtime, so it is told what an operator would tell it (WRK-7).
            "CREWMIND_ALLOW_AGENT_CHECKS_UNISOLATED": "on",
        }
        self.env.pop("CREWMIND_DATABASE_URL", None)
        self.env.pop("CREWMIND_TOKEN", None)
        self.data_dir = data_dir
        self.server: subprocess.Popen[str] | None = None
        self.output = ""

    def run(self, *arguments: str, stdin: str | None = None, check: bool = True) -> Any:
        """Run the real command with --json and return its parsed output."""
        result = subprocess.run(
            [sys.executable, "-m", "crewmind", *arguments, "--json"],
            env=self.env,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
        if check:
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)
        return result

    def start(self, *flags: str) -> float:
        """Start the server and return the seconds until it was ready."""
        started = time.monotonic()
        self.server = subprocess.Popen(
            [sys.executable, "-m", "crewmind", "up", *flags],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        while time.monotonic() - started < 30:
            try:
                if httpx.get(f"{self.url}/readyz").status_code == 200:
                    return time.monotonic() - started
            except httpx.TransportError:
                pass
            assert self.server.poll() is None, self.server.stdout and self.server.stdout.read()
            time.sleep(0.05)
        raise AssertionError("the server did not become ready")

    def stop(self) -> None:
        if self.server is not None:
            self.server.terminate()
            self.output, _ = self.server.communicate(timeout=10)
            self.server = None

    def memory_mb(self) -> float:
        assert self.server is not None
        status = Path(f"/proc/{self.server.pid}/status").read_text()
        resident = next(line for line in status.splitlines() if line.startswith("VmRSS"))
        kilobytes = int(resident.split()[1])
        return kilobytes / 1024


@pytest.fixture
def install(tmp_path: Path) -> Iterator[Install]:
    built = Install(tmp_path / "data")
    yield built
    built.stop()


RUN_MOVED = "run.state_changed"


def demo(install: Install) -> tuple[str, list[dict[str, Any]], str]:
    """The exit demo through the real CLI. Returns the project, its events and an MCP token."""
    setup = install.run("setup", "--slim", "--admin-email", "dom@example.com")
    install.start("--slim")
    password = f"{PASSWORD}\n"
    install.run("accept", "--link", setup["setup_link"], "--password-stdin", stdin=password)
    signed_in = install.run(
        "login", "--email", "dom@example.com", "--password-stdin", stdin=password
    )
    assert signed_in["role"] == "admin"
    project = install.run(
        "projects", "create", "--name", "Atlas", "--type", "deliver", "--goal", "Ship the atlas."
    )["project_id"]
    install.run(
        "settings", "change-project", "--project-id", project,
        "--changes", "run.concurrency=6", "--reason", "More parallel work.",
    )  # fmt: skip
    # No model key is added, so the crew cannot work: start says so and names who waits
    # (PRJ-1, LLM-6, CON-5). The demo starts without it; the record is what it shows.
    refused = install.run("projects", "start", "--project-id", project, check=False)
    assert json.loads(refused.stderr)["code"] == "start_blocked"
    started = install.run("projects", "start", "--project-id", project, "--without-missing")
    assert started["state"] == "running"
    assert install.run("projects", "hold", "--project-id", project)["state"] == "held"
    assert install.run("projects", "resume", "--project-id", project)["state"] == "running"
    events = install.run("record", "list", "--project-id", project, "--limit", "200")["items"]
    token = install.run("mcp-clients", "mint", "--client-name", "Desk assistant")["token"]
    return project, events, token


async def events_over_mcp(install: Install, token: str, project: str) -> list[dict[str, Any]]:
    http = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})
    transport = streamable_http_client(f"{install.url}/mcp", http_client=http)  # pyright: ignore[reportArgumentType]
    async with Client(transport) as client:
        # The whole list: by default an MCP tool answers with a summary (IF-5.7).
        asked = {"project_id": project, "limit": 200, "detail": "full"}
        result = await client.call_tool("record_list", asked)
    assert result.structured_content is not None
    return result.structured_content["items"]


def test_NFR_23_slim_mode_runs_the_exit_demo_in_one_process(install: Install) -> None:
    """NFR-23, NFR-2, IF-4.1, IF-4.5, IF-5.1: one process on SQLite serves the whole demo
    through the real CLI, the API and an MCP client. PRJ-1, CON-5: start without a
    model key names who waits, and starts without it only when asked. Secrets go in by
    standard input, the stored token file is private, and the server refuses a second copy
    on the same data."""
    project, events, token = demo(install)

    def of_the_project(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The chairman's own steps. The CEO's first planning run adds events of its own
        while this test reads (SPD-3)."""
        return [event for event in items if event["type"].startswith("project.")]

    events = of_the_project(events)
    assert [event["type"] for event in events][-5:] == [
        "project.state_changed",
        "project.hold_added",
        "project.state_changed",
        "project.hold_lifted",
        "project.state_changed",
    ]
    stored_token = json.loads((install.data_dir / "cli.json").read_text())["token"]
    api = httpx.get(
        f"{install.url}/v1/record/list",
        params={"project_id": project, "limit": 200},
        headers={"Authorization": f"Bearer {stored_token}"},
    )
    assert of_the_project(api.json()["items"]) == events
    assert of_the_project(asyncio.run(events_over_mcp(install, token, project))) == events

    assert ((install.data_dir / "cli.json").stat().st_mode & 0o077) == 0
    assert ((install.data_dir / "master.key").stat().st_mode & 0o077) == 0
    assert (install.data_dir / "crewmind.sqlite").exists()
    assert httpx.get(f"{install.url}/healthz").json() == {"status": "ok"}
    second = install.run("up", "--slim", check=False)
    assert second.returncode == 3
    assert "already running" in second.stderr
    assert install.run("doctor")["healthy"] is True

    install.run("logout")
    refused = install.run("whoami", check=False)
    assert refused.returncode == 4
    assert json.loads(refused.stderr)["code"] == "unauthenticated"
    unreachable = Install(install.data_dir)
    assert unreachable.run("whoami", check=False).returncode == 6


def test_NFR_23_slim_mode_starts_fast_and_stays_small(install: Install) -> None:
    """NFR-23: start in under 5 seconds; idle memory under 400 MB."""
    install.run("setup", "--slim")
    seconds = install.start("--slim")
    time.sleep(1)
    memory = install.memory_mb()
    assert seconds < START_LIMIT_SECONDS, f"took {seconds:.1f} s to start"
    assert memory < IDLE_MEMORY_LIMIT_MB, f"idle at {memory:.0f} MB"


def test_NFR_23_a_slim_install_moves_to_postgres_with_nothing_lost(
    install: Install, request: pytest.FixtureRequest, database_url: str
) -> None:
    """NFR-23: `crewmind migrate --to postgres` copies every row. The same project, with
    its settings and its whole event log, continues on a Postgres server."""
    if request.config.getoption("--db") != "postgres":
        pytest.skip("needs a Postgres database: run with --db=postgres")
    project, events, _ = demo(install)
    running = install.run(
        "migrate", "--to", "postgres", "--url-stdin", stdin=database_url, check=False
    )
    assert running.returncode == 3
    assert "Stop it before you migrate" in running.stderr
    install.stop()

    moved = install.run("migrate", "--to", "postgres", "--url-stdin", stdin=database_url)
    assert moved["rows_copied"]["events"] >= len(events)
    assert moved["rows_copied"]["projects"] == 1
    again = install.run(
        "migrate", "--to", "postgres", "--url-stdin", stdin=database_url, check=False
    )
    assert "already has rows" in again.stderr

    install.env["CREWMIND_DATABASE_URL"] = database_url
    install.start()
    assert (
        install.run("record", "list", "--project-id", project, "--limit", "200")["items"] == events
    )
    assert install.run("projects", "hold", "--project-id", project)["state"] == "held"
    after = install.run("record", "list", "--project-id", project, "--limit", "200")["items"]
    # The run the start queued may also move on the new server; the hold adds exactly two.
    added = [event["type"] for event in after[len(events) :] if event["type"] != RUN_MOVED]
    assert added == ["project.hold_added", "project.state_changed"]
    assert after[-1]["id"] > events[-1]["id"]
    engine = sqlalchemy.create_engine(sync_url(database_url))
    with engine.connect() as connection:
        assert connection.execute(sqlalchemy.text("SELECT count(*) FROM persons")).scalar_one() == 1
    engine.dispose()
