"""A stand-in for the browsers' push services, and the alarm sender, for tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nightsquad.domain.secrets.store import ensure_master_key
from nightsquad.gateway import outbound
from nightsquad.jobs.alarms import AlarmSender
from tests.support import App

BROWSER = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
    "p256dh": "BPublicValueFromTheBrowser",
    "auth": "sharedValue",
}


class FakePushService:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.sent: list[dict[str, Any]] = []
        self.gone = False
        monkeypatch.setattr(outbound, "web_push", self.push)

    async def push(
        self, subscription: dict[str, Any], payload: str, signing_value: str, sender: str
    ) -> bool:
        self.sent.append(
            {"to": subscription["endpoint"], "signing": signing_value, **json.loads(payload)}
        )
        return not self.gone


@pytest.fixture
def service(app: App, monkeypatch: pytest.MonkeyPatch) -> FakePushService:
    ensure_master_key(app.runtime.config.master_key_file)
    return FakePushService(monkeypatch)


def sender(app: App) -> AlarmSender:
    return AlarmSender(app.runtime.sessions, app.runtime.clock, app.runtime.services)
