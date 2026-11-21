"""What a harness sends the model gateway and gets back (LLM-1, LLM-8, LLM-9)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict[str, Any])


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])


class Turn(BaseModel):
    """One message of the conversation with the model."""

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    tool_call_id: str | None = None


class CompletionRequest(BaseModel):
    system: str
    messages: list[Turn]
    tools: list[ToolSpec] = Field(default_factory=list[ToolSpec])


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0


class CompletionResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    usage: TokenUsage = Field(default_factory=TokenUsage)
    run_tokens_used: int = 0
    run_tokens_cap: int | None = None
    warning: str | None = Field(default=None, description="Set at 80% of the run cap (GOV-6).")
