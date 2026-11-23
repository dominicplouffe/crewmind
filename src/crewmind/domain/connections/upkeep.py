"""Keeping MCP servers' tools current (CON-12, CON-16): every `mcp.tools_refresh`, each
working server is tested again and its tools read. The server is reached outside any
database transaction; what it said is written in a short one afterwards."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.catalog.caller import platform_job
from crewmind.domain.connections import mcp
from crewmind.domain.connections.mcp_client import Unreachable, probe
from crewmind.domain.connections.mcp_sign_in import fresh_headers
from crewmind.domain.connections.model import ConnectionState
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from crewmind.storage.models import Connection, McpServer

logger = logging.getLogger(__name__)

UPKEEP = platform_job("connections: MCP upkeep")
EVERY = {"hourly": timedelta(hours=1), "daily": timedelta(days=1), "weekly": timedelta(days=7)}
"""CON-12: what each choice of `mcp.tools_refresh` means."""


async def refresh_due(
    sessions: async_sessionmaker[AsyncSession],
    settings: SettingsService,
    key_file: Path,
    clock: Callable[[], datetime],
) -> int:
    """Test every working remote server not refreshed within `mcp.tools_refresh`. Returns
    how many were tested."""
    if not await asyncio.to_thread(key_file.exists):
        return 0
    store = SecretStore(key_file)
    now = clock()
    install = Subject(Scope.INSTALL, INSTALL_SUBJECT)
    async with sessions() as session:
        every = EVERY[str(await settings.get(session, install, "mcp.tools_refresh"))]
        most = int(await settings.get(session, install, "mcp.description_max"))
        seconds = float(str(settings.registry.settings["mcp.call_timeout"].default))
        due = list(
            await session.scalars(
                select(McpServer)
                .join(Connection, Connection.id == McpServer.connection_id)
                .where(
                    McpServer.kind == "remote",
                    McpServer.state.in_([mcp.ServerState.ACTIVE, mcp.ServerState.FAILING]),
                    Connection.state == ConnectionState.ACTIVE,
                    or_(
                        McpServer.tools_refreshed_at.is_(None),
                        McpServer.tools_refreshed_at <= now - every,
                    ),
                )
            )
        )
        targets = [server.connection_id for server in due if mcp.breaker_allows(server, now)]
    for server_id in targets:
        # Tokens are refreshed in their own short transaction; the server is reached after.
        async with sessions() as session, session.begin():
            server = await session.get(McpServer, server_id)
            item = await session.get(Connection, server_id)
            if server is None or item is None:
                continue
            try:
                headers = await fresh_headers(
                    session, store, server, item, clock(), UPKEEP, seconds=seconds
                )
            except Unreachable:
                continue
            url, private, transport = server.url or "", server.private_allowed, server.transport
        try:
            found = await probe(
                url, headers, private_allowed=private, seconds=seconds, description_max=most,
                transport=transport,
            )  # fmt: skip
            failure = None
        except Unreachable as error:
            found, failure = None, str(error)
        async with sessions() as session, session.begin():
            server = await session.get(McpServer, server_id)
            item = await session.get(Connection, server_id)
            if server is None or item is None:
                continue
            if found is None:
                mcp.failed(session, server, item, failure or "", clock(), UPKEEP)
                logger.info("mcp upkeep: %s did not work: %s", item.name, failure)
            else:
                mcp.worked(session, server, item, clock(), UPKEEP)
                await mcp.sync_tools(session, server, item, found, clock(), UPKEEP)
    return len(targets)
