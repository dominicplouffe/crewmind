"""Starting the egress proxy with the platform's hooks (CON-6, CON-16)."""

from __future__ import annotations

import logging
import ssl
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crewmind.domain.connections import sending
from crewmind.domain.connections.authority import Authority, LeafCache
from crewmind.domain.connections.sending import Injection, RunSending
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from crewmind.runner.egress.proxy import Connect, EgressProxy, ProxyHooks, guarded_connect

logger = logging.getLogger(__name__)


async def load_authority(
    sessions: async_sessionmaker[AsyncSession], key_file: Path, now: datetime
) -> Authority:
    async with sessions() as session, session.begin():
        return await sending.authority(session, SecretStore(key_file), now)


async def build_proxy(
    sessions: async_sessionmaker[AsyncSession],
    settings: SettingsService,
    key_file: Path,
    clock: Callable[[], datetime],
    *,
    upstream_tls: ssl.SSLContext | None = None,
    connect: Connect = guarded_connect,
) -> EgressProxy:
    """The proxy, with the install's authority loaded and its settings read once."""
    store = SecretStore(key_file)
    authority = await load_authority(sessions, key_file, clock())
    install = Subject(Scope.INSTALL, INSTALL_SUBJECT)
    async with sessions() as session:
        life = int(await settings.get(session, install, "proxy.certificate_life"))
        idle = int(await settings.get(session, install, "proxy.idle_timeout"))
    leaves = LeafCache(authority, timedelta(seconds=life))

    async def sending_for(token: str | None) -> RunSending | None:
        async with sessions() as session, session.begin():
            return await sending.sending_for_token(session, store, token)

    async def sent(run_id: str, injection: Injection, method: str, path: str, status: int) -> None:
        now = clock()
        async with sessions() as session, session.begin():
            sending.record_sent(session, run_id, injection, method, path, status, now)
            await sending.mark_used(session, injection.connection_id, now)

    async def refused(run_id: str, reason: str) -> None:
        async with sessions() as session, session.begin():
            sending.record_refused(session, run_id, reason, clock())

    return EgressProxy(
        ProxyHooks(
            sending=sending_for,
            sent=sent,
            leaf=leaves.context,
            upstream_tls=upstream_tls or ssl.create_default_context(),
            idle_seconds=float(idle),
            connect=connect,
            refused=refused,
        )
    )
