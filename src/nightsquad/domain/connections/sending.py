"""Secrets sent for the agent (CON-6, CON-16): what a run sends to which site, the record
of each time it was sent, and the install's certificate authority for the egress proxy.

The proxy asks this module, per connection, which header a run's request to a site gets.
The answer comes only from what is attached to the run's project and granted to its role.
"""

from __future__ import annotations

import base64
import contextlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.rules import Rule, rules
from nightsquad.domain.connections import service
from nightsquad.domain.connections.authority import Authority
from nightsquad.domain.connections.model import (
    ALL_ROLES,
    SECRET_NAME,
    SECRET_OWNER,
    ConnectionState,
    Delivery,
    HeaderKind,
    Kind,
)
from nightsquad.domain.execution import runs
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.storage.models import Connection, ConnectionSecret, Role, Run, RunStep, Seat

CON_6 = rules.register(
    Rule("CON-6", "A secret sent for the agent goes only to its own sites, for granted runs.")
)

SENT_STEP = "secret sent"
AUTHORITY_OWNER = ("egress", "install")
AUTHORITY_KEY, AUTHORITY_CERTIFICATE = "authority_key", "authority_certificate"


@dataclass(frozen=True)
class Injection:
    """The header one site gets from one secret, for one run."""

    connection_id: str
    name: str
    site: str
    header: str
    value: str

    def __repr__(self) -> str:  # never shows the value, in a log or a traceback
        return f"Injection({self.name} for {self.site}, header {self.header})"


@dataclass(frozen=True)
class RunSending:
    run_id: str
    by_site: dict[str, Injection]


def header_of(secret: ConnectionSecret, value: str) -> tuple[str, str]:
    """CON-6: bearer, basic with a user name, or a named header."""
    if secret.header_kind == HeaderKind.BASIC:
        pair = f"{secret.basic_user or ''}:{value}".encode()
        return "Authorization", "Basic " + base64.b64encode(pair).decode()
    if secret.header_kind == HeaderKind.HEADER and secret.header_name:
        return secret.header_name, value
    return "Authorization", f"Bearer {value}"


async def sending_for(session: AsyncSession, store: SecretStore, run: Run) -> dict[str, Injection]:
    """CON-4, CON-6: every site the run sends a secret to, with its header."""
    seat = await session.get(Seat, run.seat_id)
    role = await session.get(Role, seat.role_id) if seat is not None else None
    if role is None:
        return {}
    found: dict[str, Injection] = {}
    for link, item in await service.attached(session, run.project_id):
        roles = [str(granted) for granted in link.roles or []]
        if item.kind != Kind.SECRET or item.state != ConnectionState.ACTIVE:
            continue
        if not (ALL_ROLES in roles or role.slug in roles):
            continue
        secret = await session.get(ConnectionSecret, item.id)
        if secret is None or secret.delivery != Delivery.SENT_FOR_YOU:
            continue
        value = await store.reveal(session, (SECRET_OWNER, item.id), SECRET_NAME)
        if value is None:
            continue
        header, shown = header_of(secret, value)
        for site in secret.sites or []:
            found[str(site)] = Injection(item.id, item.name, str(site), header, shown)
    return found


async def sent_values(session: AsyncSession, store: SecretStore, run: Run) -> list[tuple[str, str]]:
    """CON-8: each value sent for the run, raw and as the header it travels in, by name, so
    that a site echoing it back cannot carry it to the model."""
    found: list[tuple[str, str]] = []
    for injection in (await sending_for(session, store, run)).values():
        found.append((injection.name, injection.value))
        scheme, _, credential = injection.value.partition(" ")
        if credential and scheme in ("Basic", "Bearer"):
            found.append((injection.name, credential))
            if scheme == "Basic":
                with contextlib.suppress(ValueError):
                    pair = base64.b64decode(credential).decode()
                    found += [(injection.name, pair), (injection.name, pair.partition(":")[2])]
    return [(name, value) for name, value in found if value]


