"""The egress proxy (CON-6, EXE-14, ADR-0010).

A run that has a secret sent for it reaches the web through this proxy, with its run token
as the proxy credential. For a connection to a site that has a secret sent for the run, the
proxy terminates TLS with a certificate from the install's authority, checks that the
connect target, the TLS server name and every request's `Host` agree, replaces any header
the agent set under that name with the secret, verifies the real site's certificate, and
relays the answer. Every other connection is relayed as an opaque tunnel: nothing in it is
read. A secret is never added to a plain HTTP request.

The proxy runs beside the control plane, so it reaches only public addresses: it must not
become a way into the host or its network (WRK-12). Each refusal says why, in plain words.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import socket
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import h11

from nightsquad.domain.connections.sending import Injection, RunSending
from nightsquad.domain.work.fetch import is_public

logger = logging.getLogger(__name__)

CHUNK = 64 * 1024
"""How much is read from a socket at a time."""
HTTPS_PORT = 443
HTTP_PORT = 80
REALM = 'Basic realm="Nightsquad egress"'
DROPPED = {b"proxy-authorization", b"proxy-connection"}


class Refused(Exception):
    """The proxy will not make this connection. The message is plain words for the agent."""


Connect = Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]
Sent = Callable[[str, Injection, str, str, int], Awaitable[None]]


async def guarded_connect(
    host: str, port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect only to an address that was just checked to be public (WRK-12)."""
    try:
        found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise Refused(f"the host {host} could not be found") from None
    addresses = [str(entry[4][0]) for entry in found]
    if not addresses or not all(is_public(address) for address in addresses):
        raise Refused(f"{host} is not a public address, so the proxy does not connect to it")
    return await asyncio.open_connection(addresses[0], port)


@dataclass
class ProxyHooks:
    """What the proxy needs from the platform, so it holds no rules of its own."""

    sending: Callable[[str | None], Awaitable[RunSending | None]]
    sent: Sent
    leaf: Callable[[str], ssl.SSLContext]
    upstream_tls: ssl.SSLContext
    idle_seconds: float
    connect: Connect = guarded_connect
    refused: Callable[[str, str], Awaitable[None]] | None = None
    """EXE-14: a refused connection is recorded in the run's trace (run id, reason)."""


def _token(request: h11.Request) -> str | None:
    for name, value in request.headers:
        if name == b"proxy-authorization" and value[:6].lower() == b"basic ":
            try:
                pair = base64.b64decode(value[6:].strip()).decode()
            except ValueError:
                return None
            return pair.partition(":")[2] or None
    return None


def _split_target(target: bytes, default_port: int) -> tuple[str, int]:
    host, _, port = target.decode("ascii", "replace").rpartition(":")
    if not host:
        return target.decode("ascii", "replace").lower(), default_port
    return host.strip("[]").lower(), int(port)


