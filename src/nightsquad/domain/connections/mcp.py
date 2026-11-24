"""MCP servers: their states, their tools' permissions, their health, and how Nightsquad
signs in to them (CON-9 to CON-12, INT-4, LLM-11, 7.18)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.state_machine import NEW, StateMachine
from nightsquad.domain.connections.mcp_client import Probe
from nightsquad.domain.connections.model import SECRET_NAME, SECRET_OWNER
from nightsquad.domain.models.service import (
    BREAKER_FAILURES,
    BREAKER_FIRST_COOLOFF,
    BREAKER_MAX_COOLOFF,
)
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import Connection, McpServer, McpTool

INT_4 = rules.register(
    Rule("INT-4", "An MCP tool call is allowed only for tools the chairman allowed.")
)

SERVER_CHANGED = event_type("mcp.state_changed", "An MCP server changed state (7.18).")
TESTED = event_type("mcp.tested", "An MCP server was tested and its tools read (CON-12).")
TOOL_CHANGED = event_type("mcp.tool_permission_changed", "An MCP tool was allowed or denied.")
TOOLS_CHANGED = event_type("mcp.tools_changed", "An MCP server's tools appeared or went.")

OAUTH_ACCESS, OAUTH_REFRESH, OAUTH_CLIENT_SECRET = "oauth_access", "oauth_refresh", "oauth_client"
OAUTH_SECRETS = (OAUTH_ACCESS, OAUTH_REFRESH, OAUTH_CLIENT_SECRET)


class AuthKind(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    HEADER = "header"
    OAUTH = "oauth"


class ServerState(StrEnum):
    ACTIVE = "active"
    NEEDS_SIGN_IN = "needs sign-in"
    FAILING = "failing"
    DELETED = "deleted"


class Permission(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class Classification(StrEnum):
    READ = "read"
    WRITE = "write"


M = ServerState
SERVER_MACHINE = StateMachine(
    "MCP server",
    "7.18-mcp-server",
    [
        (NEW, M.ACTIVE),
        (NEW, M.NEEDS_SIGN_IN),
        (M.ACTIVE, M.NEEDS_SIGN_IN),
        (M.NEEDS_SIGN_IN, M.ACTIVE),
        (M.ACTIVE, M.FAILING),
        (M.FAILING, M.ACTIVE),
        (M.ACTIVE, M.DELETED),
        (M.NEEDS_SIGN_IN, M.DELETED),
        (M.FAILING, M.DELETED),
    ],
)
P = Permission
TOOL_MACHINE = StateMachine(
    "MCP tool permission",
    "7.18-mcp-tool",
    [(NEW, P.ALLOWED), (NEW, P.DENIED), (P.DENIED, P.ALLOWED), (P.ALLOWED, P.DENIED)],
)


def move(
    session: AsyncSession, server: McpServer, item: Connection, target: ServerState, now: datetime,
    caller: Caller, why: str | None = None,
) -> None:  # fmt: skip
    if server.state == target:
        return
    SERVER_MACHINE.check(server.state, target)
    append_event(
        session,
        type=SERVER_CHANGED,
        caller=caller,
        at=now,
        subject=("connection", item.id),
        project_id=item.owner_id if item.scope == "project" else None,
        before={"state": server.state},
        after={"state": target, "name": item.name, "why": why},
    )
    server.state = target


async def headers_for(
    session: AsyncSession, store: SecretStore, server: McpServer
) -> dict[str, str]:
    """CON-9: how Nightsquad signs in to the server, for its own calls only. The values never
    enter a sandbox."""
    owner = (SECRET_OWNER, server.connection_id)
    if server.auth_kind == AuthKind.BEARER:
        value = await store.reveal(session, owner, SECRET_NAME)
        return {"Authorization": f"Bearer {value}"} if value else {}
    if server.auth_kind == AuthKind.HEADER and server.header_name:
        value = await store.reveal(session, owner, SECRET_NAME)
        return {server.header_name: value} if value else {}
    if server.auth_kind == AuthKind.OAUTH:
        value = await store.reveal(session, owner, OAUTH_ACCESS)
        return {"Authorization": f"Bearer {value}"} if value else {}
    return {}


def breaker_allows(server: McpServer, now: datetime) -> bool:
    return server.breaker_until is None or server.breaker_until <= now


def worked(
    session: AsyncSession, server: McpServer, item: Connection, now: datetime, caller: Caller
) -> None:
    """LLM-11: a call that works closes the breaker."""
    server.failures, server.breaker_until, server.cool_off_seconds = 0, None, 0
    server.last_error = None
    if server.state == ServerState.FAILING:
        move(session, server, item, ServerState.ACTIVE, now, caller, "it answered again")


def failed(
    session: AsyncSession, server: McpServer, item: Connection, reason: str, now: datetime,
    caller: Caller,
) -> None:  # fmt: skip
    """LLM-11: after three failures in a row the server is failing and calls wait out a
    cool-off that doubles, up to an hour."""
    server.failures += 1
    server.last_error = reason[:500]
    if server.failures < BREAKER_FAILURES:
        return
    first = int(BREAKER_FIRST_COOLOFF.total_seconds())
    doubled = server.cool_off_seconds * 2 if server.cool_off_seconds else first
    server.cool_off_seconds = int(min(doubled, int(BREAKER_MAX_COOLOFF.total_seconds())))
    server.breaker_until = now + timedelta(seconds=server.cool_off_seconds)
    if server.state == ServerState.ACTIVE:
        move(session, server, item, ServerState.FAILING, now, caller, reason)


async def sync_tools(
    session: AsyncSession, server: McpServer, item: Connection, probe: Probe, now: datetime,
    caller: Caller,
) -> list[McpTool]:  # fmt: skip
    """CON-12, INT-4: a new tool starts allowed only when it says it only reads; any other
    starts denied. A tool that disappears is kept, marked gone. The chairman is told what
    changed through the record."""
    stored = {
        tool.name: tool
        for tool in await session.scalars(
            select(McpTool).where(McpTool.server_id == server.connection_id)
        )
    }
    appeared: list[str] = []
    for info in probe.tools:
        tool = stored.pop(info.name, None)
        classification = Classification.READ if info.reads_only else Classification.WRITE
        if tool is None:
            permission = Permission.ALLOWED if info.reads_only else Permission.DENIED
            TOOL_MACHINE.check(NEW, permission)
            tool = McpTool(
                server_id=server.connection_id, name=info.name, permission=permission,
                first_seen=now, classification=classification, description="", input_schema={},
                last_seen=now,
            )  # fmt: skip
            session.add(tool)
            appeared.append(info.name)
        elif tool.classification == Classification.READ and classification == Classification.WRITE:
            # A tool that now says it may change things loses the allow it had as a reader.
            tool.permission = Permission.DENIED
        tool.title, tool.description, tool.input_schema = (
            info.title,
            info.description,
            info.input_schema,
        )
        tool.classification, tool.last_seen, tool.gone = classification, now, False
    gone = [tool.name for tool in stored.values() if not tool.gone]
    for tool in stored.values():
        tool.gone = True
    server.server_name, server.server_version = probe.name, probe.version
    server.transport, server.tools_refreshed_at = probe.transport, now
    if appeared or gone:
        append_event(
            session,
            type=TOOLS_CHANGED,
            caller=caller,
            at=now,
            subject=("connection", item.id),
            after={"name": item.name, "appeared": appeared, "gone": gone},
        )
    await session.flush()
    return list(
        await session.scalars(
            select(McpTool).where(McpTool.server_id == server.connection_id).order_by(McpTool.name)
        )
    )
