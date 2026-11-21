"""Every call the platform makes to a model provider or the search service (P3, INT-8).

Provider keys and the search key are used only here, in the server. Tests replace these
functions; nothing else in the code base reaches a provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from crewmind.gateway.litellm_provider import call_model as call_model
from crewmind.gateway.litellm_provider import litellm
from crewmind.gateway.registry import ProviderInfo

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SEARCH_RESULTS = 8


async def list_models(
    provider: ProviderInfo, api_key: str | None, base_url: str | None
) -> list[str]:
    """The model ids a credential can reach, read from the provider (LLM-4)."""

    def read() -> list[str]:
        found: list[Any] = litellm.get_valid_models(
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
