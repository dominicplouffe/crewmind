"""The scripted mock provider, for tests and rehearsal (LLM-8, RHS-1).

It calls no model and no network. A script is a list of turns; each call of a run returns
the next turn, with the token usage the script declares, so metering and budgets are
exercised exactly as with a real provider.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from crewmind.gateway.protocol import CompletionRequest, CompletionResponse, TokenUsage, ToolCall


class ScriptedTurn(BaseModel):
    text: str = ""
    tools: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    usage: TokenUsage = Field(default_factory=lambda: TokenUsage(input=100, output=20))
    fail: str | None = Field(default=None, description="Raise this as a provider error.")
    word_delay_ms: int = Field(
        default=0, ge=0, description="Pause between streamed words, as a slow model would."
    )


DEFAULT_SCRIPT = [ScriptedTurn(text="Nothing to do.")]


class MockProviderError(RuntimeError):
    """A provider failure a script asked for."""


class MockProvider:
    """Scripts are looked up by `<seat name>/<run kind>`, then `<seat name>`, then `*`.
    They come from `scripts` (set by tests) or from JSON files of those names in a directory."""

    name = "mock"

    def __init__(self, script_dir: Path | None = None) -> None:
        self.scripts: dict[str, list[ScriptedTurn]] = {}
        self._script_dir = script_dir

    def script_for(self, seat_name: str, run_kind: str) -> list[ScriptedTurn]:
        for key in (f"{seat_name}/{run_kind}", seat_name, "*"):
            if key in self.scripts:
                return self.scripts[key]
            if self._script_dir is not None:
                path = self._script_dir / f"{key.replace('/', '.').replace('*', 'default')}.json"
                if path.exists():
                    turns = json.loads(path.read_text(encoding="utf-8"))
                    return [ScriptedTurn.model_validate(turn) for turn in turns]
        return DEFAULT_SCRIPT

    async def complete(
        self,
        request: CompletionRequest,
        *,
        seat_name: str,
        run_kind: str,
        calls_so_far: int,
        on_delta: Callable[[str], None] | None = None,
    ) -> CompletionResponse:
        script = self.script_for(seat_name, run_kind)
        if calls_so_far >= len(script):
            return CompletionResponse(text="Done.", usage=TokenUsage(input=50, output=5))
        turn = script[calls_so_far]
        if turn.fail is not None:
            raise MockProviderError(turn.fail)
        calls = [
            ToolCall(
                id=f"call_{calls_so_far}_{index}",
                name=tool["name"],
                arguments=tool.get("arguments", {}),
            )
            for index, tool in enumerate(turn.tools)
        ]
        if on_delta is not None:
            for word in re.findall(r"\S+\s*", turn.text):
                on_delta(word)
                if turn.word_delay_ms:
                    await asyncio.sleep(turn.word_delay_ms / 1000)
        return CompletionResponse(text=turn.text, tool_calls=calls, usage=turn.usage)
