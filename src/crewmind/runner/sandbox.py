"""Sandboxes: where a run's harness executes (EXE-12, EXE-13, INV-6).

Three modes behind one interface. A sandbox is given the run token and the server's
address and nothing else: no provider key, no database address, no master key.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from crewmind.runner.agent import Stop, agent_loop


@dataclass(frozen=True)
class SandboxSpec:
    run_id: str
    project_id: str
    token: str
    api_url: str
    workspace: Path


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


class UnisolatedSandbox:
    """Development only (EXE-12): the harness is a process on the host, in the workspace
    directory, with a clean environment. It can read whatever the server's user can."""

    mode = "unisolated"

    async def start(self, spec: SandboxSpec) -> SandboxHandle:
        spec.workspace.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-m",
            "crewmind.runner.agent",
            cwd=spec.workspace,
            env={**sandbox_environment(spec), "PYTHONPATH": os.pathsep.join(sys.path)},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return _ProcessHandle(process)


class _ContainerHandle:
    def __init__(self, container: Any) -> None:
        self._container = container

    async def wait(self) -> int:
        result = await asyncio.to_thread(self._container.wait)
        await asyncio.to_thread(self._container.remove, force=True)
        return int(result.get("StatusCode", 1))

    async def kill(self) -> None:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._container.remove, force=True)


class ContainerSandbox:
    """The required mode (EXE-12): a fresh, disposable container per run, with no privilege
    escalation, CPU and memory limits, one network per project, and an install label so a
    second install on the same host never adopts another's containers."""

    mode = "container"

    def __init__(self, *, image: str, install_id: str, cpus: int, memory_bytes: int) -> None:
        import docker  # pyright: ignore[reportMissingTypeStubs]

        self._docker: Any = docker.from_env()
        self._image = image
        self._install_id = install_id
        self._cpus = cpus
        self._memory = memory_bytes

    def _network(self, project_id: str) -> str:
        name = f"crewmind-{self._install_id}-{project_id}"
        if not self._docker.networks.list(names=[name]):
            self._docker.networks.create(name, labels={"crewmind.install": self._install_id})
        return name

    async def start(self, spec: SandboxSpec) -> SandboxHandle:
        spec.workspace.mkdir(parents=True, exist_ok=True)

        def run() -> Any:
            return self._docker.containers.run(
                self._image,
                ["python", "-I", "-m", "crewmind.runner.agent"],
                detach=True,
                environment={**sandbox_environment(spec), "HOME": "/workspace"},
                working_dir="/workspace",
                volumes={str(spec.workspace): {"bind": "/workspace", "mode": "rw"}},
                network=self._network(spec.project_id),
                nano_cpus=self._cpus * 1_000_000_000,
                mem_limit=self._memory,
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],
                labels={"crewmind.install": self._install_id, "crewmind.run": spec.run_id},
                extra_hosts={"host.docker.internal": "host-gateway"},
            )

        return _ContainerHandle(await asyncio.to_thread(run))
