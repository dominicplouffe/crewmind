"""The scripted mock harness, for tests and rehearsal (LLM-8, RHS-1).

It replays a fixed script. It calls no model, touches no network and spends no tokens.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from nightsquad.runner.harness.base import (
    Finished,
    HarnessCapabilities,
    HarnessStart,
    ProgressEvent,
    TextProduced,
    ToolCalled,
)

ScriptStep = TextProduced | ToolCalled


class MockHarness:
    """Replays `script` in order, then finishes. A tool call names a tool the start granted;
    calling any other tool fails the run, as a real harness that withholds grants would."""

    def __init__(self, script: Sequence[ScriptStep]) -> None:
        self._script = tuple(script)

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            withholds_tool_grants=True,
            holds_conversation=True,
            searches=False,
            takes_images=False,
            loads_skills=False,
        )

    async def run(self, start: HarnessStart, cancel: asyncio.Event) -> AsyncIterator[ProgressEvent]:
        for step in self._script:
            await asyncio.sleep(0)
            if cancel.is_set():
                yield Finished("cancelled")
                return
            if isinstance(step, ToolCalled) and step.name not in start.tools:
                yield Finished("failed", f"tool {step.name} is not granted")
                return
            yield step
        yield Finished("completed")
