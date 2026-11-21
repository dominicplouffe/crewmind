"""How the CLI carries out an operation: over the HTTP API, or on the host (IF-4.1, IF-4.2)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from crewmind.catalog.operation import Operation
from crewmind.catalog.refusal import ErrorEnvelope, Refusal
from crewmind.surfaces.api.app import route_method, route_path


class ServerUnreachable(Exception):
    """The server did not answer (IF-4.4)."""


class Invoker(Protocol):
    async def invoke(self, operation: Operation, payload: BaseModel) -> BaseModel: ...


class HttpInvoker:
    """Calls the operation's API route. This is how every command but the host-local ones runs."""

    def __init__(self, client_factory: Callable[[], httpx.AsyncClient]) -> None:
        self._client_factory = client_factory

    async def invoke(self, operation: Operation, payload: BaseModel) -> BaseModel:
        path = route_path(operation.name)
        try:
            async with self._client_factory() as client:
                if route_method(operation) == "GET":
                    response = await client.get(
                        path, params=payload.model_dump(mode="json", exclude_none=True)
                    )
                else:
                    response = await client.post(path, json=payload.model_dump(mode="json"))
        except httpx.TransportError as error:
            raise ServerUnreachable(str(error)) from error
        if response.is_success:
            return operation.output.model_validate(response.json())
        try:
            envelope = ErrorEnvelope.model_validate(response.json())
        except (ValueError, ValidationError):
            raise ServerUnreachable(
                f"unexpected answer from the server: HTTP {response.status_code}"
            ) from None
        raise Refusal.from_envelope(envelope)


class LocalInvoker:
    """Runs a host-local operation in this process, without the server (IF-4.2)."""

    async def invoke(self, operation: Operation, payload: BaseModel) -> BaseModel:
        if not operation.host_local:
            raise RuntimeError(f"{operation.name} is not host-local and must go through the API")
        return await operation.handler(payload)


def http_client_factory(base_url: str, token: str | None) -> Callable[[], httpx.AsyncClient]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=base_url, headers=headers)

    return factory
