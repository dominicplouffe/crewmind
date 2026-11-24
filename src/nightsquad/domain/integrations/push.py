"""Push alerts to a person's browser or installed phone app (CHAT-20).

The install signs its pushes with one key pair, kept in the secret store. An alarm is
written in the transaction that causes it and sent afterwards by the alarm sender, so a
slow push service never holds a database transaction open.
"""

from __future__ import annotations

import base64
from datetime import datetime
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import platform_job
from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.projects import lifecycle
from nightsquad.domain.projects.model import LIFTED_BY, PLATFORM_HOLDS, Hold
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.storage.events import append_event, event_type
from nightsquad.storage.models import Alarm, Project

CHAT_20 = rules.register(
    Rule("CHAT-20", "Push alerts go only to a browser's own push service, over https.")
)

SECRET_OWNER = ("install", "push")
SIGNING_SECRET = "signing key"

PUSH_SERVICES = (
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
    "notify.windows.com",
)
"""The push services of the browsers people use (CHAT-20). A subscription names the address
the server will post to, so any other host is refused."""

ALARM_RAISED = event_type("alarm.raised", "An alarm was queued for a project's people.")
ALARMS = platform_job("alarms")

_WHY: dict[Hold, str] = {
    Hold.BUDGET_WALL: "it reached its budget wall",
    Hold.AUTH_FAILURES: "a model credential keeps failing to sign in",
    Hold.SKIPPED_CYCLES: "its planning cycle was skipped too many times",
}


def is_push_service(endpoint: str) -> bool:
    """Whether an address is an https address at a known push service (CHAT-20)."""
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == service or host.endswith("." + service) for service in PUSH_SERVICES
    )


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_part(signing_value: str) -> str:
    """The public half of the signing pair, in the form a browser subscribes with."""
    padded = signing_value + "=" * (-len(signing_value) % 4)
    number = int.from_bytes(base64.urlsafe_b64decode(padded), "big")
    private = ec.derive_private_key(number, ec.SECP256R1())
    return _encode(private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


async def signing_value(
    session: AsyncSession, secrets: SecretStore, now: datetime, *, create: bool
) -> str | None:
    """The install's push signing value, made on first need and never shown (INV-6)."""
    held = await secrets.reveal(session, SECRET_OWNER, SIGNING_SECRET)
    if held is not None or not create:
        return held
    private = ec.generate_private_key(ec.SECP256R1())
    size = (private.curve.key_size + 7) // 8
    made = _encode(private.private_numbers().private_value.to_bytes(size, "big"))
    await secrets.put(session, SECRET_OWNER, SIGNING_SECRET, made, now)
    return made


async def raise_alarm(session: AsyncSession, project: Project, body: str, now: datetime) -> None:
    """Queue one alarm for the project's people. The sender delivers it."""
    alarm = Alarm(project_id=project.id, title=project.name, body=body, created_at=now)
    session.add(alarm)
    await session.flush()
    append_event(
        session,
        type=ALARM_RAISED,
        caller=ALARMS,
        at=now,
        subject=("alarm", str(alarm.id)),
        project_id=project.id,
        after={"body": body},
    )


async def _on_hold(session: AsyncSession, project: Project, now: datetime, hold: Hold) -> None:
    """GOV-3, LLM-7: a pause the platform makes is an alarm. A hold the chairman sets
    themselves is not."""
    if hold in PLATFORM_HOLDS:
        await raise_alarm(
            session,
            project,
            f"Paused: {_WHY[hold]}. To continue: {LIFTED_BY[hold]}.",
            now,
        )


lifecycle.hold_hooks.append(_on_hold)