class _Stream:
    """One side of a connection, read through h11 with an idle limit."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        role: type[h11.CLIENT] | type[h11.SERVER],
        idle: float,
    ) -> None:
        self.reader, self.writer, self.idle = reader, writer, idle
        self.h11 = h11.Connection(role)

    async def next(self) -> h11.Event | type[h11.NEED_DATA] | type[h11.PAUSED]:
        while True:
            event = self.h11.next_event()
            if event is h11.NEED_DATA:
                data = await asyncio.wait_for(self.reader.read(CHUNK), self.idle)
                self.h11.receive_data(data)
                continue
            return event

    async def send(self, event: h11.Event) -> None:
        data: bytes | None = self.h11.send(event)
        if data:
            self.writer.write(data)
            await self.writer.drain()


async def _reply(
    writer: asyncio.StreamWriter, status: int, reason: str, text: str, extra: str = ""
) -> None:
    body = (text + "\n").encode()
    head = (
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n{extra}\r\n"
    )
    writer.write(head.encode() + body)
    with contextlib.suppress(ConnectionError):
        await writer.drain()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, idle: float) -> None:
    try:
        while True:
            data = await asyncio.wait_for(reader.read(CHUNK), idle)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, TimeoutError, asyncio.IncompleteReadError):
        pass
    finally:
        with contextlib.suppress(OSError, RuntimeError):
            if writer.can_write_eof():
                writer.write_eof()


async def _close(writer: asyncio.StreamWriter) -> None:
    with contextlib.suppress(Exception):
        writer.close()
        await writer.wait_closed()


class EgressProxy:
    def __init__(self, hooks: ProxyHooks) -> None:
        self.hooks = hooks
        self._server: asyncio.Server | None = None

    async def start(self, host: str, port: int) -> int:
        """Listen, and return the port listened on (port 0 picks a free one)."""
        self._server = await asyncio.start_server(self._handle, host, port)
        return int(self._server.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client = _Stream(reader, writer, h11.SERVER, self.hooks.idle_seconds)
        run: RunSending | None = None
        try:
            request = await client.next()
            if not isinstance(request, h11.Request):
                return
            run = await self.hooks.sending(_token(request))
            if run is None:
                await _reply(
                    writer, 407, "Proxy Authentication Required",
                    "This proxy is for Nightsquad runs. Use the run's own proxy address.",
                    f"Proxy-Authenticate: {REALM}\r\n",
                )  # fmt: skip
                return
            if request.method == b"CONNECT":
                await self._connect(client, request, run)
            else:
                await self._forward(client, request)
        except Refused as refused:
            logger.info("egress: refused a connection: %s", refused)
            if run is not None and self.hooks.refused is not None:
                await self.hooks.refused(run.run_id, str(refused))
            await _reply(
                writer, 403, "Forbidden", f"Nightsquad's egress proxy refused this: {refused}"
            )
        except (TimeoutError, ConnectionError, h11.ProtocolError, ssl.SSLError) as error:
            logger.info("egress: a connection ended: %s", type(error).__name__)
        except Exception:
            logger.exception("egress: a connection failed")
        finally:
            await _close(writer)

    async def _connect(self, client: _Stream, request: h11.Request, run: RunSending) -> None:
        host, port = _split_target(request.target, HTTPS_PORT)
        injection = run.by_site.get(host)
        leftover, _ = client.h11.trailing_data
        if injection is None or port != HTTPS_PORT:
            await self._tunnel(client, host, port, leftover)
            return
        if leftover:
            raise Refused("the client sent data before the tunnel was open")
        client.writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await client.writer.drain()
        await client.writer.start_tls(self.hooks.leaf(host))
        await self._inject(client, host, injection, run.run_id)

    async def _tunnel(self, client: _Stream, host: str, port: int, leftover: bytes) -> None:
        """An opaque tunnel: nothing in it is read (CON-6)."""
        upstream_reader, upstream_writer = await self._open(host, port)
        client.writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await client.writer.drain()
        if leftover:
            upstream_writer.write(leftover)
        try:
            await asyncio.gather(
                _pipe(client.reader, upstream_writer, self.hooks.idle_seconds),
                _pipe(upstream_reader, client.writer, self.hooks.idle_seconds),
            )
        finally:
            await _close(upstream_writer)

    async def _open(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            return await self.hooks.connect(host, port)
        except Refused:
            raise
        except OSError as error:
            raise Refused(f"{host} could not be reached ({type(error).__name__})") from None

    async def _inject(self, client: _Stream, host: str, injection: Injection, run_id: str) -> None:
        """CON-6: the requests inside a granted site's tunnel, one after another."""
        client.h11 = h11.Connection(h11.SERVER)
        upstream: _Stream | None = None
        try:
            while True:
                request = await client.next()
                if not isinstance(request, h11.Request):
                    return
                refusal = self._check(request, host)
                if refusal is not None:
                    status, reason, text = refusal
                    await client.send(
                        h11.Response(
                            status_code=status, reason=reason,
                            headers=[(b"content-type", b"text/plain"), (b"connection", b"close")],
                        )
                    )  # fmt: skip
                    await client.send(h11.Data(data=(text + "\n").encode()))
                    await client.send(h11.EndOfMessage())
                    return
                if upstream is None:
                    reader, writer = await self._open(host, HTTPS_PORT)
                    await writer.start_tls(self.hooks.upstream_tls, server_hostname=host)
                    upstream = _Stream(reader, writer, h11.CLIENT, self.hooks.idle_seconds)
                status = await self._exchange(client, upstream, request, injection)
                path = request.target.decode("ascii", "replace")
                await self.hooks.sent(run_id, injection, request.method.decode(), path, status)
                if (
                    client.h11.our_state is h11.MUST_CLOSE
                    or upstream.h11.our_state is h11.MUST_CLOSE
                ):
                    return
                if client.h11.our_state is not h11.DONE or upstream.h11.their_state is not h11.DONE:
                    return
                client.h11.start_next_cycle()
                upstream.h11.start_next_cycle()
        finally:
            if upstream is not None:
                await _close(upstream.writer)

    @staticmethod
    def _check(request: h11.Request, host: str) -> tuple[int, str, str] | None:
        named = {name: value for name, value in request.headers}
        wanted = named.get(b"host", b"").decode("ascii", "replace").lower()
        if wanted not in (host, f"{host}:{HTTPS_PORT}"):
            return 421, "Misdirected Request", f"This connection is for {host} only."
        if b"upgrade" in named:
            return 501, "Not Implemented", "Upgrades are not relayed on a site with a secret."
        return None

    async def _exchange(
        self, client: _Stream, upstream: _Stream, request: h11.Request, injection: Injection
    ) -> int:
        """One request with the secret's header, and its answer, streamed both ways."""
        header = injection.header.lower().encode()
        headers = [
            (name, value)
            for name, value in request.headers
            if name not in DROPPED and name != header and name != b"expect"
        ]
        headers.append((injection.header.encode(), injection.value.encode()))
        if client.h11.they_are_waiting_for_100_continue:
            await client.send(h11.InformationalResponse(status_code=100, headers=[]))
        await upstream.send(
            h11.Request(method=request.method, target=request.target, headers=headers)
        )
        while True:
            event = await client.next()
            if isinstance(event, h11.Data):
                await upstream.send(event)
            elif isinstance(event, h11.EndOfMessage):
                await upstream.send(event)
                break
            else:
                raise ConnectionError("the client went away mid-request")
        while True:
            event = await upstream.next()
            if isinstance(event, h11.InformationalResponse):
                continue
            if isinstance(event, h11.Response):
                await client.send(
                    h11.Response(
                        status_code=event.status_code, reason=event.reason, headers=event.headers
                    )
                )
                status = event.status_code
                break
            raise ConnectionError("the site closed the connection without an answer")
        while True:
            event = await upstream.next()
            if isinstance(event, h11.Data):
                await client.send(event)
            elif isinstance(event, h11.EndOfMessage):
                await client.send(event)
                return status
            else:
                raise ConnectionError("the site closed the connection mid-answer")

    async def _forward(self, client: _Stream, request: h11.Request) -> None:
        """A plain HTTP request: relayed unchanged, never with a secret."""
        url = urlsplit(request.target.decode("ascii", "replace"))
        if url.scheme != "http" or not url.hostname:
            raise Refused("only absolute http:// requests and CONNECT are relayed")
        reader, writer = await self._open(url.hostname, url.port or HTTP_PORT)
        upstream = _Stream(reader, writer, h11.CLIENT, self.hooks.idle_seconds)
        target = (url.path or "/") + (f"?{url.query}" if url.query else "")
        headers = [
            (name, value)
            for name, value in request.headers
            if name not in DROPPED and name != b"connection"
        ]
        headers.append((b"connection", b"close"))
        try:
            await upstream.send(h11.Request(method=request.method, target=target, headers=headers))
            while True:
                event = await client.next()
                if isinstance(event, h11.Data):
                    await upstream.send(event)
                elif isinstance(event, h11.EndOfMessage):
                    await upstream.send(event)
                    break
                else:
                    return
            await _pipe(reader, client.writer, self.hooks.idle_seconds)
        finally:
            await _close(writer)
