"""What a harness sends the model gateway and gets back (LLM-1, LLM-8, LLM-9)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr


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
    input: int = Field(default=0, ge=0)
    output: int = Field(default=0, ge=0)
    cache_write: int = Field(default=0, ge=0)
    cache_read: int = Field(default=0, ge=0)


class HarnessReport(BaseModel):
    """What a command-line agent reports about its own model calls (LLM-8, LLM-9). Such an
    agent holds its login and calls its provider itself, so the gateway is told, not asked."""

    usage: TokenUsage | None = Field(default=None, description="Tokens since the last report.")
    text: str = Field(default="", description="What the model wrote since the last report.")
    failure: Literal["auth", "transient"] | None = Field(
        default=None, description="The provider refused the login, or is failing or out of plan."
    )
    detail: str = Field(default="", max_length=2000)
    login: SecretStr | None = Field(
        default=None, description="The login, when the agent renewed it during the run."
    )


class ReportOutcome(BaseModel):
    run_tokens_used: int
    run_tokens_cap: int | None
    stop: bool = Field(description="The run is at its cap: end the agent now (GOV-6).")
    reason: str = ""


class CompletionResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    usage: TokenUsage = Field(default_factory=TokenUsage)
    run_tokens_used: int = 0
    run_tokens_cap: int | None = None
    warning: str | None = Field(default=None, description="Set at 80% of the run cap (GOV-6).")
