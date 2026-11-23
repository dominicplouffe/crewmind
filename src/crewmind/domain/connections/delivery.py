"""What a run is given, and masking it everywhere agent text comes back (CON-3, CON-7,
CON-8, CON-16, INV-6).

A run receives the variables and the secrets given to the agent that are attached to its
project and granted to its seat's role, and nothing else (CON-4). The values travel to the
harness over the run's own authenticated channel at the start of each run, and reach only
the commands the harness runs; they are never put in container settings.

For each run the platform holds the given secrets' values, and every place agent text
enters the platform replaces them, and their base64 and URL-encoded forms, with
`[secret: NAME]` (CON-8).
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, quote_plus

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.rules import Rule, rules
from crewmind.domain.connections import service
from crewmind.domain.connections.model import (
    ALL_ROLES,
    SECRET_NAME,
    SECRET_OWNER,
    ConnectionState,
    Delivery,
    Kind,
    Shape,
)
from crewmind.domain.conversation import sessions as chat_sessions
from crewmind.domain.secrets.store import SecretStore
from crewmind.storage.models import (
    ConnectionSecret,
    ConnectionVariable,
    Project,
    Role,
    Run,
    Seat,
)

CON_8 = rules.register(
    Rule("CON-8", "A value given to an agent is masked everywhere agent text enters crewmind.")
)


@dataclass(frozen=True)
class Given:
    """One thing a run receives: a variable, or a secret given as a variable or a file."""

    id: str
    name: str
    env: str
    description: str
    value: str
    secret: bool
    as_file: bool


async def given_for_run(session: AsyncSession, store: SecretStore | None, run: Run) -> list[Given]:
    """CON-4: what is attached to the run's project, active, and granted to its role.
    Without a store, secrets are listed without their values (for the context pack)."""
    seat = await session.get(Seat, run.seat_id)
    assert seat is not None
    role = await session.get(Role, seat.role_id)
    assert role is not None
    found: list[Given] = []
    for link, item in await service.attached(session, run.project_id):
        roles = [str(granted) for granted in link.roles or []]
        if item.state != ConnectionState.ACTIVE or not (ALL_ROLES in roles or role.slug in roles):
            continue
        env = service.env_of(link, item)
        if env is None:
            continue
        if item.kind == Kind.VARIABLE:
            variable = await session.get(ConnectionVariable, item.id)
            if variable is not None:
                found.append(
                    Given(item.id, item.name, env, item.description, variable.value, False, False)
                )
        elif item.kind == Kind.SECRET:
            secret = await session.get(ConnectionSecret, item.id)
            if secret is None or secret.delivery != Delivery.GIVEN:
                continue
            value = (
                await store.reveal(session, (SECRET_OWNER, item.id), SECRET_NAME)
                if store is not None
                else ""
            )
            if value is not None:
                as_file = secret.shape == Shape.FILE
                found.append(Given(item.id, item.name, env, item.description, value, True, as_file))
    return found


async def granted_state(session: AsyncSession, project: Project, seat: Seat) -> list[Any]:
    """CON-4: what the seat's role is granted, and when each last changed. A warm chat
    process restarts when this changes: detached, revoked, replaced or changed."""
    role = await session.get(Role, seat.role_id)
    slug = role.slug if role is not None else ""
    return sorted(
        [item.id, str(item.changed_at), str(item.value_set_at), service.env_of(link, item)]
        for link, item in await service.attached(session, project.id)
        if ALL_ROLES in (link.roles or []) or slug in (link.roles or [])
    )


def _forms(value: str) -> set[str]:
    """The value as it may come back: as written, base64 (standard and URL-safe, with and
    without padding) and URL-encoded."""
    raw = value.encode()
    encoded = {base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode()}
    forms = {value, quote(value, safe=""), quote_plus(value)}
    forms |= encoded | {form.rstrip("=") for form in encoded}
    return {form for form in forms if form}


@dataclass
class Masker:
    """Replaces every form of every given secret's value with `[secret: NAME]`."""

    forms: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])

    @classmethod
    def of(cls, given: Iterable[Given]) -> Masker:
        pairs = {(form, item.name) for item in given if item.secret for form in _forms(item.value)}
        # Longest first, so a value inside one of its own encodings is never half replaced.
        masker = cls(sorted(pairs, key=lambda pair: -len(pair[0])))
        known.remember(masker.forms)
        return masker

    def __bool__(self) -> bool:
        return bool(self.forms)

    def text(self, text: str) -> str:
        for form, name in self.forms:
            if form in text:
                text = text.replace(form, f"[secret: {name}]")
        return text

    def found(self, text: str) -> list[str]:
        """The names of the secrets whose values appear in the text."""
        return sorted({name for form, name in self.forms if form in text})

    def bytes(self, content: bytes) -> tuple[bytes, list[str]]:
        """A file's content masked, and the names found. A file that is not text is
        checked for the raw value only."""
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            found = sorted({name for form, name in self.forms if form.encode() in content})
            for form, name in self.forms:
                content = content.replace(form.encode(), f"[secret: {name}]".encode())
            return content, found
        found = self.found(text)
        return (self.text(text).encode("utf-8") if found else content), found

    def data(self, value: Any) -> Any:
        """The same JSON-like value with every string masked."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.data(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(value, dict):
            return {key: self.data(item) for key, item in value.items()}  # pyright: ignore[reportUnknownVariableType]
        return value

    def model[M: BaseModel](self, model: M) -> M:
        if not self:
            return model
        return type(model).model_validate(self.data(model.model_dump(mode="json")))


async def masker_for_run(session: AsyncSession, store: SecretStore, run_id: str) -> Masker:
    run = await session.get(Run, run_id)
    if run is None:
        return Masker()
    return Masker.of(await given_for_run(session, store, run))


class KnownValues:
    """Every value masked since the process started, for the log filter: a second safeguard
    behind the masking at each ingress (CON-16)."""

    def __init__(self) -> None:
        self._forms: dict[str, str] = {}

    def remember(self, forms: Iterable[tuple[str, str]]) -> None:
        for form, name in forms:
            self._forms[form] = name

    def __bool__(self) -> bool:
        return bool(self._forms)

    def mask(self, text: str) -> str:
        for form in sorted(self._forms, key=len, reverse=True):
            if form in text:
                text = text.replace(form, f"[secret: {self._forms[form]}]")
        return text


known = KnownValues()


def install_log_masking() -> None:
    """Mask any known secret value in every log record when it is made, whatever logger or
    handler writes it (CON-16). Installed once per process."""
    current = logging.getLogRecordFactory()
    if getattr(current, "masks_secrets", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current(*args, **kwargs)
        if known:
            message = record.getMessage()
            masked = known.mask(message)
            if masked != message:
                record.msg, record.args = masked, None
        return record

    factory.masks_secrets = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


chat_sessions.fingerprint_parts.append(granted_state)
