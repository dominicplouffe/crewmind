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

CHECK_SECONDS_LIMIT = 300  # WRK-7: the lesser of `run.timeout` and 300 seconds
CHECK_MEMORY_BYTES = 1024**3  # WRK-7: 1 GB
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


def prepare_copy(workspace: Path, pinned: dict[str, bytes]) -> Path:
    """A fresh directory holding the workspace with the pinned test files restored."""
    scratch = Path(tempfile.mkdtemp(prefix="task-check-"))
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
    """Runs a check in a fresh container with no network, 1 CPU and 1 GB (WRK-7). Written
    for the container sandbox mode; not yet run against a real Docker daemon."""

    mode = "container"

    def __init__(self, image: str) -> None:
        self._image = image

    async def run(
        self, workspace: Path, command: str, pinned: dict[str, bytes], seconds: int
    ) -> CheckResult:
        if not command.strip():
            return CheckResult(False, "The check command is empty.")
        seconds = min(seconds, CHECK_SECONDS_LIMIT)
        directory = await asyncio.to_thread(prepare_copy, workspace, pinned)

        def run() -> CheckResult:
            import importlib
            from typing import Any

            docker: Any = importlib.import_module("docker")
            client = docker.from_env()
            container = client.containers.run(
                self._image,
                ["/bin/sh", "-c", command],
                working_dir="/workspace",
                volumes={str(directory): {"bind": "/workspace", "mode": "rw"}},
                environment=check_environment(Path("/workspace")),
                network_disabled=True,
                nano_cpus=1_000_000_000,
                mem_limit=CHECK_MEMORY_BYTES,
                detach=True,
            )
            try:
                result = container.wait(timeout=seconds)
                text = container.logs().decode("utf-8", errors="replace")
                code = int(result.get("StatusCode", 1))
                return CheckResult(code == 0, _tail(f"exit {code}\n{text}"))
            except Exception:
                return CheckResult(False, f"The check did not finish in {seconds} seconds.")
            finally:
                container.remove(force=True)

        try:
            return await asyncio.to_thread(run)
        finally:
            await asyncio.to_thread(shutil.rmtree, directory.parent, True)
