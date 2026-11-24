"""What the terminal chat asks of the server. Every call is a catalog operation over the
HTTP API, plus the live stream (IF-4.1, IF-4.8)."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx

from nightsquad.catalog.refusal import ErrorEnvelope


class ChatError(Exception):
    """The server refused, in its own words."""


class ChatClient:
    def __init__(self, client_factory: Callable[[], httpx.AsyncClient], token: str | None) -> None:
        self._client_factory = client_factory
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def _call(self, method: str, path: str, **values: Any) -> dict[str, Any]:
        async with self._client_factory() as client:
            if method == "GET":
                response = await client.get(path, params=values, headers=self._headers)
            else:
                response = await client.post(path, json=values, headers=self._headers)
        data: dict[str, Any] = response.json()
        if not response.is_success:
            envelope = ErrorEnvelope.model_validate(data)
            raise ChatError(envelope.message + (f" {envelope.hint}" if envelope.hint else ""))
        return data

    async def projects(self) -> list[dict[str, Any]]:
        return (await self._call("GET", "/v1/projects/list"))["items"]

    async def history(self, project_id: str) -> list[dict[str, Any]]:
        found = await self._call("GET", "/v1/chat/history", project_id=project_id, limit=200)
        return found["items"]

    async def header(self, project_id: str) -> dict[str, Any]:
        return await self._call("GET", "/v1/chat/header", project_id=project_id)

    async def send(self, project_id: str, body: str) -> dict[str, Any]:
        return await self._call("POST", "/v1/chat/send", project_id=project_id, body=body)

    async def command(self, project_id: str, text: str) -> dict[str, Any]:
        return await self._call("POST", "/v1/chat/command", project_id=project_id, text=text)

    async def attach(self, project_id: str, path: Path) -> dict[str, Any]:
        raw = await asyncio.to_thread(path.read_bytes)
        content = base64.b64encode(raw).decode("ascii")
        return await self._call(
            "POST",
            "/v1/artifacts/upload",
            project_id=project_id,
            name=path.name,
            content_base64=content,
        )

    async def interrupt(self, project_id: str, run_id: str) -> dict[str, Any]:
        return await self._call("POST", "/v1/runs/interrupt", project_id=project_id, run_id=run_id)

    async def stream(
        self, project_id: str, after_message: int
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """The project's live events: (kind, data) pairs, for ever."""
        async with (
            self._client_factory() as client,
            client.stream(
                "GET",
                f"/stream/v1/projects/{project_id}",
                params={"after_message": after_message, "after_event": 2**62},
                headers=self._headers,
                timeout=None,
            ) as response,
        ):
            kind = ""
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    kind = line[7:]
                elif line.startswith("data: ") and kind:
                    yield kind, json.loads(line[6:])
