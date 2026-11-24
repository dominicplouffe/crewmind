"""The model gateway's provider side: usage normalisation and message shapes (LLM-1, LLM-9)."""

from __future__ import annotations

import importlib
from typing import Any

from nightsquad.gateway.litellm_provider import normalise_usage, to_messages, to_tools
from nightsquad.gateway.protocol import CompletionRequest, ToolCall, ToolSpec, Turn
from nightsquad.gateway.registry import ModelClass, nearest_class, pick_lineup, providers

AnthropicConfig: Any = importlib.import_module(
    "litellm.llms.anthropic.chat.transformation"
).AnthropicConfig
Usage: Any = importlib.import_module("litellm.types.utils").Usage


def test_LLM_9_anthropic_usage_is_split_into_fresh_input_cache_writes_and_cache_reads() -> None:
    """LLM-9, GOV-2, ADR-0003: Anthropic's own usage shape, passed through LiteLLM's real
    transformation, becomes the four token kinds. Cache reads are separate, so they can be
    left out of the budget."""
    reported = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 2_000,
        "cache_read_input_tokens": 30_000,
    }
    usage = AnthropicConfig().calculate_usage(usage_object=reported, reasoning_content=None)
    assert usage.prompt_tokens == 32_100
    normalised = normalise_usage(usage)
    assert normalised.model_dump() == {
        "input": 100,
        "output": 50,
        "cache_write": 2_000,
        "cache_read": 30_000,
    }


def test_LLM_9_openai_and_gemini_style_usage_subtracts_cached_tokens() -> None:
    """LLM-9: OpenAI and Gemini report prompt tokens with cached tokens inside them."""
    openai = Usage(
        prompt_tokens=1_500, completion_tokens=70, prompt_tokens_details={"cached_tokens": 1_024}
    )
    assert normalise_usage(openai).model_dump() == {
        "input": 476,
        "output": 70,
        "cache_write": 0,
        "cache_read": 1_024,
    }
    plain = Usage(prompt_tokens=10, completion_tokens=3)
    assert normalise_usage(plain).model_dump() == {
        "input": 10,
        "output": 3,
        "cache_write": 0,
        "cache_read": 0,
    }
    assert normalise_usage(None).input == 0


def test_LLM_8_the_conversation_reaches_the_provider_in_the_standard_shape() -> None:
    """LLM-8: tool calls and tool results keep their ids through the gateway."""
    request = CompletionRequest(
        system="Be brief.",
        messages=[
            Turn(role="user", content="go"),
            Turn(role="assistant", tool_calls=[ToolCall(id="c1", name="agent_whoami")]),
            Turn(role="tool", content='{"seat": "CEO"}', tool_call_id="c1"),
        ],
        tools=[ToolSpec(name="agent_whoami", description="Who you are.")],
    )
    messages = to_messages(request)
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "tool"]
    assert messages[2]["tool_calls"][0]["function"] == {"name": "agent_whoami", "arguments": "{}"}
    assert messages[3]["tool_call_id"] == "c1"
    tools = to_tools(request)
    assert tools is not None
    assert tools[0]["function"]["parameters"] == {"type": "object", "properties": {}}
    assert to_tools(CompletionRequest(system="s", messages=[])) is None


def test_LLM_1_the_provider_registry_is_data_and_covers_the_minimum_set() -> None:
    """LLM-1: the registry is data and lists every provider the spec requires."""
    required = {
        "anthropic",
        "openai",
        "gemini",
        "vertex_ai",
        "azure",
        "bedrock",
        "mistral",
        "deepseek",
        "openai_compatible",
    }
    assert required <= set(providers())
    assert providers()["openai_compatible"].needs_base_url


def test_LLM_4_lineups_take_the_newest_model_per_class_and_substitute_downward() -> None:
    """LLM-4, P12: the newest reachable model per class; an unknown model is left out; a
    missing class falls to the nearest one below, else above."""
    anthropic = providers()["anthropic"]
    lineup = pick_lineup(
        anthropic,
        ["claude-sonnet-4-5", "claude-sonnet-5-5", "claude-haiku-5-5", "text-embedding-9"],
    )
    assert lineup == {
        ModelClass.BALANCED: "claude-sonnet-5-5",
        ModelClass.FAST: "claude-haiku-5-5",
    }
    assert nearest_class(ModelClass.FRONTIER, set(lineup)) is ModelClass.BALANCED
    assert nearest_class(ModelClass.FAST, {ModelClass.FRONTIER}) is ModelClass.FRONTIER
    assert nearest_class(ModelClass.FAST, set()) is None
    assert pick_lineup(anthropic, []) == anthropic.default_lineup
