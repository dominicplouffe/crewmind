"""Attacks on push alerts (CHAT-20, INV-6, P4)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select

from crewmind.domain.secrets.store import ensure_master_key
from crewmind.gateway import outbound
from crewmind.jobs.alarms import AlarmSender
from crewmind.storage.models import PushSubscription, StoredSecret
from tests.attack.harness import assert_refused
from tests.attack.test_budget import BIG
from tests.support import App, running_project, wake

BROWSER = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
    "p256dh": "BPublicValueFromTheBrowser",
    "auth": "sharedValue",
}


OVER_THE_WALL: list[dict[str, Any]] = [
    {"text": "working", "tools": [{"name": "agent_whoami"}], "usage": BIG},
    {"text": "more", "usage": BIG},
]


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


@pytest.mark.attack("CHAT-20")
@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://127.0.0.1:8420/v1/projects/list",
        "https://169.254.169.254/latest/meta-data",
        "https://fcm.googleapis.com.evil.example/push",
        "https://evilfcm.googleapis.com.example/",
        "https://internal.example/hook",
        "file:///etc/passwd",
    ],
)
async def test_CHAT_20_a_subscription_cannot_point_the_server_at_another_host(
    app: App, service: FakePushService, endpoint: str
) -> None:
    """CHAT-20, P4: the server posts alarms to the address in a subscription, so only an
    https address at a browser push service is accepted."""
    person = await app.person("owner@example.com")
    refused = await app.call("push.subscribe", person, **{**BROWSER, "endpoint": endpoint})
    assert_refused(refused, rule="CHAT-20", code="not_a_push_service")
    async with app.runtime.sessions() as session:
        assert list(await session.scalars(select(PushSubscription))) == []


@pytest.mark.attack("CHAT-20")
async def test_CHAT_20_alarm_reaches_only_the_projects_people_and_no_secret_leaves(
    app: App, service: FakePushService
) -> None:
    """CHAT-20, GOV-3, INV-6: a pause at the budget wall is pushed once to each browser of
    the project's people, to nobody else, and the signing value is stored sealed and never
    shown. A hold the chairman sets is not an alarm. One person cannot remove another's
    subscription."""
    owner = await app.person("owner@example.com")
    outsider = await app.person("outsider@example.com")
    identity = await app.ok("push.public_key", owner)
    assert identity == await app.ok("push.public_key", outsider)
    assert (await app.ok("push.subscribe", owner, **BROWSER))["browsers"] == 1
    other = {**BROWSER, "endpoint": "https://web.push.apple.com/other"}
    await app.ok("push.subscribe", outsider, **other)

    stolen = await app.ok("push.unsubscribe", outsider, endpoint=BROWSER["endpoint"])
    assert stolen["browsers"] == 1
    assert (await app.ok("push.subscribe", owner, **BROWSER))["browsers"] == 1

    project = await running_project(app, owner, **{"budget.tokens": 1_000_000})
    await app.ok("projects.hold", owner, project_id=project)
    assert await sender(app).tick() == 0
    await app.ok("projects.resume", owner, project_id=project)

    app.script("CEO", *OVER_THE_WALL)
    await wake(app, project)
    await app.work()
    assert (await app.ok("projects.status", owner, project_id=project))["state"] == "paused"

    assert await sender(app).tick() == 1
    assert await sender(app).tick() == 0
    (sent,) = service.sent
    assert sent["to"] == BROWSER["endpoint"]
    assert sent["title"] == "Atlas"
    assert "budget wall" in sent["body"]
    assert sent["project_id"] == project

    async with app.runtime.sessions() as session:
        stored = list(await session.scalars(select(StoredSecret)))
    assert sent["signing"].encode() not in b"".join(row.ciphertext for row in stored)
    assert sent["signing"] not in json.dumps(identity)
    events = json.dumps(await app.events(owner, project))
    assert sent["signing"] not in events
    assert "alarm.raised" in events


async def test_CHAT_20_a_subscription_the_push_service_dropped_is_removed(
    app: App, service: FakePushService
) -> None:
    """CHAT-20, BG-3: when the push service says a browser is gone, its subscription is
    deleted, and the alarm is still marked sent."""
    owner = await app.person("owner@example.com")
    await app.ok("push.public_key", owner)
    await app.ok("push.subscribe", owner, **BROWSER)
    project = await running_project(app, owner, **{"budget.tokens": 1_000_000})
    app.script("CEO", *OVER_THE_WALL)
    await wake(app, project)
    await app.work()
    service.gone = True
    assert await sender(app).tick() == 0
    async with app.runtime.sessions() as session:
        assert list(await session.scalars(select(PushSubscription))) == []
    assert await sender(app).tick() == 0
    assert len(service.sent) == 1
