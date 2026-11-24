"""Every call the platform makes to a model provider, the search service or a push service
(P3, INT-8, CHAT-20).

Provider keys, the search key and the push signing value are used only here, in the
server. Tests replace these functions; nothing else in the code base reaches out.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

import httpx

from nightsquad.gateway.litellm_provider import call_model as call_model
from nightsquad.gateway.litellm_provider import model_library
from nightsquad.gateway.registry import ProviderInfo

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SEARCH_RESULTS = 8


async def list_models(
    provider: ProviderInfo, api_key: str | None, base_url: str | None
) -> list[str]:
    """The model ids a credential can reach, read from the provider (LLM-4)."""

    def read() -> list[str]:
        found: list[Any] = model_library().get_valid_models(
            check_provider_endpoint=True,
            custom_llm_provider=provider.prefix,
            api_key=api_key,
            api_base=base_url,
        )
        return [str(model).split("/", 1)[-1] for model in found]

    return await asyncio.to_thread(read)


async def brave_search(api_key: str, query: str) -> list[dict[str, Any]]:
    """One web search on the Brave Search API (INT-8). Results are untrusted input (P4)."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            BRAVE_URL,
            params={"q": query, "count": SEARCH_RESULTS},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
    response.raise_for_status()
    results = response.json().get("web", {}).get("results", [])
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        }
        for item in results
    ]


PUSH_HELD_SECONDS = 24 * 60 * 60  # CHAT-20: a push service holds an alarm for up to a day


async def web_push(
    subscription: dict[str, Any], payload: str, signing_value: str, sender: str
) -> bool:
    """Send one encrypted push to a browser's push service (CHAT-20). Returns False when
    the service says the subscription no longer exists."""
    pywebpush: Any = importlib.import_module("pywebpush")
    try:
        await pywebpush.webpush_async(
            subscription,
            data=payload,
            vapid_private_key=signing_value,
            vapid_claims={"sub": sender},
            ttl=PUSH_HELD_SECONDS,
        )
    except pywebpush.WebPushException as error:
        status = getattr(getattr(error, "response", None), "status", None)
        if status in (404, 410):
            return False
        raise
    return True
