"""The harness interface: what drives a model inside a sandbox (LLM-8).

A harness is transport only and never changes the rules. It reaches models only through the
model gateway with the run token (P3).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol


class Effort(StrEnum):
    """The one effort scale, translated per model by the gateway (LLM-5)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


@dataclass(frozen=True)
class HarnessCapabilities:
    """What a harness states about itself (LLM-8)."""

    withholds_tool_grants: bool
    holds_conversation: bool
    searches: bool
    takes_images: bool
    loads_skills: bool


@dataclass(frozen=True)
class RunLimits:
    """Limits passed to the harness. The gateway and the runner enforce them (GOV-6, EXE-7)."""

    max_tokens: int | None
    timeout_seconds: int


@dataclass(frozen=True)
class HarnessStart:
    """Everything a harness is started with (LLM-8)."""

    system_prompt: str
    context_pack: str
    tools: Sequence[str]
    effort: Effort
    limits: RunLimits


@dataclass(frozen=True)
class TextProduced:
    text: str


@dataclass(frozen=True)
class ToolCalled:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class Finished:
    reason: Literal["completed", "cancelled", "failed"]
    detail: str = ""


ProgressEvent = TextProduced | ToolCalled | Finished


class Harness(Protocol):
    """One interface for every harness (LLM-8): start, stream progress, honour cancellation."""

    @property
    def capabilities(self) -> HarnessCapabilities: ...

    def run(self, start: HarnessStart, cancel: asyncio.Event) -> AsyncIterator[ProgressEvent]:
        """Stream progress until a `Finished` event. Setting `cancel` ends the run promptly."""
        ...
