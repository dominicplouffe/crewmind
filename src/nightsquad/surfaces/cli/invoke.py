"""How the CLI carries out an operation: over the HTTP API, or on the host (IF-4.1, IF-4.2)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from nightsquad.catalog.caller import HOST_OPERATOR
from nightsquad.catalog.execute import Executor
from nightsquad.catalog.operation import Operation
from nightsquad.catalog.refusal import ErrorEnvelope, Refusal
from nightsquad.surfaces.api.app import route_method, route_path


class ServerUnreachable(Exception):
    """The server did not answer (IF-4.4)."""


class Invoker(Protocol):
    async def invoke(
        self, operation: Operation, payload: BaseModel, *, bearer: str | None = None
    ) -> BaseModel: ...


def _plain(payload: BaseModel) -> dict[str, Any]:
    """Input as JSON data. Secrets are sent, never printed (IF-4.5)."""
    data = payload.model_dump(mode="json")
    for name in type(payload).model_fields:
        value = getattr(payload, name)
        if isinstance(value, SecretStr):
            data[name] = value.get_secret_value()
    return data


class HttpInvoker:
    """Calls the operation's API route. This is how every command but the host-local ones runs."""

    def __init__(
        self,
        client_factory: Callable[[], httpx.AsyncClient],
        token_source: Callable[[], str | None] = lambda: None,
    ) -> None:
        self._client_factory = client_factory
        self._token_source = token_source

    async def invoke(
        self, operation: Operation, payload: BaseModel, *, bearer: str | None = None
    ) -> BaseModel:
        path = route_path(operation.name)
        token = bearer or self._token_source()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data = _plain(payload)
        try:
            async with self._client_factory() as client:
                if route_method(operation) == "GET":
                    params = {key: value for key, value in data.items() if value is not None}
                    response = await client.get(path, params=params, headers=headers)
                else:
                    response = await client.post(path, json=data, headers=headers)
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
    """Runs a host-local operation in this process, as the host operator (IF-4.2)."""

    def __init__(self, executor_factory: Callable[[], Awaitable[Executor]]) -> None:
        self._executor_factory = executor_factory

    async def invoke(
        self, operation: Operation, payload: BaseModel, *, bearer: str | None = None
    ) -> BaseModel:
        if not operation.host_local:
            raise RuntimeError(f"{operation.name} is not host-local and must go through the API")
        executor = await self._executor_factory()
        return await executor.execute(operation, HOST_OPERATOR, payload)


def http_client_factory(base_url: str) -> Callable[[], httpx.AsyncClient]:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=base_url)

    return factory
