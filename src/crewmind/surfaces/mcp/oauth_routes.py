"""The standard OAuth endpoints (IF-5.1), as thin adapters over the `oauth.*` operations:
metadata, dynamic client registration, the authorization redirect and the token endpoint.
No rule lives here."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError

from crewmind.catalog import mcp_scopes
from crewmind.catalog.caller import ANONYMOUS
from crewmind.catalog.execute import Executor
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.registry import catalog
from crewmind.domain.accounts.oauth import audience_of

CONSENT_PAGE = "/#/oauth/approve"
"""Where the web app asks the signed-in person to approve the client."""


def add_oauth_routes(app: FastAPI, executor: Executor, base_url: str) -> None:
    issuer = base_url.rstrip("/")

    async def metadata() -> JSONResponse:
        return JSONResponse(
            {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/oauth/authorize",
                "token_endpoint": f"{issuer}/oauth/token",
                "registration_endpoint": f"{issuer}/oauth/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
                "scopes_supported": list(mcp_scopes.SCOPES),
            }
        )

    async def resource() -> JSONResponse:
        return JSONResponse(
            {
                "resource": audience_of(issuer),
                "authorization_servers": [issuer],
                "scopes_supported": list(mcp_scopes.SCOPES),
            }
        )

    async def call(name: str, values: dict[str, Any], status: int = 200) -> JSONResponse:
        operation = catalog.get(name)
        try:
            payload = operation.input.model_validate(values)
            result = await executor.execute(operation, ANONYMOUS, payload)
        except ValidationError:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        except Refusal as refusal:
            envelope = refusal.envelope
            return JSONResponse(
                {"error": envelope.code, "error_description": envelope.message}, status_code=400
            )
        return JSONResponse(result.model_dump(mode="json"), status_code=status)

    async def register(request: Request) -> JSONResponse:
        body = await request.json()
        answer = await call(
            "oauth.register",
            {
                "client_name": body.get("client_name", "MCP client"),
                "redirect_uris": body.get("redirect_uris", []),
            },
            status=201,
        )
        return answer

    async def token(request: Request) -> JSONResponse:
        form = await request.form()
        return await call("oauth.token", {key: str(value) for key, value in form.items()})

    async def authorize(request: Request) -> RedirectResponse:
        """Send the browser to the app, where the signed-in person approves or not."""
        return RedirectResponse(f"{CONSENT_PAGE}?{urlencode(dict(request.query_params))}")

    app.add_api_route("/.well-known/oauth-authorization-server", metadata, methods=["GET"])
    app.add_api_route("/.well-known/oauth-protected-resource", resource, methods=["GET"])
    app.add_api_route("/oauth/register", register, methods=["POST"])
    app.add_api_route("/oauth/token", token, methods=["POST"])
    app.add_api_route("/oauth/authorize", authorize, methods=["GET"])
