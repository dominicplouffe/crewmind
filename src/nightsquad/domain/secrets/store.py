"""Secrets encrypted at rest under the install master key (ACC-6, NFR-12, INV-6).

Values are sealed with AES-256-GCM. Each value is bound to its owner and name as associated
data, so a sealed value moved onto another row no longer opens. Each row records which key
sealed it, so a rotation can be checked and an interrupted one finished.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules
from nightsquad.storage.models import StoredSecret

ACC_6 = rules.register(Rule("ACC-6", "Secrets are stored and read only under the master key."))

_KEY_BYTES = 32
_NONCE_BYTES = 12


class MasterKey:
    def __init__(self, raw: bytes) -> None:
        if len(raw) != _KEY_BYTES:
            raise ValueError("a master key is 32 bytes")
        self._cipher = AESGCM(raw)
        self._raw = raw
        self.id = hashlib.sha256(raw).hexdigest()[:16]

    @classmethod
    def generate(cls) -> MasterKey:
        return cls(secrets.token_bytes(_KEY_BYTES))

    @classmethod
    def read(cls, path: Path) -> MasterKey:
        """Read the key file. Without it, secrets can be neither stored nor read (ACC-6)."""
        try:
            return cls(base64.b64decode(path.read_text(encoding="ascii").strip()))
        except (OSError, ValueError):
            raise Refusal(
                "master_key_missing",
                f"The master key at {path} is missing or unreadable, so secrets cannot be "
                "stored or read.",
                rule=ACC_6.id,
                hint="Restore the key from a backup, or run `squad setup` on a new install.",
            ) from None

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as file:
            file.write(base64.b64encode(self._raw).decode("ascii"))

    def seal(self, value: str, bound_to: bytes | None = None) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        return nonce, self._cipher.encrypt(nonce, value.encode(), bound_to)

    def open(self, nonce: bytes, ciphertext: bytes, bound_to: bytes | None = None) -> str:
        return self._cipher.decrypt(nonce, ciphertext, bound_to).decode()


def binding(owner_kind: str, owner_id: str, name: str) -> bytes:
    """What a value is sealed to: its owner and its name (CON-2, finding 10 of the phase 7.B
    review). The separator cannot occur in any of the three."""
    return "\x1f".join((owner_kind, owner_id, name)).encode()


def _binding_of(row: StoredSecret) -> bytes:
    return binding(row.owner_kind, row.owner_id, row.name)


def ensure_master_key(path: Path) -> bool:
    """Create the master key if there is none. Never overwrites one (NFR-2). Returns whether
    a key was created."""
    if path.exists():
        return False
    MasterKey.generate().write(path)
    return True


class SecretStore:
    """Named secret values per owner. Values leave only through `reveal`, for the platform's
    own use; no operation output carries one (INV-6)."""

    def __init__(self, key_file: Path) -> None:
        self._key_file = key_file

    async def put(
        self, session: AsyncSession, owner: tuple[str, str], name: str, value: str, now: datetime
    ) -> None:
        key = MasterKey.read(self._key_file)
        nonce, ciphertext = key.seal(value, binding(owner[0], owner[1], name))
        row = await self._row(session, owner, name)
        if row is None:
            row = StoredSecret(
                owner_kind=owner[0],
                owner_id=owner[1],
                name=name,
                nonce=nonce,
                ciphertext=ciphertext,
                key_id=key.id,
                bound=True,
                created_at=now,
            )
            session.add(row)
        else:
            row.nonce, row.ciphertext, row.key_id, row.bound = nonce, ciphertext, key.id, True

    async def reveal(self, session: AsyncSession, owner: tuple[str, str], name: str) -> str | None:
        """The value, for the platform's own use. A value that cannot be opened as sealed to
        this row is refused, never returned."""
        key = MasterKey.read(self._key_file)
        row = await self._row(session, owner, name)
        if row is None:
            return None
        if not row.bound:
            return self._bind(key, row)
        try:
            return key.open(row.nonce, row.ciphertext, _binding_of(row))
        except InvalidTag:
            raise Refusal(
                "secret_unreadable",
                f"The secret {row.name} cannot be read: it was not sealed for this place.",
                rule=ACC_6.id,
                hint="Replace its value.",
            ) from None

    async def delete(self, session: AsyncSession, owner: tuple[str, str], name: str) -> None:
        row = await self._row(session, owner, name)
        if row is not None:
            await session.delete(row)

    @staticmethod
    def _bind(key: MasterKey, row: StoredSecret) -> str:
        """A value stored before values were bound to their row: open it, and seal it again,
        bound. The caller's transaction keeps the change."""
        value = key.open(row.nonce, row.ciphertext)
        row.nonce, row.ciphertext = key.seal(value, _binding_of(row))
        row.key_id, row.bound = key.id, True
        return value

    async def bind_all(self, session: AsyncSession) -> int:
        """Seal every value stored before values were bound to their row. Run once when the
        server starts; safe to repeat. Returns how many were sealed again."""
        key = MasterKey.read(self._key_file)
        rows = list(
            await session.scalars(select(StoredSecret).where(StoredSecret.bound.is_(False)))
        )
        for row in rows:
            self._bind(key, row)
        return len(rows)

    async def rotate(self, session: AsyncSession) -> int:
        """Re-encrypt every secret under a new key, all or nothing (ACC-6).

        The new key is written beside the old one first. Every value is re-sealed in the
        caller's transaction; if one cannot be opened, the error aborts that transaction and
        the old key stays. The caller commits, then calls `finish_rotation`.
        """
        old = MasterKey.read(self._key_file)
        new = MasterKey.generate()
        rows = list(await session.scalars(select(StoredSecret)))
        for row in rows:
            try:
                value = old.open(row.nonce, row.ciphertext, _binding_of(row) if row.bound else None)
            except InvalidTag:
                raise Refusal(
                    "secret_unreadable",
                    f"The secret {row.name} cannot be read with the current master key, so "
                    "nothing was rotated.",
                    rule=ACC_6.id,
                    hint="Restore the matching key from a backup, then rotate again.",
                ) from None
            row.nonce, row.ciphertext = new.seal(value, _binding_of(row))
            row.key_id, row.bound = new.id, True
        new.write(self.pending_key_file)
        return len(rows)

    @property
    def pending_key_file(self) -> Path:
        return self._key_file.with_suffix(self._key_file.suffix + ".next")

    def finish_rotation(self) -> None:
        """Make the new key current, once the re-encrypted values are committed."""
        self.pending_key_file.replace(self._key_file)

    def abandon_rotation(self) -> None:
        self.pending_key_file.unlink(missing_ok=True)

    async def recover_rotation(self, session: AsyncSession) -> bool:
        """Finish or abandon a rotation interrupted between commit and key swap."""
        if not self.pending_key_file.exists():
            return False
        pending = MasterKey.read(self.pending_key_file)
        sealed_with = set(await session.scalars(select(StoredSecret.key_id).distinct()))
        if sealed_with == {pending.id}:
            self.finish_rotation()
            return True
        self.abandon_rotation()
        return False

    async def _row(
        self, session: AsyncSession, owner: tuple[str, str], name: str
    ) -> StoredSecret | None:
        return await session.scalar(
            select(StoredSecret).where(
                StoredSecret.owner_kind == owner[0],
                StoredSecret.owner_id == owner[1],
                StoredSecret.name == name,
            )
        )
