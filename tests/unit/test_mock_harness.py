"""The scripted mock harness (LLM-8, RHS-1)."""

from __future__ import annotations

import asyncio

from crewmind.runner.harness.base import (
    Effort,
    Finished,
    Harness,
    HarnessStart,
    ProgressEvent,
    RunLimits,
    TextProduced,
    ToolCalled,
)
from crewmind.runner.harness.mock import MockHarness

START = HarnessStart(
    system_prompt="You are a test agent.",
    context_pack="",
    tools=("tasks_claim",),
    effort=Effort.LOW,
    limits=RunLimits(max_tokens=None, timeout_seconds=60),
)


async def _collect(harness: Harness, cancel: asyncio.Event) -> list[ProgressEvent]:
    return [event async for event in harness.run(START, cancel)]


async def test_LLM_8_the_mock_replays_its_script_in_order() -> None:
    """LLM-8: the mock streams each scripted step, then finishes."""
    script = [TextProduced("reading the plan"), ToolCalled("tasks_claim", {"task": 1})]
    events = await _collect(MockHarness(script), asyncio.Event())
    assert events == [*script, Finished("completed")]


async def test_LLM_8_the_mock_honours_cancellation() -> None:
    """LLM-8, EXE-9: once cancelled, the harness stops before its next step."""
    cancel = asyncio.Event()
    harness = MockHarness([TextProduced("one"), TextProduced("two"), TextProduced("three")])
    events: list[ProgressEvent] = []
    async for event in harness.run(START, cancel):
        events.append(event)
        cancel.set()
    assert events == [TextProduced("one"), Finished("cancelled")]


async def test_LLM_8_the_mock_withholds_tools_that_were_not_granted() -> None:
    """LLM-8: a scripted call to a tool the start did not grant fails the run."""
    harness = MockHarness([ToolCalled("shell", {"command": "ls"})])
    assert harness.capabilities.withholds_tool_grants
    events = await _collect(harness, asyncio.Event())
    assert events == [Finished("failed", "tool shell is not granted")]
