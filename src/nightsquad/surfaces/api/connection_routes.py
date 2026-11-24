"""The browser's way back from an MCP server's sign-in page (CON-10): a thin adapter over
`connections.finish_sign_in`. It reads the session cookie, finishes the sign-in, and sends
the browser back to where it started. No rule lives here."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from nightsquad.catalog.execute import Executor
from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.registry import catalog
from nightsquad.domain.accounts.credentials import Authenticator
from nightsquad.domain.connections.mcp_sign_in import CALLBACK_PATH
from nightsquad.surfaces.api.app import SESSION_COOKIE

FALLBACK = "/settings/connections"


def _back(to: str, **query: str) -> RedirectResponse:
    place = to if to.startswith("/") and not to.startswith("//") else FALLBACK
    separator = "&" if "?" in place else "?"
    return RedirectResponse(f"{place}{separator}{urlencode(query)}", status_code=303)


def add_connection_routes(app: FastAPI, executor: Executor, authenticator: Authenticator) -> None:
    async def callback(request: Request) -> RedirectResponse:
        query = request.query_params
        if query.get("error"):
            return _back(FALLBACK, sign_in_error=query.get("error_description") or query["error"])
        caller = await authenticator.authenticate(request.cookies.get(SESSION_COOKIE))
        operation = catalog.get("connections.finish_sign_in")
        try:
            payload = operation.input.model_validate(
                {"code": query.get("code", ""), "state": query.get("state", "")}
            )
            result = await executor.execute(operation, caller, payload)
        except Refusal as refusal:
            return _back(FALLBACK, sign_in_error=refusal.envelope.message)
        except ValueError:
            return _back(FALLBACK, sign_in_error="The provider sent back an incomplete answer.")
        data = result.model_dump()
        return _back(str(data["return_to"]), signed_in=str(data["name"]))

    app.add_api_route(CALLBACK_PATH, callback, methods=["GET"], include_in_schema=False)
