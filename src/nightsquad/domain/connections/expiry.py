"""Secrets that expire (CON-2, 7.18): the chairman of every project using one is told
`secret.expiry_warning` before and on the day; the day after, it expires, its needs are
open again and the seats that depend on it are held (CON-14)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import platform_job
from nightsquad.domain.connections import service
from nightsquad.domain.connections.model import (
    CONNECTION_MACHINE,
    EXPIRY_WARNED,
    STATE_CHANGED,
    ConnectionState,
)
from nightsquad.domain.integrations import alerts
from nightsquad.domain.settings.registry import Scope as SettingScope
from nightsquad.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from nightsquad.storage.events import append_event
from nightsquad.storage.models import Connection

EXPIRY = platform_job("connections: expiry")
EARLY, ON_THE_DAY = "early", "day"


def _warn(session: AsyncSession, item: Connection, which: str, now: datetime) -> list[str]:
    append_event(
        session,
        type=EXPIRY_WARNED,
        caller=EXPIRY,
        at=now,
        subject=("connection", item.id),
        after={"name": item.name, "warning": which, "expires_on": str(item.expires_on)},
    )
    return [*(item.warned or []), which]


async def check(session: AsyncSession, settings: SettingsService, now: datetime) -> None:
    lead = timedelta(
        seconds=int(
            await settings.get(
                session, Subject(SettingScope.INSTALL, INSTALL_SUBJECT), "secret.expiry_warning"
            )
        )
    )
    today = now.date()
    rows = await session.scalars(
        select(Connection).where(
            Connection.state == ConnectionState.ACTIVE, Connection.expires_on.is_not(None)
        )
    )
    for item in rows:
        day = item.expires_on
        assert day is not None
        users = await service.attachments(session, item.id)
        if day < today:
            CONNECTION_MACHINE.check(item.state, ConnectionState.EXPIRED)
            append_event(
                session,
                type=STATE_CHANGED,
                caller=EXPIRY,
                at=now,
                subject=("connection", item.id),
                before={"state": item.state},
                after={"state": ConnectionState.EXPIRED, "name": item.name},
            )
            item.state, item.changed_at = ConnectionState.EXPIRED, now
            for _, project in users:
                alerts.queue(
                    session, project,
                    f"{service.label(item).capitalize()} has expired. Replace its value or "
                    "move its expiry date; the agents that use it wait until then.",
                    now, level=alerts.ALARM,
                )  # fmt: skip
                await service.refresh(session, project, now, EXPIRY)
            continue
        warned = list(item.warned or [])
        if day == today and ON_THE_DAY not in warned:
            text = f"{service.label(item).capitalize()} expires at the end of today."
            item.warned = _warn(session, item, ON_THE_DAY, now)
        elif day - lead <= today and EARLY not in warned and ON_THE_DAY not in warned:
            text = f"{service.label(item).capitalize()} expires on {day.isoformat()}."
            item.warned = _warn(session, item, EARLY, now)
        else:
            continue
        for _, project in users:
            alerts.queue(
                session, project, f"{text} Replace its value or move the date.", now,
                level=alerts.ALARM,
            )  # fmt: skip
