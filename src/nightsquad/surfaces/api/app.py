"""The HTTP API, generated from the operation catalog (IF-1.2, IF-3.1 to IF-3.7).

This adapter holds no business rules. It reads the credential, hands the call to the
executor, and translates the answer. Each operation gets one route derived from its name:
`projects.hold` is `POST /v1/projects/hold`; operations of class `read` use `GET`.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from nightsquad.catalog.execute import Executor
from nightsquad.catalog.operation import Operation, Reversibility
from nightsquad.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from nightsquad.catalog.registry import Catalog
from nightsquad.catalog.rules import Rule, rules
from nightsquad.catalog.surfaces import Surface, exposed_on, takes_a_document
from nightsquad.domain.accounts.credentials import Authenticator

API_PREFIX = "/v1"
SESSION_COOKIE = "nightsquad_session"
IDEMPOTENCY_HEADER = "Idempotency-Key"

IF_3_7 = rules.register(Rule("IF-3.7", "A browser session writes only from the app's own origin."))

STATUS_BY_KIND: dict[RefusalKind, int] = {
    RefusalKind.RULE: 403,
    RefusalKind.FORBIDDEN: 403,
    RefusalKind.UNAUTHENTICATED: 401,
    RefusalKind.NOT_FOUND: 404,
    RefusalKind.INVALID: 422,
}

# Operations after which the session cookie is set or cleared (ACC-2, IF-3.7).
_SETS_COOKIE = "auth.login"
_CLEARS_COOKIE = frozenset({"auth.logout", "auth.change_password"})


def route_path(operation_name: str) -> str:
    return f"{API_PREFIX}/{operation_name.replace('.', '/')}"


def reads_a_document(operation: Operation) -> bool:
    """A read whose input is a whole document (a role, a squad, a project spec) cannot be
    sent in a query string."""
    return operation.reversibility is Reversibility.READ and takes_a_document(operation.input)


def route_method(operation: Operation) -> str:
    """Reads are GET, except one that takes a document, which is sent as a POST body."""
    if operation.reversibility is Reversibility.READ and not reads_a_document(operation):
        return "GET"
    return "POST"


def invalid_input(detail: object) -> ErrorEnvelope:
    return ErrorEnvelope(
        kind=RefusalKind.INVALID,
        code="invalid_input",
        message=f"The input is not valid: {detail}",
        hint="Check the operation's input schema.",
    )


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _credential(request: Request, operation: Operation, allowed_origin: str) -> str | None:
    """The bearer token, or else the session cookie. A write carried by the cookie must come
    from the app's own origin (IF-3.7): another site can send the cookie but not the token."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    cookie = request.cookies.get(SESSION_COOKIE)
    origin = request.headers.get("Origin")
    is_write = operation.reversibility is not Reversibility.READ
    if cookie and is_write and origin is not None and origin != allowed_origin:
        raise Refusal(
            "cross_origin_write",
            f"A write from {origin} was refused: only {allowed_origin} may write with a "
            "browser session.",
            kind=RefusalKind.FORBIDDEN,
            rule=IF_3_7.id,
            hint="Use the app, or a personal token.",
        )
    return cookie


def _endpoint(
    operation: Operation, executor: Executor, authenticator: Authenticator, base_url: str
) -> Callable[..., Awaitable[JSONResponse]]:
    allowed_origin = _origin(base_url)
    secure = base_url.startswith("https://")

    async def endpoint(request: Request, payload: Any) -> JSONResponse:
        credential = _credential(request, operation, allowed_origin)
        caller = await authenticator.authenticate(credential)
        result = await executor.execute(
            operation, caller, payload, idempotency_key=request.headers.get(IDEMPOTENCY_HEADER)
        )
        response = JSONResponse(result.model_dump(mode="json"))
        if operation.name == _SETS_COOKIE:
            response.set_cookie(
                SESSION_COOKIE,
                result.model_dump()["session"],
                httponly=True,
                samesite="strict",
                secure=secure,
                path="/",
            )
        elif operation.name in _CLEARS_COOKIE:
            response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    annotation: Any = operation.input
    if route_method(operation) == "GET":
        annotation = Annotated[operation.input, Query()]
    parameters = [
        inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
        inspect.Parameter(
            "payload", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation
        ),
    ]
    endpoint.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    endpoint.__annotations__ = {"request": Request, "payload": annotation}
    return endpoint


def build_api(
    catalog: Catalog, executor: Executor, authenticator: Authenticator, *, base_url: str
) -> FastAPI:
    """Build the API with one route per operation that belongs on it."""
    app = FastAPI(title="nightsquad", version="1")

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
            _endpoint(operation, executor, authenticator, base_url),
            methods=[route_method(operation)],
            response_model=operation.output,
            operation_id=operation.name,
            summary=operation.summary,
            description=f"Requires: {operation.authority.value}.",
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
