"""Password hashing with a memory-hard function (ACC-1)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.accounts.model import PASSWORD_MIN_LENGTH

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("a password nobody has")


def hash_password(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise Refusal(
            "password_too_short",
            f"A password needs at least {PASSWORD_MIN_LENGTH} characters; this one has "
            f"{len(password)}.",
            kind=RefusalKind.INVALID,
            rule="ACC-1",
            hint="Choose a longer password.",
        )
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Check a password. With no stored hash, a dummy hash is checked instead, so an unknown
    or unusable account takes as long to refuse as a wrong password (ACC-1)."""
    try:
        _hasher.verify(stored_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return stored_hash is not None