async def sites_for(session: AsyncSession, run: Run) -> list[tuple[Connection, list[str]]]:
    """CON-14: each secret sent for this run and the sites it goes to, by name only, for
    its context pack. No value is read."""
    seat = await session.get(Seat, run.seat_id)
    role = await session.get(Role, seat.role_id) if seat is not None else None
    if role is None:
        return []
    found: list[tuple[Connection, list[str]]] = []
    for link, item in await service.attached(session, run.project_id):
        roles = [str(granted) for granted in link.roles or []]
        if item.kind != Kind.SECRET or item.state != ConnectionState.ACTIVE:
            continue
        if not (ALL_ROLES in roles or role.slug in roles):
            continue
        secret = await session.get(ConnectionSecret, item.id)
        if secret is not None and secret.delivery == Delivery.SENT_FOR_YOU:
            found.append((item, [str(site) for site in secret.sites or []]))
    return found


async def sending_for_token(
    session: AsyncSession, store: SecretStore, token: str | None
) -> RunSending | None:
    """The run a proxy credential belongs to, and what it sends; None for a credential that
    is not a live run's (the proxy then refuses it)."""
    run = await runs.run_for_token(session, token)
    if run is None:
        return None
    return RunSending(run.id, await sending_for(session, store, run))


async def has_sending(session: AsyncSession, run: Run) -> bool:
    """Whether the run sends any secret, without reading a value: only such a run is sent
    through the proxy."""
    seat = await session.get(Seat, run.seat_id)
    role = await session.get(Role, seat.role_id) if seat is not None else None
    if role is None:
        return False
    for link, item in await service.attached(session, run.project_id):
        roles = [str(granted) for granted in link.roles or []]
        if item.kind != Kind.SECRET or item.state != ConnectionState.ACTIVE:
            continue
        if not (ALL_ROLES in roles or role.slug in roles):
            continue
        secret = await session.get(ConnectionSecret, item.id)
        if secret is not None and secret.delivery == Delivery.SENT_FOR_YOU:
            return True
    return False


def record_sent(
    session: AsyncSession,
    run_id: str,
    injection: Injection,
    method: str,
    path: str,
    status: int,
    now: datetime,
) -> None:
    """CON-16: each time a secret is sent, the run's trace names the site, the secret, the
    method, the path without its query, and the answer's status. Never the value."""
    session.add(
        RunStep(
            run_id=run_id,
            kind=SENT_STEP,
            data={
                "site": injection.site,
                "secret": injection.name,
                "header": injection.header,
                "method": method,
                "path": path.split("?", 1)[0],
                "status": status,
            },
            at=now,
        )
    )


REFUSED_STEP = "egress refused"


def record_refused(session: AsyncSession, run_id: str, reason: str, now: datetime) -> None:
    """EXE-14: a connection the proxy refused is in the run's trace, with the reason the
    agent was given."""
    session.add(RunStep(run_id=run_id, kind=REFUSED_STEP, data={"reason": reason}, at=now))


async def mark_used(session: AsyncSession, connection_id: str, now: datetime) -> None:
    await session.execute(
        update(Connection).where(Connection.id == connection_id).values(last_used_at=now)
    )


async def authority(session: AsyncSession, store: SecretStore, now: datetime) -> Authority:
    """The install's certificate authority, created on first use. Its key is stored like
    any secret (CON-6)."""
    key = await store.reveal(session, AUTHORITY_OWNER, AUTHORITY_KEY)
    certificate = await store.reveal(session, AUTHORITY_OWNER, AUTHORITY_CERTIFICATE)
    if key is not None and certificate is not None:
        return Authority(key.encode(), certificate.encode())
    made = Authority.create("nightsquad egress proxy")
    await store.put(session, AUTHORITY_OWNER, AUTHORITY_KEY, made.key_pem.decode(), now)
    await store.put(
        session, AUTHORITY_OWNER, AUTHORITY_CERTIFICATE, made.certificate_pem.decode(), now
    )
    return made
