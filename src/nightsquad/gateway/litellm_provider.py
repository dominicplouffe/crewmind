"""Model calls through LiteLLM, and the normalising of what providers report (LLM-1, LLM-9).

LiteLLM is used as a library inside the gateway (NFR-24). Providers report cache usage
differently; `normalise_usage` turns LiteLLM's unified usage into the four token kinds the
ledger records, so the budget counts non-cached tokens the same way everywhere (ADR-0003).
"""

from __future__ import annotations

import functools
import importlib
import json
from collections.abc import Callable
from typing import Any

from nightsquad.gateway.protocol import (
    CompletionRequest,
    CompletionResponse,
    TokenUsage,
    ToolCall,
)
from nightsquad.gateway.registry import Effort, ProviderInfo


@functools.cache
def model_library() -> Any:
    """LiteLLM, loaded on the first model call. Loading it takes seconds, so commands and
    sandboxes that make no model call never pay for it. It is loosely typed, so it is used
    through `Any` and its answers are read defensively."""
    library: Any = importlib.import_module("litellm")
    library.telemetry = False
    library.drop_params = True
    return library


AUTH_ERRORS = frozenset({"AuthenticationError", "PermissionDeniedError"})
TRANSIENT_ERRORS = frozenset(
    {
        "RateLimitError",
        "Timeout",
        "APIConnectionError",
        "InternalServerError",
        "ServiceUnavailableError",
    }
)


def _is_one_of(error: BaseException, names: frozenset[str]) -> bool:
    return any(base.__name__ in names for base in type(error).__mro__)


def is_auth_error(error: BaseException) -> bool:
    """LLM-11: the provider refused the credential itself."""
    return _is_one_of(error, AUTH_ERRORS)


def is_transient_error(error: BaseException) -> bool:
    """LLM-11: a failure that may pass, such as a rate limit or a timeout."""
    return _is_one_of(error, TRANSIENT_ERRORS) and not is_auth_error(error)


# LLM-5: one effort scale. `max` is sent as the highest level a provider accepts; a model
# without effort control ignores it (LiteLLM drops the parameter).
_EFFORT = {Effort.LOW: "low", Effort.MEDIUM: "medium", Effort.HIGH: "high", Effort.MAX: "high"}


def normalise_usage(usage: Any) -> TokenUsage:
    """LiteLLM reports `prompt_tokens` including cache reads and cache writes, with both
    broken out in `prompt_tokens_details`. Input here is what was read fresh."""
    if usage is None:
        return TokenUsage()
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    output = int(getattr(usage, "completion_tokens", 0) or 0)
    details = getattr(usage, "prompt_tokens_details", None)
    cache_read = int(getattr(details, "cached_tokens", 0) or 0)
    cache_write = int(
        getattr(details, "cache_write_tokens", 0)
        or getattr(details, "cache_creation_tokens", 0)
        or getattr(usage, "cache_creation_input_tokens", 0)
        or 0
    )
    return TokenUsage(
        input=max(prompt - cache_read - cache_write, 0),
        output=output,
        cache_write=cache_write,
        cache_read=cache_read,
    )


def to_messages(request: CompletionRequest) -> list[dict[str, Any]]:
    """The conversation in the OpenAI message shape LiteLLM takes."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}]
    for turn in request.messages:
        message: dict[str, Any] = {"role": turn.role, "content": turn.content}
        if turn.role == "assistant" and turn.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in turn.tool_calls
            ]
        if turn.role == "tool":
            message["tool_call_id"] = turn.tool_call_id
        messages.append(message)
    return messages


def to_tools(request: CompletionRequest) -> list[dict[str, Any]] | None:
    if not request.tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        }
        for tool in request.tools
    ]


def from_response(response: Any) -> CompletionResponse:
    message: Any = response.choices[0].message
    calls: list[ToolCall] = []
    requested: list[Any] = getattr(message, "tool_calls", None) or []
    for call in requested:
        arguments: dict[str, Any]
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
    return CompletionResponse(
        text=message.content or "",
        tool_calls=calls,
        usage=normalise_usage(getattr(response, "usage", None)),
    )


async def call_model(
    provider: ProviderInfo,
    request: CompletionRequest,
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    effort: str | None,
    on_delta: Callable[[str], None] | None = None,
) -> CompletionResponse:
    """One model call. The key is used here and nowhere else (P3). With `on_delta`, the
    reply is streamed and each piece of text is passed on as it arrives (IF-3.6)."""
    arguments: dict[str, Any] = {
        "model": f"{provider.prefix}/{model}",
        "messages": to_messages(request),
        "api_key": api_key,
    }
    tools = to_tools(request)
    if tools:
        arguments["tools"] = tools
    if base_url:
        arguments["api_base"] = base_url
    if effort:
        arguments["reasoning_effort"] = _EFFORT[Effort(effort)]
    if on_delta is None:
        return from_response(await model_library().acompletion(**arguments))
    stream = await model_library().acompletion(
        **arguments, stream=True, stream_options={"include_usage": True}
    )
    chunks: list[Any] = []
    async for chunk in stream:
        chunks.append(chunk)
        choices: list[Any] = getattr(chunk, "choices", None) or []
        text = getattr(getattr(choices[0], "delta", None), "content", None) if choices else None
        if text:
            on_delta(text)
    return from_response(
        model_library().stream_chunk_builder(chunks, messages=arguments["messages"])
    )
