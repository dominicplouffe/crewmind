"""Operations for a person's push alerts (CHAT-20)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.domain.integrations import push
from crewmind.domain.secrets.store import SecretStore
from crewmind.services import services_of
from crewmind.storage.events import event_type
from crewmind.storage.models import PushSubscription

SUBSCRIBED = event_type("push.subscribed", "A person turned push alerts on in a browser.")
UNSUBSCRIBED = event_type("push.unsubscribed", "A person turned push alerts off in a browser.")


class PushIdentity(BaseModel):
    server_identity: str = Field(
        description="What a browser needs to subscribe to this install's alerts."
    )


class SubscribeInput(BaseModel):
    endpoint: str = Field(max_length=1000, description="The address the browser gave.")
    p256dh: str = Field(max_length=200, description="The browser's public value.")
    auth: str = Field(max_length=100, description="The browser's shared value.")


class UnsubscribeInput(BaseModel):
    endpoint: str = Field(max_length=1000, description="The address the browser gave.")


class Alerts(BaseModel):
    browsers: int = Field(description="How many of your browsers get alerts.")


async def _count(context: Context) -> Alerts:
    rows = await context.session.scalars(
        select(PushSubscription.id).where(PushSubscription.person_id == context.caller.actor_id)
    )
    return Alerts(browsers=len(list(rows)))


@operation(
    "push.public_key",
    summary="Show what a browser needs to subscribe to alerts.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def public_key(context: Context, payload: Empty) -> PushIdentity:
    """CHAT-20, INV-6: only the public half is ever shown."""
    services = services_of(context)
    value = await push.signing_value(
        context.session, SecretStore(services.master_key_file), context.now, create=True
    )
    assert value is not None
    return PushIdentity(server_identity=push.public_part(value))


@operation(
    "push.subscribe",
    summary="Turn on alerts in this browser.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def subscribe(context: Context, payload: SubscribeInput) -> Alerts:
    """CHAT-20, P4: the address must be a browser push service, so the server cannot be
    made to post anywhere else."""
    if not push.is_push_service(payload.endpoint):
        raise Refusal(
            "not_a_push_service",
            "That address is not a browser push service, so alerts cannot be sent to it.",
            rule=push.CHAT_20.id,
            hint="Turn alerts on from the crewmind app in your browser.",
        )
    await context.session.execute(
        delete(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    row = PushSubscription(
        person_id=context.caller.actor_id,
        endpoint=payload.endpoint,
        p256dh=payload.p256dh,
        auth=payload.auth,
        created_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    context.record(SUBSCRIBED, subject=("push_subscription", row.id))
    return await _count(context)


@operation(
    "push.unsubscribe",
    summary="Turn off alerts in this browser.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def unsubscribe(context: Context, payload: UnsubscribeInput) -> Alerts:
    """CHAT-20: a person removes only their own subscription."""
    row = await context.session.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.person_id == context.caller.actor_id,
        )
    )
    if row is not None:
        context.record(UNSUBSCRIBED, subject=("push_subscription", row.id))
        await context.session.delete(row)
    return await _count(context)
