"""A local web site for the egress proxy's tests: HTTPS for several host names with its own
certificate authority, and plain HTTP. Each answer echoes what the site received."""

from __future__ import annotations

import asyncio
import contextlib
import json
import ssl
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import h11

from crewmind.domain.connections.authority import Authority

HOSTS = ("wp.test", "other.test")


def server_context(authority: Authority, host: str) -> ssl.SSLContext:
    certificate, key = authority.leaf(host, timedelta(hours=1))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    with tempfile.TemporaryDirectory() as directory:
        pem = Path(directory) / "leaf.pem"
        pem.write_bytes(certificate + key)
        context.load_cert_chain(pem)
    return context


def trusting(*authorities: Authority) -> ssl.SSLContext:
    context = ssl.create_default_context(
        cadata="\n".join(a.certificate_pem.decode() for a in authorities)
    )
    return context


class Site:
    """Echoes each request as JSON: its target, headers and body length. Keeps connections
    alive between requests."""

    def __init__(self) -> None:
        self.authority = Authority.create("test site authority")
        self.received: list[dict[str, Any]] = []
        self.https_port = 0
        self.http_port = 0
        self._servers: list[asyncio.Server] = []

    async def start(self) -> None:
        contexts = {host: server_context(self.authority, host) for host in HOSTS}
        default = contexts[HOSTS[0]]

        def choose(sock: ssl.SSLObject, name: str | None, _: ssl.SSLContext) -> None:
            if name in contexts:
                sock.context = contexts[name]

        default.sni_callback = choose  # pyright: ignore[reportAttributeAccessIssue]
        secure = await asyncio.start_server(self._handle, "127.0.0.1", 0, ssl=default)
        plain = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self._servers = [secure, plain]
        self.https_port = secure.sockets[0].getsockname()[1]
        self.http_port = plain.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for server in self._servers:
            server.close()
            with contextlib.suppress(Exception):
                await server.wait_closed()

    async def connect(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """What the proxy uses in place of DNS: every test host is this site."""
        if host not in HOSTS:
            raise OSError(f"no test host {host}")
        return await asyncio.open_connection(
            "127.0.0.1", self.https_port if port == 443 else self.http_port
        )

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection = h11.Connection(h11.SERVER)
        try:
            while True:
                request: Any = None
                size = 0
                while True:
                    event = connection.next_event()
                    if event is h11.NEED_DATA:
                        connection.receive_data(await reader.read(65536))
                        continue
                    if isinstance(event, h11.Request):
                        request = event
                    elif isinstance(event, h11.Data):
                        size += len(event.data)
                    elif isinstance(event, h11.EndOfMessage):
                        break
                    elif isinstance(event, h11.ConnectionClosed) or event is h11.PAUSED:
                        return
                seen = {
                    "target": request.target.decode(),
                    "headers": {name.decode(): value.decode() for name, value in request.headers},
                    "body": size,
                }
                self.received.append(seen)
                body = json.dumps(seen).encode()
                writer.write(
                    connection.send(
                        h11.Response(
                            status_code=200,
                            headers=[
                                (b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                            ],
                        )
                    )
                    or b""
                )
                writer.write(connection.send(h11.Data(data=body)) or b"")
                writer.write(connection.send(h11.EndOfMessage()) or b"")
                await writer.drain()
                if connection.our_state is h11.MUST_CLOSE:
                    return
                connection.start_next_cycle()
        except (ConnectionError, h11.ProtocolError, ssl.SSLError):
            return
        finally:
            with contextlib.suppress(Exception):
                writer.close()
