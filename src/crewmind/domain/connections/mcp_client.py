"""Reaching a remote MCP server (CON-9, CON-12): the address guard, the transports, and
reading what the server is and which tools it offers.

Everything a server says (its name, its tools, their descriptions and schemas) is
untrusted input (P4): it is cut to size here and never followed as an instruction.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx2
from mcp import Client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import McpHttpClientFactory  # pyright: ignore[reportPrivateUsage]

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules

CON_9 = rules.register(
    Rule(
        "CON-9",
        "A remote MCP server is reached over https at a public address, or one an admin allowed.",
    )
)
CON_12 = rules.register(Rule("CON-12", "A tool that is not marked as only reading starts denied."))

STREAMABLE, SSE = "streamable_http", "sse"
METADATA = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fd00:ec2::254/128"),
    ipaddress.ip_network("100.100.100.200/32"),
)
"""CON-9: link-local and cloud metadata addresses, refused even where private ones are allowed."""


class Unreachable(Exception):
    """The server could not be reached or did not speak MCP. The message is plain words.
    `refused` says the server refused the sign-in, which a fresh token may cure."""

    def __init__(self, message: str, *, refused: bool = False) -> None:
        super().__init__(message)
        self.refused = refused


def check_url(url: str, private_allowed: bool) -> str:
    """CON-9: https only, except http to localhost; no credentials, no fragment."""
    parts = urlsplit(url.strip())
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise Refusal(
            "mcp_url_not_https",
            "An MCP server is reached over https (http only on localhost).",
            rule=CON_9.id,
            hint="Use the server's https address.",
        )
    if not parts.hostname or parts.username or parts.password or parts.fragment:
        raise Refusal(
            "mcp_url_invalid",
            "That is not a usable MCP server address.",
            rule=CON_9.id,
            hint="Give the full address, such as https://mcp.example.com/mcp, with no user name.",
        )
    if local and not private_allowed:
        raise Refusal(
            "mcp_private_address",
            "localhost is a private address. An admin may allow a private address for one server.",
            rule=CON_9.id,
        )
    return url.strip()


def address_allowed(address: str, private_allowed: bool) -> bool:
    ip = ipaddress.ip_address(address)
    if any(ip in network for network in METADATA) or ip.is_multicast or ip.is_unspecified:
        return False
    return ip.is_global or private_allowed


async def check_host(host: str, port: int, private_allowed: bool) -> None:
    """CON-9, WRK-12: every address the host resolves to must be allowed."""
    try:
        found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise Unreachable(f"the host {host} could not be found") from None
    addresses = [str(entry[4][0]) for entry in found]
    if not addresses or not all(address_allowed(a, private_allowed) for a in addresses):
        if private_allowed:
            raise Unreachable(f"{host} is a link-local or cloud metadata address, never reached")
        raise Unreachable(
            f"{host} is not a public address. An admin may allow a private address for this server."
        )


class _Guarded(httpx2.AsyncBaseTransport):
    """Checks the address of every request's host before it is sent (CON-9)."""

    def __init__(self, private_allowed: bool) -> None:
        self._inner = httpx2.AsyncHTTPTransport(trust_env=False)
        self._private = private_allowed

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        url = request.url
        await check_host(
            url.host, url.port or (443 if url.scheme == "https" else 80), self._private
        )
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


ClientFactory = Callable[[dict[str, str], bool, float], httpx2.AsyncClient]


def guarded_client(
    headers: dict[str, str], private_allowed: bool, seconds: float
) -> httpx2.AsyncClient:
    """An HTTP client for one MCP server: its sign-in headers, the address guard, no
    redirects (a redirect could lead anywhere), and the call time limit."""
    return httpx2.AsyncClient(
        transport=_Guarded(private_allowed),
        headers=headers,
        timeout=seconds,
        follow_redirects=False,
        trust_env=False,
    )


client_factory: list[ClientFactory] = [guarded_client]
"""The one factory in use; tests put a local server's in its place."""


@dataclass
class ToolInfo:
    name: str
    title: str | None
    description: str
    input_schema: dict[str, Any]
    reads_only: bool


@dataclass
class Probe:
    transport: str
    name: str | None
    version: str | None
    tools: list[ToolInfo] = field(default_factory=list[ToolInfo])


