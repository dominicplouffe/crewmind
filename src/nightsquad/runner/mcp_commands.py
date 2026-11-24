"""MCP servers started from a command (CON-11).

Each runs in its own container: no workspace, no install secret, nothing of any agent's,
only the variables it was given, and it is reached over standard input and output by the
platform alone. It starts on first use, serves calls one at a time, and stops after
`mcp.command_idle` unused; a server that crashed starts afresh on the next call. Without a
container runtime it runs as a plain process, for development only, with a warning.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import struct
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from socket import SHUT_RDWR
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.message import SessionMessage
from mcp.types import jsonrpc_message_adapter

from nightsquad.domain.connections.mcp_client import CommandSpec
from nightsquad.runner.containers import INSTALL_LABEL, confinement, cpus_granted, docker_client

logger = logging.getLogger(__name__)

SERVER_LABEL = "nightsquad.mcp-server"
FRAME_HEADER = 8
"""Docker multiplexes a container's output in frames: one byte for the stream, three
padding bytes, and a four-byte big-endian length."""
STDOUT = 1
READ_CHUNK = 64 * 1024

Job = Callable[[Client], Awaitable[Any]]


def _message(line: str) -> SessionMessage | Exception:
    try:
        return SessionMessage(jsonrpc_message_adapter.validate_json(line, by_name=False))
    except ValueError as error:  # a server's stray line is reported to the session, not raised
        return error


@contextlib.asynccontextmanager
async def container_transport(
    spec: CommandSpec, default_image: str, install_id: str, cpus: float, memory_bytes: int
) -> AsyncGenerator[tuple[Any, Any]]:
    """The server's own container, reached over its attached standard input and output."""
    client = docker_client()
    container = await asyncio.to_thread(
        client.containers.create,
        spec.image or default_image,
        list(spec.argv),
        name=f"nightsquad-mcp-{spec.server_id[:12]}-{uuid.uuid4().hex[:6]}",
        stdin_open=True,
        tty=False,
        detach=True,
        environment=dict(spec.environment),
        labels={INSTALL_LABEL: install_id, SERVER_LABEL: spec.server_id},
        nano_cpus=cpus_granted(client, cpus),
        mem_limit=memory_bytes,
        **confinement(),
    )
    socket = await asyncio.to_thread(
        container.attach_socket, params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1}
    )
    raw = getattr(socket, "_sock", socket)
    raw.setblocking(False)
    await asyncio.to_thread(container.start)
    loop = asyncio.get_running_loop()
    read_writer, read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    write_stream, write_reader = anyio.create_memory_object_stream[SessionMessage](0)

    async def reader() -> None:
        buffer, text = b"", ""
        async with read_writer:
            while True:
                data = await loop.sock_recv(raw, READ_CHUNK)
                if not data:
                    return
                buffer += data
                while len(buffer) >= FRAME_HEADER:
                    kind, size = buffer[0], struct.unpack(">I", buffer[4:8])[0]
                    if len(buffer) < FRAME_HEADER + size:
                        break
                    frame, buffer = (
                        buffer[FRAME_HEADER : FRAME_HEADER + size],
                        buffer[FRAME_HEADER + size :],
                    )
                    if kind != STDOUT:
                        continue  # stderr is the server's own business, never shown to agents
                    lines = (text + frame.decode("utf-8", "replace")).split("\n")
                    text = lines.pop()
                    for line in lines:
                        if line.strip():
                            await read_writer.send(_message(line))

    async def writer() -> None:
        async with write_reader:
            async for message in write_reader:
                data = message.message.model_dump_json(by_alias=True, exclude_unset=True) + "\n"
                await loop.sock_sendall(raw, data.encode())

    try:
        async with anyio.create_task_group() as group:
            group.start_soon(reader)
            group.start_soon(writer)
            try:
                yield read_stream, write_stream
            finally:
                group.cancel_scope.cancel()
    finally:
        # Shut down rather than close: Docker's response object closes the socket itself
        # when it is collected, and fails if it was closed under it.
        with contextlib.suppress(Exception):
            raw.shutdown(SHUT_RDWR)
        with contextlib.suppress(Exception):
            await asyncio.to_thread(container.remove, force=True)
        with contextlib.suppress(Exception):
            socket.close()
        with contextlib.suppress(Exception):
            client.close()


