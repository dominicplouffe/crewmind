"""Signing in to an MCP server with OAuth, as the MCP authorization specification asks
(CON-10): the server's protected-resource metadata, then its authorization server's
metadata; dynamic client registration where offered, otherwise a pasted client id; the
authorization code with PKCE S256; the resource indicator for audience binding; and
refreshing tokens, keeping a rotated refresh token.

Every request goes through the same address guard as the MCP server itself (CON-9). What
the servers answer is untrusted: only the fields named here are read.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx2

from crewmind.domain.connections import mcp_client
from crewmind.domain.connections.mcp_client import Unreachable

CLIENT_NAME = "crewmind"


@dataclass(frozen=True)
class Endpoints:
    resource: str
    issuer: str
    authorization: str
    token: str
    registration: str | None
    scopes: list[str]


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str | None
    expires_in: int | None

    def __repr__(self) -> str:  # never shows a token, in a log or a traceback
        return f"Tokens(expires_in={self.expires_in})"


def new_verifier() -> tuple[str, str]:
    """A PKCE verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def new_state() -> tuple[str, str]:
    """A single-use state and the hash it is kept as."""
    state = secrets.token_urlsafe(32)
    return state, hashlib.sha256(state.encode()).hexdigest()


def state_key(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _well_known(url: str, name: str) -> list[str]:
    """RFC 8414 and RFC 9728 places: the name inserted before the path, then at the root."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    places = [urlunsplit((parts.scheme, parts.netloc, f"/.well-known/{name}{path}", "", ""))]
    if path:
        places.append(urlunsplit((parts.scheme, parts.netloc, f"/.well-known/{name}", "", "")))
    return places


async def _json(http: httpx2.AsyncClient, url: str) -> dict[str, Any] | None:
    try:
        answer = await http.get(url)
    except httpx2.HTTPError:
        return None
    if answer.status_code != 200:
        return None
    try:
        data = _dict(answer.json())
    except ValueError:
        return None
    return data or None


def _client(private_allowed: bool, seconds: float) -> httpx2.AsyncClient:
    return mcp_client.client_factory[0]({}, private_allowed, seconds)


def _dict(value: object) -> dict[str, Any]:
    """A JSON object from an untrusted answer, or an empty one."""
    if not isinstance(value, dict):
        return {}
    items = cast(dict[object, object], value)
    return {str(key): item for key, item in items.items()}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def _text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


async def discover(url: str, *, private_allowed: bool, seconds: float) -> Endpoints:
    """Where to sign in for this server (CON-10)."""
    async with _client(private_allowed, seconds) as http:
        resource_meta: dict[str, Any] | None = None
        try:
            challenge = await http.post(url, json={"jsonrpc": "2.0", "id": 0, "method": "ping"})
            header = challenge.headers.get("www-authenticate", "")
            if "resource_metadata=" in header:
                pointed = header.split("resource_metadata=", 1)[1].split(",")[0].strip().strip('"')
                resource_meta = await _json(http, pointed)
        except httpx2.HTTPError:
            pass
        for place in [] if resource_meta else _well_known(url, "oauth-protected-resource"):
            resource_meta = await _json(http, place)
            if resource_meta:
                break
        servers = (resource_meta or {}).get("authorization_servers") or [_origin(url)]
        issuer = str(servers[0]) if servers else _origin(url)
        resource = _text(resource_meta or {}, "resource") or url
        server_meta: dict[str, Any] | None = None
        for place in [
            *_well_known(issuer, "oauth-authorization-server"),
            *_well_known(issuer, "openid-configuration"),
        ]:
            server_meta = await _json(http, place)
            if server_meta:
                break
    if (
        not server_meta
        or not _text(server_meta, "authorization_endpoint")
        or not _text(server_meta, "token_endpoint")
    ):
        raise Unreachable("it does not say where to sign in (no OAuth authorization server found)")
    methods = _strings(server_meta.get("code_challenge_methods_supported")) or ["S256"]
    if "S256" not in methods:
        raise Unreachable("its authorization server does not offer PKCE with S256")
    scopes = _strings((resource_meta or {}).get("scopes_supported")) or _strings(
        server_meta.get("scopes_supported")
    )
    return Endpoints(
        resource=resource,
        issuer=issuer,
        authorization=str(server_meta["authorization_endpoint"]),
        token=str(server_meta["token_endpoint"]),
        registration=_text(server_meta, "registration_endpoint"),
        scopes=scopes[:20],
    )


async def register(
    endpoints: Endpoints, redirect_uri: str, *, private_allowed: bool, seconds: float
) -> tuple[str, str | None]:
    """Dynamic client registration: a client id, and a secret if the server gives one."""
    if endpoints.registration is None:
        raise Unreachable("its authorization server offers no registration; paste a client id")
    async with _client(private_allowed, seconds) as http:
        answer = await http.post(
            endpoints.registration,
            json={
                "client_name": CLIENT_NAME,
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
    if answer.status_code not in (200, 201):
        raise Unreachable(
            f"its authorization server refused the registration (HTTP {answer.status_code})"
        )
    data = _dict(answer.json())
    client_id = _text(data, "client_id")
    if client_id is None:
        raise Unreachable("its authorization server registered no client id")
    return client_id, _text(data, "client_secret")


def authorize_url(
    endpoints: Endpoints, client_id: str, redirect_uri: str, state: str, challenge: str
) -> str:
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": endpoints.resource,
    }
    if endpoints.scopes:
        query["scope"] = " ".join(endpoints.scopes)
    separator = "&" if "?" in endpoints.authorization else "?"
    return f"{endpoints.authorization}{separator}{urlencode(query)}"


async def _token(
    token_url: str, form: dict[str, str], client_secret: str | None, *, private_allowed: bool,
    seconds: float,
) -> Tokens:  # fmt: skip
    auth = None
    if client_secret:
        pair = f"{form['client_id']}:{client_secret}".encode()
        auth = {"Authorization": "Basic " + base64.b64encode(pair).decode()}
    async with _client(private_allowed, seconds) as http:
        answer = await http.post(token_url, data=form, headers=auth or {})
    if answer.status_code != 200:
        raise Unreachable(
            f"its authorization server refused the tokens (HTTP {answer.status_code})"
        )
    data = _dict(answer.json())
    access = _text(data, "access_token")
    if access is None:
        raise Unreachable("its authorization server sent no access token")
    expires: object = data.get("expires_in")
    return Tokens(
        access=access,
        refresh=_text(data, "refresh_token"),
        expires_in=int(expires) if isinstance(expires, int | float) else None,
    )


async def exchange(
    endpoints_token: str, resource: str, client_id: str, client_secret: str | None, code: str,
    verifier: str, redirect_uri: str, *, private_allowed: bool, seconds: float,
) -> Tokens:  # fmt: skip
    """The authorization code, with its PKCE verifier and the resource, for tokens."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": resource,
    }
    return await _token(
        endpoints_token, form, client_secret, private_allowed=private_allowed, seconds=seconds
    )


async def refresh(
    endpoints_token: str, resource: str, client_id: str, client_secret: str | None,
    refresh_token: str, *, private_allowed: bool, seconds: float,
) -> Tokens:  # fmt: skip
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "resource": resource,
    }
    return await _token(
        endpoints_token, form, client_secret, private_allowed=private_allowed, seconds=seconds
    )
