"""Lets a periodic job run early when something has just changed (SPD-1).

Jobs still tick on their period (section 10). A write operation pings, and each waiting
job wakes without sitting out the rest of its period, so ready work does not wait on a
clock. A ping carries no data: the job reads the database as it always does.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta

SHORTEST_GAP = timedelta(milliseconds=200)
"""A job never runs twice within this gap, so a burst of writes costs one pass (BG-3)."""


class Nudge:
    def __init__(self) -> None:
        self._waiting: list[asyncio.Event] = []

    def waiter(self) -> asyncio.Event:
        """An event of its own for one job loop."""
        event = asyncio.Event()
        self._waiting.append(event)
        return event

    def ping(self) -> None:
        """Something changed: wake every waiting job."""
        for event in self._waiting:
            event.set()


nudge = Nudge()


async def pause(event: asyncio.Event, period: timedelta) -> None:
    """Wait for the next pass: until a ping, and at most one period."""
    await asyncio.sleep(SHORTEST_GAP.total_seconds())
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(event.wait(), (period - SHORTEST_GAP).total_seconds())
    event.clear()