def process_transport(spec: CommandSpec) -> contextlib.AbstractAsyncContextManager[Any]:
    """Development only: a plain process with only its own variables and a PATH."""
    environment = {"PATH": os.environ.get("PATH", os.defpath), **spec.environment}
    return stdio_client(
        StdioServerParameters(command=spec.argv[0], args=list(spec.argv[1:]), env=environment)
    )


@dataclass
class _Live:
    spec: CommandSpec
    jobs: asyncio.Queue[tuple[Job, asyncio.Future[Any]]] = field(
        default_factory=lambda: asyncio.Queue[tuple[Job, asyncio.Future[Any]]]()
    )
    task: asyncio.Task[None] | None = None


class CommandPool:
    """Keeps each command server running while it is used (CON-11)."""

    def __init__(
        self,
        *,
        containers: bool,
        idle_seconds: Callable[[], Awaitable[float]],
        default_image: str,
        install_id: str,
        cpus: float,
        memory_bytes: int,
    ) -> None:
        self.containers = containers
        self._idle = idle_seconds
        self._image, self._install = default_image, install_id
        self._cpus, self._memory = cpus, memory_bytes
        self._live: dict[str, _Live] = {}
        if not containers:
            logger.warning(
                "MCP command servers run as plain processes on this host, for development "
                "only: they are not isolated from it (CON-11)"
            )

    def _transport(self, spec: CommandSpec) -> contextlib.AbstractAsyncContextManager[Any]:
        if self.containers:
            return container_transport(spec, self._image, self._install, self._cpus, self._memory)
        return process_transport(spec)

    async def run(self, spec: CommandSpec, job: Job, seconds: float) -> Any:
        live = self._live.get(spec.server_id)
        if live is not None and (live.spec != spec or live.task is None or live.task.done()):
            await self.stop(spec.server_id)
            live = None
        if live is None:
            live = _Live(spec)
            live.task = asyncio.create_task(self._serve(live))
            self._live[spec.server_id] = live
        done: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await live.jobs.put((job, done))
        return await asyncio.wait_for(done, seconds)

    async def _serve(self, live: _Live) -> None:
        """One server: started, then its jobs one at a time, until idle or broken."""
        pending: tuple[Job, asyncio.Future[Any]] | None = None
        try:
            async with Client(self._transport(live.spec)) as client:
                while True:
                    idle = await self._idle()
                    try:
                        pending = await asyncio.wait_for(live.jobs.get(), idle)
                    except TimeoutError:
                        return  # unused for mcp.command_idle: stop
                    job, done = pending
                    try:
                        done.set_result(await job(client))
                    except Exception as error:
                        if not done.done():
                            done.set_exception(error)
                    pending = None
        except Exception as error:
            logger.info(
                "mcp command server %s stopped: %s", live.spec.server_id, type(error).__name__
            )
            if pending is not None and not pending[1].done():
                pending[1].set_exception(error)
            while not live.jobs.empty():
                _, waiting = live.jobs.get_nowait()
                if not waiting.done():
                    waiting.set_exception(error)
        finally:
            if self._live.get(live.spec.server_id) is live:
                self._live.pop(live.spec.server_id, None)

    async def stop(self, server_id: str) -> None:
        live = self._live.pop(server_id, None)
        if live is not None and live.task is not None:
            live.task.cancel()
            with contextlib.suppress(BaseException):
                await live.task

    async def close(self) -> None:
        for server_id in list(self._live):
            await self.stop(server_id)

    def running(self) -> list[str]:
        return list(self._live)
