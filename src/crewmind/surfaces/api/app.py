"""The HTTP API, generated from the operation catalog (IF-1.2, IF-3.1, IF-3.4).

This adapter holds no business rules. Each operation gets one route derived from its name:
`projects.hold` is `POST /v1/projects/hold`; operations of class `read` use `GET`.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from crewmind.catalog.operation import Operation, Reversibility
from crewmind.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from crewmind.catalog.registry import Catalog
from crewmind.catalog.surfaces import Surface, exposed_on

API_PREFIX = "/v1"

STATUS_BY_KIND: dict[RefusalKind, int] = {
    RefusalKind.RULE: 403,
    RefusalKind.FORBIDDEN: 403,
    RefusalKind.UNAUTHENTICATED: 401,
    RefusalKind.NOT_FOUND: 404,
    RefusalKind.INVALID: 422,
}


def route_path(operation_name: str) -> str:
    return f"{API_PREFIX}/{operation_name.replace('.', '/')}"


def route_method(operation: Operation) -> str:
    return "GET" if operation.reversibility is Reversibility.READ else "POST"


def _endpoint(operation: Operation) -> Callable[..., Awaitable[BaseModel]]:
    async def endpoint(payload: Any) -> BaseModel:
        return await operation.handler(payload)

    annotation: Any = operation.input
    if operation.reversibility is Reversibility.READ:
        annotation = Annotated[operation.input, Query()]
    parameter = inspect.Parameter(
        "payload", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation
    )
    endpoint.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [parameter], return_annotation=operation.output
    )
    endpoint.__annotations__ = {"payload": annotation, "return": operation.output}
    return endpoint


def invalid_input(detail: object) -> ErrorEnvelope:
    return ErrorEnvelope(
        kind=RefusalKind.INVALID,
        code="invalid_input",
        message=f"The input is not valid: {detail}",
        hint="Check the operation's input schema.",
    )


def build_api(catalog: Catalog) -> FastAPI:
    """Build the API with one route per operation that belongs on it."""
    app = FastAPI(title="crewmind", version="1")

    async def refused(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, Refusal)
        envelope = error.envelope
        return JSONResponse(envelope.model_dump(), status_code=STATUS_BY_KIND[envelope.kind])

    async def invalid(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, RequestValidationError)
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'][1:])}: {problem['msg']}"
            for problem in error.errors()
        )
        envelope = invalid_input(problems)
        return JSONResponse(envelope.model_dump(), status_code=STATUS_BY_KIND[envelope.kind])

    app.add_exception_handler(Refusal, refused)
    app.add_exception_handler(RequestValidationError, invalid)

    for operation in catalog:
        if not exposed_on(operation, Surface.API):
            continue
        app.add_api_route(
            route_path(operation.name),
            _endpoint(operation),
            methods=[route_method(operation)],
            response_model=operation.output,
            operation_id=operation.name,
            summary=operation.summary,
            tags=[operation.group],
        )
    return app


def exposed_operations(app: FastAPI) -> set[str]:
    """The operation names the API actually serves: every route under the versioned prefix."""
    names: set[str] = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(f"{API_PREFIX}/"):
            names.add(route.path.removeprefix(f"{API_PREFIX}/").replace("/", "."))
    return names
