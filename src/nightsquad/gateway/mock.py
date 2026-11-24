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
from typing import Any, cast

from pydantic import BaseModel, Field

from nightsquad.gateway.protocol import CompletionRequest, CompletionResponse, TokenUsage, ToolCall


class ScriptedTurn(BaseModel):
    text: str = ""
    tools: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    usage: TokenUsage = Field(default_factory=lambda: TokenUsage(input=100, output=20))
    fail: str | None = Field(default=None, description="Raise this as a provider error.")
    word_delay_ms: int = Field(
        default=0, ge=0, description="Pause between streamed words, as a slow model would."
    )
    delay_ms: int = Field(
        default=0, ge=0, description="Pause before answering, as thinking time would."
    )


DEFAULT_SCRIPT = [ScriptedTurn(text="Nothing to do.")]


class MockProviderError(RuntimeError):
    """A provider failure a script asked for."""


class MockProvider:
    """Scripts are looked up by `<seat name>/<run kind>`, then `<seat name>`, then `*`.
    They come from `scripts` (set by tests) or from JSON files of those names in a directory.

    A file holds a list of turns, replayed in every run. Or it holds
    `{"runs": [[...], [...]], "then": [...]}`: the first run of that seat and kind plays
    the first list, the second run the second, and every later run plays `then`."""

    name = "mock"

    def __init__(self, script_dir: Path | None = None) -> None:
        self.scripts: dict[str, list[ScriptedTurn]] = {}
        self._script_dir = script_dir
        self._runs_seen: dict[str, list[str]] = {}

    def script_for(
        self, seat_name: str, run_kind: str, run_id: str | None = None
    ) -> list[ScriptedTurn]:
        for key in (f"{seat_name}/{run_kind}", seat_name, "*"):
            if key in self.scripts:
                return self.scripts[key]
            if self._script_dir is not None:
                path = self._script_dir / f"{key.replace('/', '.').replace('*', 'default')}.json"
                if path.exists():
                    written = json.loads(path.read_text(encoding="utf-8"))
                    turns = self._turns_of_run(key, written, run_id)
                    return [ScriptedTurn.model_validate(turn) for turn in turns]
        return DEFAULT_SCRIPT

    def _turns_of_run(self, key: str, written: Any, run_id: str | None) -> list[Any]:
        """The turns this run plays: the whole list, or the list for its place in line."""
        if isinstance(written, list):
            return cast(list[Any], written)
        seen = self._runs_seen.setdefault(key, [])
        if run_id is not None and run_id not in seen:
            seen.append(run_id)
        place = seen.index(run_id) if run_id in seen else len(seen)
        runs: list[list[Any]] = written.get("runs", [])
        return runs[place] if place < len(runs) else written.get("then", [])

    def has_script(self, seat_name: str, run_kind: str) -> bool:
        """Whether a script was written for this caller, rather than the default."""
        return self.script_for(seat_name, run_kind) is not DEFAULT_SCRIPT

    async def complete(
        self,
        request: CompletionRequest,
        *,
        seat_name: str,
        run_kind: str,
        calls_so_far: int,
        on_delta: Callable[[str], None] | None = None,
        run_id: str | None = None,
    ) -> CompletionResponse:
        script = self.script_for(seat_name, run_kind, run_id)
        if calls_so_far >= len(script):
            return CompletionResponse(text="Done.", usage=TokenUsage(input=50, output=5))
        turn = script[calls_so_far]
        if turn.fail is not None:
            raise MockProviderError(turn.fail)
        if turn.delay_ms:
            await asyncio.sleep(turn.delay_ms / 1000)
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
