"""Recall memory behind one narrow interface: add, extract, search, update, forget, history
(MEM-2, MEM-3).

Two engines implement it. `Mem0Engine` is the product's: Mem0 as a library, storing in
pgvector on Postgres and in embedded Qdrant on SQLite, with a local ONNX embedder.
`InProcessEngine` keeps everything in memory and scores by shared words; tests and
rehearsals use it, so the default suite needs no model files. Only glue is written here.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import threading
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules

MEM_2 = rules.register(
    Rule("MEM-2", "Recall memory runs locally: the model is on disk and nothing is fetched.")
)

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384
COLLECTION = "nightsquad_memories"

ModelCall = Callable[[str, str], Coroutine[Any, Any, str]]
"""The platform's model call for extraction: (system, prompt) to the answer text. It goes
through the gateway, so it is metered and no key is held here (P3)."""


@dataclass(frozen=True)
class Recalled:
    """One remembered fact, as the engine returns it."""

    id: str
    scope: str
    text: str
    created_at: datetime
    updated_at: datetime
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict[str, Any])


class MemoryEngine(Protocol):
    async def add(self, scope: str, text: str, metadata: dict[str, Any]) -> str: ...

    async def extract(
        self, scope: str, messages: list[dict[str, str]], metadata: dict[str, Any], model: ModelCall
    ) -> list[str]: ...

    async def search(self, scopes: list[str], query: str, limit: int) -> list[Recalled]: ...

    async def listed(self, scope: str, limit: int) -> list[Recalled]: ...

    async def get(self, memory_id: str) -> Recalled | None: ...

    async def update(self, memory_id: str, text: str) -> None: ...

    async def forget(self, memory_id: str) -> None: ...

    async def forget_scope(self, scope: str) -> None: ...

    async def history(self, memory_id: str) -> list[dict[str, Any]]: ...


def parse_facts(answer: str) -> list[str]:
    """The facts in an extractor's answer: `{"memory": [{"text": ...}]}`. Anything else
    means nothing was extracted; a bad answer never raises."""
    found = re.search(r"\{.*\}", answer, re.DOTALL)
    try:
        parsed: Any = json.loads(found.group(0) if found else answer, strict=False)
    except ValueError:
        return []
    if not isinstance(parsed, dict):
        return []
    items: Any = cast(dict[str, Any], parsed).get("memory", [])
    if not isinstance(items, list):
        return []
    facts: list[str] = []
    for item in cast(list[Any], items):
        if isinstance(item, dict):
            text: Any = cast(dict[str, Any], item).get("text")
            if text:
                facts.append(str(text).strip())
    return facts


EXTRACT_SYSTEM = (
    "You extract durable facts from a team's work for its long-term memory: findings, the "
    "chairman's preferences, lessons and context that will still matter later. Skip "
    "greetings, status chatter and anything already in the existing memories. Keep any "
    "ILLUSTRATION — NOT DATA label with the fact it marks. Answer with JSON only: "
    '{"memory": [{"text": "one fact in one sentence"}]}. If nothing is worth keeping, '
    'answer {"memory": []}.'
)


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2}


class InProcessEngine:
    """Memories kept in this process and scored by shared words. For tests and rehearsals."""

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._rows: dict[str, Recalled] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}

    async def add(self, scope: str, text: str, metadata: dict[str, Any]) -> str:
        now = self._clock()
        memory_id = uuid.uuid4().hex
        self._rows[memory_id] = Recalled(memory_id, scope, text, now, now, metadata=dict(metadata))
        self._history[memory_id] = [{"event": "ADD", "text": text, "at": now.isoformat()}]
        return memory_id

    async def extract(
        self, scope: str, messages: list[dict[str, str]], metadata: dict[str, Any], model: ModelCall
    ) -> list[str]:
        known = "\n".join(f"- {row.text}" for row in await self.listed(scope, 50))
        said = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        answer = await model(
            EXTRACT_SYSTEM, f"## Existing memories\n{known or '(none)'}\n\n## New messages\n{said}"
        )
        return [await self.add(scope, fact, metadata) for fact in parse_facts(answer)]

    async def search(self, scopes: list[str], query: str, limit: int) -> list[Recalled]:
        wanted = _words(query)
        scored: list[Recalled] = []
        for row in self._rows.values():
            shared = wanted & _words(row.text)
            if row.scope in scopes and shared:
                score = len(shared) / (len(wanted) or 1)
                scored.append(replace(row, score=round(score, 3)))
        scored.sort(key=lambda row: (-row.score, row.created_at))
        return scored[:limit]

    async def listed(self, scope: str, limit: int) -> list[Recalled]:
        rows = [row for row in self._rows.values() if row.scope == scope]
        return sorted(rows, key=lambda row: row.created_at, reverse=True)[:limit]

    async def get(self, memory_id: str) -> Recalled | None:
        return self._rows.get(memory_id)

    async def update(self, memory_id: str, text: str) -> None:
        row = self._rows[memory_id]
        now = self._clock()
        self._rows[memory_id] = Recalled(
            row.id, row.scope, text, row.created_at, now, metadata=row.metadata
        )
        self._history[memory_id].append({"event": "UPDATE", "text": text, "at": now.isoformat()})

    async def forget(self, memory_id: str) -> None:
        self._rows.pop(memory_id, None)
        self._history.pop(memory_id, None)

    async def forget_scope(self, scope: str) -> None:
        for memory_id in [row.id for row in self._rows.values() if row.scope == scope]:
            await self.forget(memory_id)

    async def history(self, memory_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(memory_id, []))


def shipped_model_directory() -> Path:
    """Where the embedding model sits inside the package (MEM-2). It is added when the
    package or the image is built, and by `python -m nightsquad.domain.memory.fetch_model`
    in a source checkout."""
    return Path(__file__).resolve().parents[2] / "embedding_model"


def _when(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.now(UTC)


class Mem0Engine:
    """Mem0 as a library inside the server (MEM-2). Loaded on first use, never at start,
    because loading it costs about two seconds and 140 MB (NFR-23)."""

    def __init__(self, data_dir: Path, database_url: str, model_dir: Path | None = None) -> None:
        self._directory = data_dir / "memory"
        self._database_url = database_url
        self._model_dir = model_dir or shipped_model_directory()
        self._memory: Any = None
        self._build = threading.Lock()
        self._extracting = threading.Lock()

    def _config(self) -> dict[str, Any]:
        if self._database_url.startswith("sqlite"):
            store: dict[str, Any] = {
                "provider": "qdrant",
                "config": {
                    "path": str(self._directory / "qdrant"),
                    "collection_name": COLLECTION,
                    "embedding_model_dims": EMBEDDING_DIMENSIONS,
                    "on_disk": True,
                },
            }
        else:
            plain = re.sub(r"^postgresql\+\w+://", "postgresql://", self._database_url)
            store = {
                "provider": "pgvector",
                "config": {
                    "connection_string": plain,
                    "collection_name": COLLECTION,
                    "embedding_model_dims": EMBEDDING_DIMENSIONS,
                },
            }
        return {
            "vector_store": store,
            "embedder": {"provider": "fastembed", "config": {"model": EMBEDDING_MODEL}},
            # Mem0 insists on a provider it knows. It is replaced before any call (P3).
            "llm": {"provider": "openai", "config": {"api_key": "unused"}},
            "history_db_path": str(self._directory / "history.db"),
        }

    def _loaded(self) -> Any:
        with self._build:
            if self._memory is None:
                if not any(self._model_dir.glob("models--*")):
                    raise Refusal(
                        "memory_model_missing",
                        "Recall memory is unavailable: the embedding model is not installed.",
                        rule=MEM_2.id,
                        hint="In a source checkout, run "
                        "`python -m nightsquad.domain.memory.fetch_model` once.",
                    )
                # NFR-1: Mem0 reports usage unless told not to, and the model is read from
                # disk, never fetched at run time. Nothing here needs the network.
                os.environ["MEM0_TELEMETRY"] = "false"
                os.environ["FASTEMBED_CACHE_PATH"] = str(self._model_dir)
                os.environ["HF_HUB_OFFLINE"] = "1"
                self._directory.mkdir(parents=True, exist_ok=True)
                mem0: Any = importlib.import_module("mem0")
                self._memory = mem0.Memory.from_config(self._config())
                self._memory.llm = _NoModel()
            return self._memory

    async def _call(self, name: str, *arguments: Any, **named: Any) -> Any:
        def run() -> Any:
            return getattr(self._loaded(), name)(*arguments, **named)

        return await asyncio.to_thread(run)

    def _recalled(self, row: dict[str, Any]) -> Recalled:
        return Recalled(
            id=str(row["id"]),
            scope=str(row.get("user_id", "")),
            text=str(row.get("memory", "")),
            created_at=_when(row.get("created_at")),
            updated_at=_when(row.get("updated_at") or row.get("created_at")),
            score=float(row.get("score") or 0.0),
            metadata=dict(row.get("metadata") or {}),
        )

    async def add(self, scope: str, text: str, metadata: dict[str, Any]) -> str:
        result = await self._call("add", text, user_id=scope, infer=False, metadata=metadata)
        return str(result["results"][0]["id"])

    async def extract(
        self, scope: str, messages: list[dict[str, str]], metadata: dict[str, Any], model: ModelCall
    ) -> list[str]:
        loop = asyncio.get_running_loop()

        def run() -> list[str]:
            memory = self._loaded()
            with self._extracting:
                memory.llm = _GatewayModel(model, loop)
                try:
                    result = memory.add(messages, user_id=scope, infer=True, metadata=metadata)
                finally:
                    memory.llm = _NoModel()
            return [str(item["id"]) for item in result.get("results", [])]

        return await asyncio.to_thread(run)

    async def search(self, scopes: list[str], query: str, limit: int) -> list[Recalled]:
        found: list[Recalled] = []
        for scope in scopes:
            result = await self._call("search", query, filters={"user_id": scope}, top_k=limit)
            found += [self._recalled(row) for row in result.get("results", [])]
        found.sort(key=lambda row: -row.score)
        return found[:limit]

    async def listed(self, scope: str, limit: int) -> list[Recalled]:
        result = await self._call("get_all", filters={"user_id": scope}, top_k=limit)
        rows = [self._recalled(row) for row in result.get("results", [])]
        return sorted(rows, key=lambda row: row.created_at, reverse=True)

    async def get(self, memory_id: str) -> Recalled | None:
        try:
            row = await self._call("get", memory_id)
        except Exception:
            return None
        return self._recalled(row) if row else None

    async def update(self, memory_id: str, text: str) -> None:
        await self._call("update", memory_id, text)

    async def forget(self, memory_id: str) -> None:
        """MEM-6: the entry leaves the store, the index and Mem0's own history file."""

        def run() -> None:
            memory = self._loaded()
            memory.delete(memory_id)
            with memory.db._lock:
                memory.db.connection.execute(
                    "DELETE FROM history WHERE memory_id = ?", (memory_id,)
                )
                memory.db.connection.commit()

        await asyncio.to_thread(run)

    async def forget_scope(self, scope: str) -> None:
        for row in await self.listed(scope, 10_000):
            await self.forget(row.id)

    async def history(self, memory_id: str) -> list[dict[str, Any]]:
        rows = await self._call("history", memory_id)
        return [
            {
                "event": row.get("event"),
                "text": row.get("new_memory") or row.get("old_memory"),
                "at": row.get("created_at"),
            }
            for row in rows
        ]


class _NoModel:
    """Stands where Mem0 expects a model when none may be called."""

    def generate_response(self, *_: Any, **__: Any) -> str:
        raise RuntimeError("no model call is allowed outside an extraction")


class _GatewayModel:
    """Passes Mem0's one extraction call to the platform's metered model call (P3, LLM-14)."""

    def __init__(self, model: ModelCall, loop: asyncio.AbstractEventLoop) -> None:
        self._model = model
        self._loop = loop

    def generate_response(self, messages: list[dict[str, str]], **_: Any) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        prompt = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
        call = asyncio.run_coroutine_threadsafe(self._model(system, prompt), self._loop)
        return call.result()
