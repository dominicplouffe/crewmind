"""Sandboxes: where a run's harness executes (EXE-12, EXE-13, INV-6).

Three modes behind one interface. A sandbox is given the run token and the server's
address and nothing else: no provider key, no database address, no master key.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from crewmind.runner.agent import DONE, WARM_FLAG, Stop, agent_loop
from crewmind.runner.containers import (
    CONTAINER_PATH,
    INSTALL_LABEL,
    RUN_LABEL,
    WORKSPACE,
    confinement,
    docker_client,
    hand_over,
    host_of,
    own_container,
)


@dataclass(frozen=True)
class SandboxSpec:
    run_id: str
    project_id: str
    token: str
    api_url: str
    workspace: Path
    warm: tuple[str, int] | None = None
    """For a chat run: the agent and the generation of its chat session. A sandbox that
    keeps warm processes reuses one for the same pair (MSG-11)."""


class SandboxHandle(Protocol):
    async def wait(self) -> int:
        """Wait for the harness to end. 0 is a normal end."""
        ...

    async def kill(self) -> None: ...


class Sandbox(Protocol):
    mode: str

    async def start(self, spec: SandboxSpec) -> SandboxHandle: ...


def sandbox_environment(spec: SandboxSpec) -> dict[str, str]:
    """Everything a sandbox process is given. Built from nothing, never from the server's
    own environment, so no secret can ride along (INV-6, EXE-13)."""
    return {
        "CREWMIND_RUN_TOKEN": spec.token,
        "CREWMIND_AGENT_API": spec.api_url,
        "PATH": os.defpath,
        "HOME": str(spec.workspace),
        "LANG": "C.UTF-8",
    }


class _TaskHandle:
    def __init__(self, task: asyncio.Task[int]) -> None:
        self._task = task

    async def wait(self) -> int:
        try:
            return await self._task
        except asyncio.CancelledError:
            return 1

    async def kill(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task


class InProcessSandbox:
    """Runs the harness loop as a task in this process, against an in-process server.
    For tests only: it isolates nothing."""

    mode = "in-process"

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport = transport

    async def start(self, spec: SandboxSpec) -> SandboxHandle:
        async def run() -> int:
            headers = {"Authorization": f"Bearer {spec.token}"}
            async with httpx.AsyncClient(
                transport=self._transport, base_url=spec.api_url, headers=headers
            ) as client:
                try:
                    await agent_loop(client, spec.workspace)
                except Stop:
                    return 0
                except Exception:
                    return 1
            return 0

        return _TaskHandle(asyncio.create_task(run()))


class _ProcessHandle:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process

    async def wait(self) -> int:
        return await self._process.wait()

    async def kill(self) -> None:
        with contextlib.suppress(ProcessLookupError):
            self._process.kill()
        await self._process.wait()


class _WarmHandle:
    """One chat run handled by a warm process: the token goes in on standard input and
    the result comes back as a line."""

    def __init__(self, owner: UnisolatedSandbox, seat_id: str, process: asyncio.subprocess.Process):
        self._owner = owner
        self._seat_id = seat_id
        self._process = process

    async def wait(self) -> int:
        """The run's exit code. A process that was interrupted mid-answer is ended, so the
        next run never reads the answer to this one."""
        assert self._process.stdout is not None
        clean = False
        try:
            line = (await self._process.stdout.readline()).decode().strip()
            clean = line.startswith(DONE)
            return int(line.removeprefix(DONE)) if clean else 1
        finally:
            if not clean:
                await asyncio.shield(self._owner.end_warm(self._seat_id))
            self._owner.release(self._seat_id)

    async def kill(self) -> None:
        await self._owner.end_warm(self._seat_id)
        self._owner.release(self._seat_id)


class UnisolatedSandbox:
    """Development only (EXE-12): the harness is a process on the host, in the workspace
    directory, with a clean environment. It can read whatever the server's user can.

    A chat run reuses the agent's warm process while its chat session lasts (MSG-11)."""

    mode = "unisolated"

    def __init__(self) -> None:
        self._warm: dict[str, tuple[int, asyncio.subprocess.Process]] = {}
        self._answering: set[str] = set()

    async def _spawn(self, spec: SandboxSpec, *flags: str) -> asyncio.subprocess.Process:
        spec.workspace.mkdir(parents=True, exist_ok=True)
        piped = asyncio.subprocess.PIPE if flags else asyncio.subprocess.DEVNULL
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-m",
            "crewmind.runner.agent",
            *flags,
            cwd=spec.workspace,
            env={**sandbox_environment(spec), "PYTHONPATH": os.pathsep.join(sys.path)},
            stdin=piped,
            stdout=piped,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def start(self, spec: SandboxSpec) -> SandboxHandle:
        if spec.warm is None:
            return _ProcessHandle(await self._spawn(spec))
        seat_id, generation = spec.warm
        if seat_id in self._answering:
            # The agent's warm process is answering another run and takes one at a time,
            # so this run gets a process of its own.
            return _ProcessHandle(await self._spawn(spec))
        self._answering.add(seat_id)
        try:
            kept = self._warm.get(seat_id)
            if kept is None or kept[0] != generation or kept[1].returncode is not None:
                await self.end_warm(seat_id)
                kept = (generation, await self._spawn(spec, WARM_FLAG))
                self._warm[seat_id] = kept
            process = kept[1]
            assert process.stdin is not None
            process.stdin.write(f"{spec.token}\n".encode())
            await process.stdin.drain()
        except BaseException:
            self.release(seat_id)
            raise
        return _WarmHandle(self, seat_id, process)

    async def end_warm(self, seat_id: str) -> None:
        kept = self._warm.pop(seat_id, None)
        if kept is not None and kept[1].returncode is None:
            with contextlib.suppress(ProcessLookupError):
                kept[1].kill()
            await kept[1].wait()

    def release(self, seat_id: str) -> None:
        """The run that held this agent's warm process is over."""
        self._answering.discard(seat_id)

    async def keep_warm(self, seats: dict[str, int]) -> None:
        """End every warm process whose session has closed or moved to a new generation."""
        for seat_id, (generation, _) in list(self._warm.items()):
            if seats.get(seat_id) != generation:
                await self.end_warm(seat_id)

    @property
    def warm_processes(self) -> dict[str, int]:
        """Each agent with a live warm process, and that process's id."""
        return {
            seat: kept[1].pid for seat, kept in self._warm.items() if kept[1].returncode is None
        }


