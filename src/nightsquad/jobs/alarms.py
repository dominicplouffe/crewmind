"""The alarm sender: delivers queued alarms as push alerts (CHAT-20, BG-3).

Alarms are read in one transaction, sent with no transaction open, and marked sent in
another. A crash between sending and marking sends an alarm twice at worst, never zero
times. Each alarm is tried once per browser; a failure is logged, never retried for ever.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightsquad.catalog.execute import Clock
from nightsquad.domain.integrations import alerts, push
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.domain.settings.registry import Scope
from nightsquad.domain.settings.service import Subject
from nightsquad.gateway import outbound
from nightsquad.services import Services
from nightsquad.storage.models import Alarm, Membership, PushSubscription

logger = logging.getLogger(__name__)

TICK = timedelta(seconds=15)  # section 10: periodic jobs run every 15 s


@dataclass(frozen=True)
class _Delivery:
    alarm_id: int
    project_id: str
    title: str
    body: str
    subscriptions: list[tuple[str, dict[str, object]]]


class AlarmSender:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], clock: Clock, services: Services
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._services = services

    async def tick(self) -> int:
        """Send every queued alarm. Returns how many pushes were accepted."""
        async with self._sessions() as session, session.begin():
            alarms = list(
                await session.scalars(
                    select(Alarm).where(Alarm.sent_at.is_(None)).order_by(Alarm.id)
                )
            )
            if not alarms:
                return 0
            deliveries = [await self._delivery(session, alarm) for alarm in alarms]
            signing = await push.signing_value(
                session,
                SecretStore(self._services.master_key_file),
                self._clock(),
                create=False,
            )
        accepted = 0
        gone: list[str] = []
        for delivery in deliveries:
            payload = json.dumps(
                {
                    "title": delivery.title,
                    "body": delivery.body,
                    "project_id": delivery.project_id,
                }
            )
            for subscription_id, subscription in delivery.subscriptions:
                if signing is None:
                    break
                try:
                    if await outbound.web_push(
                        subscription, payload, signing, self._services.base_url
                    ):
                        accepted += 1
                    else:
                        gone.append(subscription_id)
                except Exception as error:
                    logger.warning(
                        "alarm %s was not delivered to one browser (%s)",
                        delivery.alarm_id,
                        type(error).__name__,
                    )
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(Alarm)
                .where(Alarm.id.in_([delivery.alarm_id for delivery in deliveries]))
                .values(sent_at=self._clock())
            )
            if gone:
                await session.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
        return accepted

    async def _delivery(self, session: AsyncSession, alarm: Alarm) -> _Delivery:
        found = await session.scalars(
            select(PushSubscription)
            .join(Membership, Membership.person_id == PushSubscription.person_id)
            .where(Membership.project_id == alarm.project_id, Membership.state == "member")
        )
        rows: list[PushSubscription] = []
        for row in found:
            if alarm.person_id is not None and row.person_id != alarm.person_id:
                continue
            level = await self._services.settings.get(
                session, Subject(Scope.PERSON, row.person_id), "alerts.level"
            )
            if alerts.wants(str(level), alarm.level):
                rows.append(row)
        return _Delivery(
            alarm.id,
            alarm.project_id,
            alarm.title,
            alarm.body,
            [
                (
                    row.id,
                    {"endpoint": row.endpoint, "keys": {"p256dh": row.p256dh, "auth": row.auth}},
                )
                for row in rows
            ],
        )

    async def run(self) -> None:
        """Tick for ever. A failed pass is logged and the next one still runs (NFR-9)."""
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("alarm sender: tick failed")
            await asyncio.sleep(TICK.total_seconds())
