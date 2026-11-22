"""Fetching a public page for the platform: the SSRF guard (WRK-12, EXE-14, P4).

Every URL the control plane fetches for an agent goes through here. Only public addresses
are reached. The address is checked at the moment of connecting, on every connection, so
a redirect or a changed DNS answer cannot lead inside. The body is capped and timed.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx

FETCH_SECONDS = 20  # WRK-12
FETCH_BYTES = 2 * 1024 * 1024  # WRK-12: a 2 MB cap
MAX_REDIRECTS = 5


class FetchRefused(Exception):
    """The guard will not fetch this, or the fetch failed. The message is plain words."""


def is_public(address: str) -> bool:
    """Whether an IP address is on the public internet: not private, loopback, link-local,
    reserved, multicast or unspecified."""
    return ipaddress.ip_address(address).is_global


async def _public_addresses(host: str, port: int) -> list[str]:
    try:
        found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise FetchRefused(f"the host {host} could not be found") from None
    addresses = [str(entry[4][0]) for entry in found]
    inside = [address for address in addresses if not is_public(address)]
    if inside or not addresses:
        raise FetchRefused(f"{host} is not a public address, so it is not fetched")
    return addresses


class _GuardedBackend(httpcore.AsyncNetworkBackend):
    """Connects only to an address that was just checked to be public."""

    def __init__(self) -> None:
        self._real: Any = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (the library's own signature)
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await _public_addresses(host, port)
        return await self._real.connect_tcp(
            addresses[0], port, timeout=timeout, local_address=local_address,
            socket_options=socket_options,
        )  # fmt: skip

    async def connect_unix_socket(self, *_: Any, **__: Any) -> httpcore.AsyncNetworkStream:
        raise FetchRefused("only public web addresses are fetched")

    async def sleep(self, seconds: float) -> None:
        await self._real.sleep(seconds)


def _client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport()
    # The transport's pool is replaced so that every connection passes the guard. httpx
    # offers no public way to supply a network backend.
    transport._pool = httpcore.AsyncConnectionPool(network_backend=_GuardedBackend())  # pyright: ignore[reportPrivateUsage]
    return httpx.AsyncClient(
        transport=transport, timeout=FETCH_SECONDS, follow_redirects=False, trust_env=False
    )


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchRefused("only http and https addresses are fetched")
    if parts.username or parts.password:
        raise FetchRefused("an address with a user name or password is not fetched")


async def fetch_public(url: str) -> bytes:
    """Fetch a public page: http(s) only, public addresses only, every redirect re-checked,
    20 seconds and 2 MB at most (WRK-12). Raises `FetchRefused` with the reason."""

    async def run() -> bytes:
        current = url
        async with _client() as client:
            for _ in range(MAX_REDIRECTS + 1):
                check_url(current)
                async with client.stream("GET", current) as response:
                    if response.is_redirect:
                        current = str(response.next_request.url) if response.next_request else ""
                        continue
                    if response.status_code >= 400:
                        raise FetchRefused(f"the page answered with status {response.status_code}")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > FETCH_BYTES:
                            raise FetchRefused("the page is larger than 2 MB")
                    return bytes(body)
        raise FetchRefused("the address redirected too many times")

    try:
        return await asyncio.wait_for(run(), timeout=FETCH_SECONDS)
    except TimeoutError:
        raise FetchRefused(f"the page did not answer within {FETCH_SECONDS} seconds") from None
    except (httpx.HTTPError, httpcore.ConnectError, OSError) as error:
        raise FetchRefused(f"the page could not be fetched ({type(error).__name__})") from None
