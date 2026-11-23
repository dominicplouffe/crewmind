"""Running a platform check: a task's pinned command, in a fresh copy of the workspace, with
no model, no credentials and no tokens (WRK-7, INV-2, P5).

The check never runs in the workspace itself. The workspace is copied, the pinned test
files are put back as they were when the task was created, and the command runs there.
So nothing the claimant edited can weaken the test, and the check cannot change the work.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import resource
import shutil
import signal
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from crewmind.runner.containers import (
    CONTAINER_PATH,
    INSTALL_LABEL,
    WORKSPACE,
    confinement,
    cpus_granted,
    docker_client,
    hand_over,
)

CHECK_SECONDS_LIMIT = 300  # WRK-7: the lesser of `run.timeout` and 300 seconds
CHECK_MEMORY_BYTES = 1024**3  # WRK-7: 1 GB
CHECK_CPUS = 1  # WRK-7: 1 CPU
OUTPUT_TAIL_CHARACTERS = 4000  # WRK-7: the platform keeps the tail of the output


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    output: str


class CheckRunner(Protocol):
    mode: str

    async def run(
        self, workspace: Path, command: str, pinned: dict[str, bytes], seconds: int
    ) -> CheckResult: ...


def check_environment(home: Path) -> dict[str, str]:
    """Everything a check is given. No token, no key, no address of the server (WRK-7)."""
    return {"PATH": os.defpath, "HOME": str(home), "LANG": "C.UTF-8"}


def _tail(text: str) -> str:
    return text[-OUTPUT_TAIL_CHARACTERS:]


def prepare_copy(workspace: Path, pinned: dict[str, bytes], root: Path | None = None) -> Path:
    """A fresh directory holding the workspace with the pinned test files restored. It is
    made under `root` when given, else in the system's temporary directory."""
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="task-check-", dir=root))
    target = scratch / "workspace"
    if workspace.is_dir():
        shutil.copytree(workspace, target, symlinks=True)
    else:
        target.mkdir()
    for name, content in pinned.items():
        file = (target / name).resolve()
        if target.resolve() not in file.parents:
            continue
        file.parent.mkdir(parents=True, exist_ok=True)
        if file.exists():
            file.chmod(0o644)
        file.write_bytes(content)
    return target


class ProcessCheckRunner:
    """Runs a check as a process of the server's user, in a clean environment with a memory
    limit and a timeout. It isolates no more than the unisolated sandbox does (EXE-12)."""

    mode = "unisolated"

    async def run(
        self, workspace: Path, command: str, pinned: dict[str, bytes], seconds: int
    ) -> CheckResult:
        if not command.strip():
            return CheckResult(False, "The check command is empty.")
        seconds = min(seconds, CHECK_SECONDS_LIMIT)
        directory = await asyncio.to_thread(prepare_copy, workspace, pinned)

        def limit() -> None:
            os.setsid()
            resource.setrlimit(resource.RLIMIT_AS, (CHECK_MEMORY_BYTES, CHECK_MEMORY_BYTES))
            resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))

        try:
            process = await asyncio.create_subprocess_exec(
                "/bin/sh",
                "-c",
                command,
                cwd=directory,
                env=check_environment(directory),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                preexec_fn=limit,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=seconds)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
                return CheckResult(False, f"The check did not finish in {seconds} seconds.")
            text = output.decode("utf-8", errors="replace")
            return CheckResult(process.returncode == 0, _tail(f"exit {process.returncode}\n{text}"))
        finally:
            await asyncio.to_thread(shutil.rmtree, directory.parent, True)


class ContainerCheckRunner:
    """Runs a check in a fresh container with no network, 1 CPU and 1 GB (WRK-7), as an
    unprivileged user with no capabilities (EXE-12). The copy of the workspace is made
    under `scratch`, which the container runtime must see at the same path."""

    mode = "container"

    def __init__(self, image: str, scratch: Path, install_id: str) -> None:
        self._image = image
        self._scratch = scratch
        self._install_id = install_id

    async def run(
        self, workspace: Path, command: str, pinned: dict[str, bytes], seconds: int
    ) -> CheckResult:
        if not command.strip():
            return CheckResult(False, "The check command is empty.")
        seconds = min(seconds, CHECK_SECONDS_LIMIT)
        directory = await asyncio.to_thread(prepare_copy, workspace, pinned, self._scratch)

        def run() -> CheckResult:
            hand_over(directory)
            client = docker_client()
            container = client.containers.run(
                self._image,
                ["/bin/sh", "-c", command],
                detach=True,
                init=True,
                working_dir=WORKSPACE,
                volumes={str(directory): {"bind": WORKSPACE, "mode": "rw"}},
                environment={**check_environment(Path(WORKSPACE)), "PATH": CONTAINER_PATH},
                network_disabled=True,
                nano_cpus=cpus_granted(client, CHECK_CPUS),
                mem_limit=CHECK_MEMORY_BYTES,
                memswap_limit=CHECK_MEMORY_BYTES,
                labels={INSTALL_LABEL: self._install_id},
                **confinement(),
            )
            try:
                try:
                    result = container.wait(timeout=seconds)
                except requests.exceptions.RequestException:
                    return CheckResult(False, f"The check did not finish in {seconds} seconds.")
                text = container.logs().decode("utf-8", errors="replace")
                code = int(result.get("StatusCode", 1))
                return CheckResult(code == 0, _tail(f"exit {code}\n{text}"))
            finally:
                container.remove(force=True)

        try:
            return await asyncio.to_thread(run)
        finally:
            await asyncio.to_thread(shutil.rmtree, directory.parent, True)
