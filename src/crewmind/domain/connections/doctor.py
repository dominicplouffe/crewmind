"""What `crewmind doctor` checks about connections (CON-16, NFR-5): MCP servers that need
sign-in or are failing, needs left open in started projects, and the egress proxy when a
secret is sent for an agent. Every finding comes with its fix."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from crewmind.domain.connections import needs
from crewmind.domain.connections.mcp import ServerState
from crewmind.domain.connections.model import ConnectionState, Delivery, Kind
from crewmind.domain.install import operations as install
from crewmind.domain.install.config import Config
from crewmind.domain.install.operations import Finding
from crewmind.domain.install.process import running_server
from crewmind.domain.projects.model import ProjectState
from crewmind.storage.models import (
    Connection,
    ConnectionSecret,
    McpServer,
    Project,
    ProjectConnection,
    ProjectNeed,
)

PROXY_FILE = "egress.json"
"""Where the server says whether its egress proxy started, and on which port."""
CONNECT_SECONDS = 2.0
LISTED = 5
"""How many names a finding lists before it says how many more."""


def record_proxy(data_dir: Path, port: int | None, error: str | None) -> None:
    """Written by the server when it starts the proxy, for the doctor to read."""
    with contextlib.suppress(OSError):
        (data_dir / PROXY_FILE).write_text(
            json.dumps({"port": port, "error": error}), encoding="utf-8"
        )


def _proxy_record(data_dir: Path) -> dict[str, Any] | None:
    try:
        found: dict[str, Any] = json.loads((data_dir / PROXY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found


def _names(names: list[str]) -> str:
    more = len(names) - LISTED
    return ", ".join(names[:LISTED]) + (f" and {more} more" if more > 0 else "")


async def _rows(config: Config, statement: Any) -> list[Any]:
    from crewmind.runtime import build_runtime

    runtime = build_runtime(config)
    try:
        async with runtime.sessions() as session:
            return list((await session.execute(statement)).all())
    finally:
        await runtime.close()


async def check_mcp(config: Config) -> Finding:
    """CON-10, CON-16: servers that need someone to sign in again, or that fail."""
    rows = await _rows(
        config,
        select(Connection.name, McpServer.state)
        .join(McpServer, McpServer.connection_id == Connection.id)
        .where(
            Connection.state == ConnectionState.ACTIVE,
            McpServer.state.in_([ServerState.NEEDS_SIGN_IN, ServerState.FAILING]),
        )
        .order_by(Connection.name),
    )
    signs = [name for name, state in rows if state == ServerState.NEEDS_SIGN_IN]
    failing = [name for name, state in rows if state == ServerState.FAILING]
    if not rows:
        return Finding(check="MCP servers", ok=True, detail="Every MCP server answers.")
    parts: list[str] = []
    if signs:
        parts.append(f"Waiting for sign-in: {_names(signs)}.")
    if failing:
        parts.append(f"Failing: {_names(failing)}.")
    return Finding(
        check="MCP servers",
        ok=False,
        detail=" ".join(parts),
        fix="Open Connections in Settings: sign in again, or test the server and fix what it "
        "says (`crewmind connections test-mcp`).",
    )


async def check_needs(config: Config) -> Finding:
    """CON-5: needs left open in projects that have started, which hold their seats."""
    rows = await _rows(
        config,
        select(Project.name, func.count(ProjectNeed.name))
        .join(ProjectNeed, ProjectNeed.project_id == Project.id)
        .where(
            ProjectNeed.state.in_(needs.UNMET),
            Project.state.notin_([ProjectState.DRAFT, ProjectState.STOPPED]),
        )
        .group_by(Project.name)
        .order_by(Project.name),
    )
    if not rows:
        return Finding(check="connection needs", ok=True, detail="No started project lacks one.")
    listed = [f"{name} ({count})" for name, count in rows]
    return Finding(
        check="connection needs",
        ok=False,
        detail=f"Started projects with agents waiting for a connection: {_names(listed)}.",
        fix="Open each project's Connections panel and add what is missing "
        "(`crewmind connections for-project`).",
    )


async def check_proxy(config: Config) -> Finding:
    """CON-6: when a secret is sent for an agent, the egress proxy runs and answers."""
    sent = await _rows(
        config,
        select(func.count(ProjectConnection.connection_id))
        .join(Connection, Connection.id == ProjectConnection.connection_id)
        .join(ConnectionSecret, ConnectionSecret.connection_id == Connection.id)
        .where(
            Connection.kind == Kind.SECRET,
            Connection.state == ConnectionState.ACTIVE,
            ConnectionSecret.delivery == Delivery.SENT_FOR_YOU,
        ),
    )
    if not sent or not sent[0][0]:
        return Finding(check="egress proxy", ok=True, detail="No secret is sent for agents yet.")
    if running_server(config.data_dir) is None:
        return Finding(
            check="egress proxy",
            ok=True,
            detail="It starts with the server, which is not running.",
        )
    record = _proxy_record(config.data_dir) or {}
    port = record.get("port")
    if not isinstance(port, int):
        reason = record.get("error") or "it did not start"
        return Finding(
            check="egress proxy",
            ok=False,
            detail=f"Secrets are sent for agents, and the egress proxy is not running: {reason}.",
            fix="Check the server log, free CREWMIND_EGRESS_PORT if it is taken, and restart "
            "the server with `crewmind up`.",
        )
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(config.host, port), CONNECT_SECONDS
        )
        writer.close()
    except (OSError, TimeoutError):
        return Finding(
            check="egress proxy",
            ok=False,
            detail=f"The egress proxy does not answer on port {port}.",
            fix="Restart the server with `crewmind up`.",
        )
    return Finding(check="egress proxy", ok=True, detail=f"It answers on port {port}.")


install.doctor_checks += [check_mcp, check_needs, check_proxy]