def _cut(text: str | None, most: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= most else text[: most - 1] + "…"


def classify(annotations: Any) -> bool:
    """CON-12, INT-4: a tool reads only when it says so and does not also say it destroys."""
    if annotations is None:
        return False
    return bool(getattr(annotations, "read_only_hint", False)) and not bool(
        getattr(annotations, "destructive_hint", False)
    )


def _reuse(http: httpx2.AsyncClient) -> McpHttpClientFactory:
    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
    ) -> httpx2.AsyncClient:
        return http

    return factory


def _transport(kind: str, url: str, http: httpx2.AsyncClient) -> AbstractAsyncContextManager[Any]:
    if kind == STREAMABLE:
        return streamable_http_client(url, http_client=http)
    return sse_client(
        url,
        headers=dict(http.headers),
        httpx_client_factory=_reuse(http),
    )


async def _read(
    client: Client, description_max: int
) -> tuple[str | None, str | None, list[ToolInfo]]:
    info = client.server_info
    tools: list[ToolInfo] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor) if cursor else await client.list_tools()
        for tool in page.tools:
            tools.append(
                ToolInfo(
                    name=_cut(tool.name, 200),
                    title=_cut(tool.title, 200) or None,
                    description=_cut(tool.description, description_max),
                    input_schema=dict(tool.input_schema or {}),
                    reads_only=classify(tool.annotations),
                )
            )
        cursor = page.next_cursor
        if not cursor:
            break
    return (
        _cut(getattr(info, "name", None), 200) or None,
        _cut(getattr(info, "version", None), 100) or None,
        tools,
    )


async def probe(
    url: str,
    headers: dict[str, str],
    *,
    private_allowed: bool,
    seconds: float,
    description_max: int,
    transport: str | None = None,
) -> Probe:
    """CON-9, CON-12: connect, read the server's name and its tools. Streamable HTTP first,
    then HTTP with server-sent events for servers that only speak that."""
    tried = [transport] if transport else [STREAMABLE, SSE]
    reasons: list[str] = []
    for kind in tried:
        http = client_factory[0](headers, private_allowed, seconds)
        statuses = _Statuses()
        http.event_hooks["response"].append(statuses.seen)
        try:
            # The SSE transport opens the client itself; the streamable one is given it open.
            async with contextlib.AsyncExitStack() as stack:
                if kind == STREAMABLE:
                    await stack.enter_async_context(http)
                client = await stack.enter_async_context(
                    Client(_transport(kind, url, http), read_timeout_seconds=seconds)
                )
                name, version, tools = await asyncio.wait_for(
                    _read(client, description_max), seconds
                )
                return Probe(kind, name, version, tools)
        except Unreachable:
            raise
        except TimeoutError:
            reasons.append(f"it did not answer within {int(seconds)} seconds")
        except Exception as error:  # the transports raise many kinds; each is one plain reason
            refused = [status for status in statuses if status in (401, 403)]
            if refused:
                raise Unreachable(
                    f"it refused the sign-in (HTTP {refused[0]})", refused=True
                ) from None
            reasons.append(_reason(error))
        finally:
            await http.aclose()
    raise Unreachable(reasons[0] if reasons else "it did not answer as an MCP server")


class _Statuses(list[int]):
    """The status of every answer a probe received, to tell a refused sign-in apart."""

    async def seen(self, response: httpx2.Response) -> None:
        self.append(int(response.status_code))


def _reason(error: BaseException) -> str:
    """One plain sentence from whatever went wrong, without a header or token in it."""
    while True:
        inner: list[BaseException] = list(getattr(error, "exceptions", ()) or ())
        if not inner:
            break
        error = inner[0]
    if isinstance(error, Unreachable):
        return str(error)
    if isinstance(error, httpx2.HTTPStatusError):
        status = int(error.response.status_code)
        if status in (401, 403):
            return f"it refused the sign-in (HTTP {status})"
        return f"it answered HTTP {status}"
    if isinstance(error, httpx2.ConnectError):
        return "it could not be reached"
    kind = str(getattr(type(error), "__name__", "error"))
    return f"it did not answer as an MCP server ({kind})"
