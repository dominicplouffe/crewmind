"""A local OAuth authorization server and a protected MCP server, for the sign-in tests.
It issues short-lived access tokens, rotates refresh tokens, checks PKCE S256 and the
resource indicator, and can refuse every refresh."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs

import httpx2
from mcp.server.transport_security import TransportSecuritySettings

from nightsquad.domain.connections import mcp_client
from tests.attack.mcp_support import URL, Receive, Scope, Send, build_server

ISSUER = "https://auth.test"
RESOURCE_META = "https://mcp.test/.well-known/oauth-protected-resource/mcp"


class Authority:
    def __init__(self, access_life: int = 3600) -> None:
        self.access_life = access_life
        self.codes: dict[str, dict[str, str]] = {}
        self.access: set[str] = set()
        self.refresh: set[str] = set()
        self.refused_refresh = False
        self.grants: list[str] = []
        self.registered: list[dict[str, Any]] = []

    def code_for(self, query: dict[str, str]) -> str:
        """What the provider's sign-in page would do once the person agrees."""
        code = secrets.token_urlsafe(12)
        self.codes[code] = query
        return code

    def _tokens(self) -> dict[str, Any]:
        access, refresh = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
        self.access.add(access)
        self.refresh.add(refresh)
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": self.access_life,
            "token_type": "Bearer",
        }

    def token(self, form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        self.grants.append(form.get("grant_type", ""))
        if form.get("resource") != URL:
            return 400, {"error": "invalid_target"}
        if form.get("grant_type") == "authorization_code":
            asked = self.codes.pop(form.get("code", ""), None)
            if asked is None:
                return 400, {"error": "invalid_grant"}
            digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
            if (
                challenge != asked["code_challenge"]
                or form.get("redirect_uri") != asked["redirect_uri"]
            ):
                return 400, {"error": "invalid_grant"}
            return 200, self._tokens()
        if form.get("grant_type") == "refresh_token":
            token = form.get("refresh_token", "")
            if self.refused_refresh or token not in self.refresh:
                return 400, {"error": "invalid_grant"}
            self.refresh.discard(token)  # rotated: the old one never works again
            return 200, self._tokens()
        return 400, {"error": "unsupported_grant_type"}


async def _respond(
    send: Send, status: int, body: dict[str, Any], headers: list[tuple[bytes, bytes]] | None = None
) -> None:
    data = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), *(headers or [])],
        }
    )
    await send({"type": "http.response.body", "body": data})


async def _body(receive: Receive) -> bytes:
    chunks = b""
    while True:
        message = await receive()
        chunks += message.get("body", b"")
        if not message.get("more_body"):
            return chunks


@asynccontextmanager
async def oauth_serving(authority: Authority) -> AsyncGenerator[Authority]:
    server = build_server()
    mcp_app = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await mcp_app(scope, receive, send)
            return
        path = scope["path"]
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if path == "/.well-known/oauth-protected-resource/mcp":
            await _respond(send, 200, {"resource": URL, "authorization_servers": [ISSUER]})
        elif path == "/.well-known/oauth-authorization-server":
            await _respond(send, 200, {
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token", "registration_endpoint": f"{ISSUER}/register",
                "code_challenge_methods_supported": ["S256"],
            })  # fmt: skip
        elif path == "/register":
            authority.registered.append(json.loads(await _body(receive)))
            await _respond(send, 201, {"client_id": "client-1"})
        elif path == "/token":
            form = {
                key: values[0] for key, values in parse_qs((await _body(receive)).decode()).items()
            }
            status, body = authority.token(form)
            await _respond(send, status, body)
        elif path.startswith("/mcp"):
            bearer = headers.get("authorization", "").removeprefix("Bearer ")
            if bearer not in authority.access:
                await _respond(
                    send, 401, {"error": "invalid_token"},
                    [(b"www-authenticate", f'Bearer resource_metadata="{RESOURCE_META}"'.encode())],
                )  # fmt: skip
                return
            await mcp_app(scope, receive, send)
        else:
            await _respond(send, 404, {})

    def local(headers: dict[str, str], private: bool, seconds: float) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="https://mcp.test", headers=headers,
            timeout=seconds,
        )  # fmt: skip

    previous = mcp_client.client_factory[0]
    mcp_client.client_factory[0] = local
    try:
        async with server.session_manager.run():
            yield authority
    finally:
        mcp_client.client_factory[0] = previous
