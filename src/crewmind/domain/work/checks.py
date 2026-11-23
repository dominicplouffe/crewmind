"""Command tests: they must fail before the work, and they are pinned (WRK-5, INV-2).

When a task with a command test is created, the command and the contents of its test files
are pinned and the check is run once. A check that already passes is refused, because it
proves nothing. Every later check runs the pinned command against the pinned files.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crewmind.catalog.rules import Rule, rules
from crewmind.runner.check_sandbox import CheckResult, CheckRunner

WRK_5 = rules.register(Rule("WRK-5", "A command test must fail before any work is done."))
WRK_7 = rules.register(
    Rule("WRK-7", "A check runs with no model and no credentials; unsafe hosts refuse it.")
)

CANNOT_FAIL = ("true", ":", "exit 0")  # WRK-5: the fixed list, with a bare echo or printf
_BARE_PRINT = re.compile(r"^(echo|printf)\b[^;&|<>`$()]*$")
CONTAINER_SOCKETS = (Path("/var/run/docker.sock"), Path("/run/podman/podman.sock"))


def cannot_fail(command: str) -> bool:
    """WRK-5: commands that pass whatever the work is."""
    text = " ".join(command.split())
    return text in CANNOT_FAIL or bool(_BARE_PRINT.match(text))


def fingerprint(command: str, hashes: dict[str, str]) -> str:
    """What makes two command tests the same: the command and its test files' hashes."""
    parts = [" ".join(command.split()), *(f"{name}={hashes[name]}" for name in sorted(hashes))]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class Pinned:
    """A command test as pinned at creation: the files' contents, and the first run."""

    files: dict[str, bytes]
    missing: list[str]
    first_run: CheckResult | None

    @property
    def hashes(self) -> dict[str, str]:
        return {name: hashlib.sha256(content).hexdigest() for name, content in self.files.items()}


def read_test_files(workspace: Path, names: list[str]) -> tuple[dict[str, bytes], list[str]]:
    """The test files as they are now. A name outside the workspace is treated as missing."""
    files: dict[str, bytes] = {}
    missing: list[str] = []
    root = workspace.resolve()
    for name in names:
        file = (root / name).resolve()
        if root in file.parents and file.is_file():
            files[name] = file.read_bytes()
        else:
            missing.append(name)
    return files, missing


def unsafe_host(runner: CheckRunner, allowed: bool) -> bool:
    """WRK-7: on an unisolated host that holds a container-runtime socket, a check an agent
    wrote could drive that runtime, so it is refused unless the operator allows it."""
    return (
        runner.mode == "unisolated"
        and not allowed
        and any(socket.exists() for socket in CONTAINER_SOCKETS)
    )


async def pin_and_run(
    runner: CheckRunner, workspace: Path, command: str, names: list[str], seconds: int
) -> Pinned:
    """Pin the test files and run the check once on the current workspace (WRK-5). This
    runs with no database transaction open."""
    files, missing = read_test_files(workspace, names)
    if missing or cannot_fail(command) or not command.strip():
        return Pinned(files, missing, None)
    return Pinned(files, missing, await runner.run(workspace, command, files, seconds))


def changed_by_the_work(workspace: Path, test_files: dict[str, str]) -> list[str]:
    """The pinned test files whose contents in the workspace are no longer the pinned ones
    (WRK-5). The check puts each one back before it runs, so work done in one of them is
    never what the check sees."""
    changed: list[str] = []
    for name, pinned_hash in sorted(test_files.items()):
        file = workspace / name
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != pinned_hash:
            changed.append(name)
    return changed


def pinned_file_note(names: list[str]) -> str:
    """What the worker and the task's author are told when the work is in a pinned file."""
    listed = ", ".join(names)
    return (
        f"The check puts the pinned test files back before it runs, and the work changed "
        f"{listed}. Work done in a pinned test file is never seen by the check, so this task "
        "cannot pass as it is written. Its author must issue it again without pinning "
        f"{'that file' if len(names) == 1 else 'those files'}.\n"
    )


def stored(pinned: Pinned, blobs: Any) -> dict[str, str]:
    """Keep the pinned files' contents, by hash, so every later check can restore them."""
    return {name: blobs.put(content) for name, content in pinned.files.items()}


def restored(test_files: dict[str, str], blobs: Any) -> dict[str, bytes]:
    return {name: blobs.read(content_hash) for name, content_hash in test_files.items()}
