"""Refusals: one error shape on every surface (IF-1.4, IF-3.4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class RefusalKind(StrEnum):
    """Why a call was refused. Surfaces map the kind to a status or exit code (IF-3.3, IF-4.4)."""

    RULE = "rule"
    FORBIDDEN = "forbidden"
    UNAUTHENTICATED = "unauthenticated"
    NOT_FOUND = "not_found"
    INVALID = "invalid"


class ErrorEnvelope(BaseModel):
    """The stable error envelope (IF-3.4): identical on every surface (IF-1.4)."""

    kind: RefusalKind
    code: str
    message: str
    rule: str | None = None
    hint: str | None = None


class Refusal(Exception):
    """A refused call. `message` is the plain sentence, `rule` the rule id when a governed rule
    refused, and `hint` the legitimate path forward (IF-1.4)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        kind: RefusalKind = RefusalKind.RULE,
        rule: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.envelope = ErrorEnvelope(kind=kind, code=code, message=message, rule=rule, hint=hint)
        self.afterwards: Any = None
        """An async function of a database session, run in its own transaction after the
        refused call is rolled back: for what must be recorded even though the call failed."""

    @classmethod
    def from_envelope(cls, envelope: ErrorEnvelope) -> Refusal:
        return cls(
            envelope.code,
            envelope.message,
            kind=envelope.kind,
            rule=envelope.rule,
            hint=envelope.hint,
        )
