"""Live, unstored signals inside the server process (IF-3.6, CHAT-3)."""

from __future__ import annotations

import asyncio
from typing import Any

SUBSCRIBER_QUEUE = 1000


class StreamHub:
    """In-process fan-out of things that are not stored: the words of a reply in progress
    and what an agent is doing right now."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._held: dict[str, dict[str, Any]] = {}

    def hold(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish something that stays true until it is replaced or released, and keep
        it, so that whoever starts watching later is told it too (P17)."""
        self._held[topic] = payload
        self.publish(topic, payload)

    def holding(self, topic: str) -> dict[str, Any] | None:
        return self._held.get(topic)

    def release(self, topic: str) -> None:
        self._held.pop(topic, None)

    def publish(self, project_id: str, payload: dict[str, Any]) -> None:
        for queue in self._subscribers.get(project_id, ()):
            if queue.qsize() < SUBSCRIBER_QUEUE:
                queue.put_nowait(payload)

    def subscribe(self, project_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(project_id, set()).add(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.get(project_id, set()).discard(queue)