HARNESS_COMMAND = ("python", "-I", "-m", "crewmind.runner.agent")
"""What a sandbox container runs: the harness loop from the agent image (LLM-8)."""


class _ContainerHandle:
    def __init__(self, container: Any, release: Callable[[], None]) -> None:
        self._container = container
        self._release = release

    def _remove(self) -> None:
        with contextlib.suppress(Exception):
            self._container.remove(force=True)
        self._release()

    async def wait(self) -> int:
        result = await asyncio.to_thread(self._container.wait)
        await asyncio.to_thread(self._remove)
        return int(result.get("StatusCode", 1))

    async def kill(self) -> None:
        await asyncio.to_thread(self._remove)


class ContainerSandbox:
    """The required mode (EXE-12): a fresh, disposable container per run. It runs as an
    unprivileged user with no capabilities and no way to gain privileges, under CPU and
    memory limits, on a network of its project's own. An install label keeps a second
    install on the same host from adopting this one's containers.

    The container is given the workspace and nothing else of the host. It reaches the
    server at the agent API address. When the server is itself a container, the server
    joins each project's network under that address's host name, so a sandbox can reach
    it and no other project's sandbox."""

    mode = "container"

    def __init__(
        self,
        *,
        image: str,
        install_id: str,
        cpus: int,
        memory_bytes: int,
        command: Sequence[str] = HARNESS_COMMAND,
    ) -> None:
        self._docker: Any = docker_client()
        self._command = list(command)
        self._server: Any | None = own_container(self._docker)
        self._image = image
        self._install_id = install_id
        self._cpus = cpus
        self._memory = memory_bytes
        self._networks = threading.Lock()
        self.remove_leftovers()

    @property
    def _label(self) -> dict[str, str]:
        return {INSTALL_LABEL: self._install_id}

    def remove_leftovers(self) -> None:
        """Remove what an earlier server process of this install left behind. No run of
        this install is live when its server starts, so every such container is dead
        weight (EXE-7 reaps the runs themselves)."""
        mine = {"label": f"{INSTALL_LABEL}={self._install_id}"}
        for container in self._docker.containers.list(all=True, filters=mine):
            with contextlib.suppress(Exception):
                container.remove(force=True)
        for network in self._docker.networks.list(filters=mine):
            self._drop(network)

    def _network_name(self, project_id: str) -> str:
        return f"crewmind-{self._install_id}-{project_id}"

    def _find(self, name: str) -> Any | None:
        # Docker matches network names by substring, so the exact one is picked out here.
        return next((n for n in self._docker.networks.list(names=[name]) if n.name == name), None)

    def _join(self, project_id: str, api_url: str) -> str:
        """The project's own network (EXE-12), with the server on it if the server is a
        container. Called with the network lock held."""
        name = self._network_name(project_id)
        network = self._find(name) or self._docker.networks.create(name, labels=self._label)
        if self._server is not None:
            network.reload()
            if self._server.id not in network.attrs.get("Containers", {}):
                network.connect(self._server, aliases=[host_of(api_url)])
        return name

    def _drop(self, network: Any) -> None:
        with contextlib.suppress(Exception):
            if self._server is not None:
                network.disconnect(self._server, force=True)
        with contextlib.suppress(Exception):
            network.remove()

    def _leave(self, project_id: str) -> None:
        """Remove the project's network once no sandbox is on it. Docker has a small pool
        of network addresses, so an idle project does not keep one."""
        with self._networks:
            network = self._find(self._network_name(project_id))
            if network is None:
                return
            network.reload()
            server = self._server.id if self._server is not None else None
            if not set(network.attrs.get("Containers", {})) - {server}:
                self._drop(network)

    async def start(self, spec: SandboxSpec) -> SandboxHandle:
        spec.workspace.mkdir(parents=True, exist_ok=True)

        def run() -> Any:
            hand_over(spec.workspace)
            with self._networks:
                return self._docker.containers.run(
                    self._image,
                    self._command,
                    detach=True,
                    init=True,
                    environment={
                        **sandbox_environment(spec),
                        "HOME": WORKSPACE,
                        "PATH": CONTAINER_PATH,
                    },
                    working_dir=WORKSPACE,
                    volumes={str(spec.workspace): {"bind": WORKSPACE, "mode": "rw"}},
                    network=self._join(spec.project_id, spec.api_url),
                    nano_cpus=self._cpus * 1_000_000_000,
                    mem_limit=self._memory,
                    memswap_limit=self._memory,
                    labels={**self._label, RUN_LABEL: spec.run_id},
                    extra_hosts={"host.docker.internal": "host-gateway"},
                    **confinement(),
                )

        container = await asyncio.to_thread(run)
        return _ContainerHandle(container, lambda: self._leave(spec.project_id))
