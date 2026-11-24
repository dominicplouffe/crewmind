"""Two-phase confirmation for irreversible MCP writes (IF-5.3, section 7.10).

The first call returns a preview and a confirm token bound to the tool and a hash of its
exact arguments. The second call, with the same arguments and the token, spends it. A
token is used once and lives 5 minutes.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Caller
from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.state_machine import NEW, StateMachine
from nightsquad.storage.models import McpConfirmToken

IF_5_3 = rules.register(
    Rule("IF-5.3", "An irreversible MCP write needs a confirm token for its exact arguments.")
)
LIFE = timedelta(minutes=5)  # IF-5.3
UNSPENT, SPENT, EXPIRED = "unspent", "spent", "expired"
CONFIRM_MACHINE = StateMachine(
    "MCP confirm token", "7.10", [(NEW, UNSPENT), (UNSPENT, SPENT), (UNSPENT, EXPIRED)]
)
PREFIX = "ns_confirm_"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def arguments_hash(tool: str, arguments: dict[str, Any]) -> str:
    return _hash(tool + "\n" + json.dumps(arguments, sort_keys=True, separators=(",", ":")))


async def issue(
    session: AsyncSession, caller: Caller, tool: str, arguments: dict[str, Any], now: datetime
) -> str:
    """Make a confirm token for this exact call. Only its hash is stored."""
    CONFIRM_MACHINE.check(NEW, UNSPENT)
    plain = PREFIX + secrets.token_urlsafe(24)
    session.add(
        McpConfirmToken(
            token_hash=_hash(plain),
            person_id=caller.actor_id,
            client=caller.via,
            tool=tool,
            arguments_hash=arguments_hash(tool, arguments),
            state=UNSPENT,
            created_at=now,
            expires_at=now + LIFE,
        )
    )
    return plain


async def spend(
    session: AsyncSession,
    caller: Caller,
    tool: str,
    arguments: dict[str, Any],
    token: str,
    now: datetime,
) -> None:
    """Spend a confirm token, or refuse: unknown, another client's, another tool's,
    different arguments, already spent, or older than 5 minutes."""
    row = await session.scalar(
        select(McpConfirmToken).where(McpConfirmToken.token_hash == _hash(token))
    )
    matches = (
        row is not None
        and row.person_id == caller.actor_id
        and row.client == caller.via
        and row.tool == tool
        and row.arguments_hash == arguments_hash(tool, arguments)
    )
    if row is None or not matches:
        raise Refusal(
            "confirm_token_does_not_match",
            "This confirm token is not for this tool with these exact arguments.",
            rule=IF_5_3.id,
            hint="Call the tool again without `confirm` to get a new preview and token.",
        )
    if row.state == UNSPENT and now > row.expires_at:
        CONFIRM_MACHINE.check(row.state, EXPIRED)
        row.state = EXPIRED
    if row.state != UNSPENT:
        raise Refusal(
            f"confirm_token_{row.state}",
            f"This confirm token is {row.state}. A token is used once, within 5 minutes.",
            rule=IF_5_3.id,
            hint="Call the tool again without `confirm` to get a new preview and token.",
        )
    CONFIRM_MACHINE.check(row.state, SPENT)
    row.state = SPENT
