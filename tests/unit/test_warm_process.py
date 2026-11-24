"""A warm agent process answers one run at a time (MSG-11, EXE-8)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from nightsquad.runner import sandbox
from nightsquad.runner.sandbox import SandboxSpec, UnisolatedSandbox


class Pipe:
    def __init__(self) -> None:
        self.lines: asyncio.Queue[bytes] = asyncio.Queue()
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None

    async def readline(self) -> bytes:
        return await self.lines.get()


class Process:
    def __init__(self, flags: tuple[str, ...]) -> None:
        self.flags, self.returncode = flags, None
        self.stdin, self.stdout = Pipe(), Pipe()

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


async def test_MSG_11_a_warm_process_answers_one_run_at_a_time(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """MSG-11, EXE-8: a second chat run for an agent whose warm process is still answering
    gets a process of its own, so no run reads another's answer. Once the first run has
    answered, the warm process is used again. A run interrupted mid-answer ends the warm
    process, so its late answer is never read by the next run."""
    started: list[Process] = []

    async def spawn(self: UnisolatedSandbox, spec: SandboxSpec, *flags: str) -> Process:
        started.append(Process(flags))
        return started[-1]

    monkeypatch.setattr(UnisolatedSandbox, "_spawn", spawn)
    box = UnisolatedSandbox()

    def spec(run: str) -> SandboxSpec:
        return SandboxSpec(run, "p", f"token-{run}", "http://x", tmp_path, warm=("seat", 1))

    first = await box.start(spec("a"))
    second = await box.start(spec("b"))
    assert [process.flags for process in started] == [(sandbox.WARM_FLAG,), ()]
    assert started[0].stdin.written == [b"token-a\n"]
    assert isinstance(second, sandbox._ProcessHandle)  # pyright: ignore[reportPrivateUsage]

    started[0].stdout.lines.put_nowait(f"{sandbox.DONE}0\n".encode())
    assert await first.wait() == 0
    third = await box.start(spec("c"))
    assert len(started) == 2
    assert started[0].stdin.written == [b"token-a\n", b"token-c\n"]

    waiting = asyncio.create_task(third.wait())
    await asyncio.sleep(0)
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)
    assert started[0].returncode is not None
    await box.start(spec("d"))
    assert [process.flags for process in started][2:] == [(sandbox.WARM_FLAG,)]
