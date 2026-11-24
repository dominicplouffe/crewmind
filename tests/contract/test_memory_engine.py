"""The memory engine contract, run against every engine (MEM-2, MEM-3, MEM-6, NFR-1).

The in-process engine runs in the default suite. Mem0 runs with its real stores (embedded
Qdrant on SQLite, pgvector on Postgres) and the local embedding model, when that model has
been fetched; otherwise those cases skip and say how to fetch it.
"""

from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest

from nightsquad.domain.memory.engine import (
    InProcessEngine,
    Mem0Engine,
    MemoryEngine,
    parse_facts,
    shipped_model_directory,
)

PROJECT, OTHER = "project:alpha", "project:beta"
FETCH = "run `uv run python -m nightsquad.domain.memory.fetch_model` first"


@pytest.fixture(params=["in-process", "mem0"])
async def engine(
    request: pytest.FixtureRequest, tmp_path: Path, migrated_url: str
) -> AsyncIterator[MemoryEngine]:
    if request.param == "in-process":
        yield InProcessEngine()
        return
    if not any(shipped_model_directory().glob("models--*")):
        pytest.skip(f"the embedding model is not on disk: {FETCH}")
    built = Mem0Engine(tmp_path / "data", migrated_url)
    yield built
    await built.forget_scope(PROJECT)
    await built.forget_scope(OTHER)


async def test_MEM_2_add_search_update_forget_and_history(engine: MemoryEngine) -> None:
    """MEM-2, MEM-6: a fact is stored, found by a question about it ahead of unrelated
    facts, edited, and forgotten from the store and from the history."""
    launch = await engine.add(PROJECT, "The launch is planned for spring in Montreal.", {})
    await engine.add(PROJECT, "The chairman prefers tables over long paragraphs.", {})
    await engine.add(PROJECT, "The office dog is called Biscuit.", {"source": "run 7"})

    found = await engine.search([PROJECT], "When and where is the launch planned?", 2)
    assert found[0].id == launch
    assert found[0].scope == PROJECT
    assert len(found) <= 2

    await engine.update(launch, "The launch is planned for autumn in Montreal.")
    current = await engine.get(launch)
    assert current is not None
    assert current.text == "The launch is planned for autumn in Montreal."
    assert [step["event"] for step in await engine.history(launch)] == ["ADD", "UPDATE"]

    await engine.forget(launch)
    assert await engine.get(launch) is None
    assert await engine.history(launch) == []
    assert all(row.id != launch for row in await engine.listed(PROJECT, 10))
    again = await engine.search([PROJECT], "When and where is the launch planned?", 3)
    assert all("launch" not in row.text for row in again)


async def test_MEM_3_a_search_reads_only_the_scopes_it_names(engine: MemoryEngine) -> None:
    """MEM-3, P3: nothing from another scope is ever returned, and metadata comes back."""
    await engine.add(PROJECT, "Our revenue target is four million.", {"source": "message 3"})
    await engine.add(OTHER, "Their revenue target is nine million.", {})
    mine = await engine.search([PROJECT], "What is the revenue target?", 5)
    assert [row.scope for row in mine] == [PROJECT]
    assert mine[0].metadata["source"] == "message 3"
    both = await engine.search([PROJECT, OTHER], "What is the revenue target?", 5)
    assert {row.scope for row in both} == {PROJECT, OTHER}

    await engine.forget_scope(OTHER)
    assert await engine.listed(OTHER, 10) == []
    assert len(await engine.listed(PROJECT, 10)) == 1


async def test_MEM_4_extraction_goes_through_the_platforms_model_call(
    engine: MemoryEngine,
) -> None:
    """MEM-4, P3: the engine extracts facts with the model call it is handed and with no
    other, and stores what comes back."""
    calls: list[tuple[str, str]] = []

    async def model(system: str, prompt: str) -> str:
        calls.append((system, prompt))
        return json.dumps({"memory": [{"text": "The supplier ships from Lisbon on Mondays."}]})

    said = [
        {"role": "assistant", "content": "I checked: the supplier ships from Lisbon on Mondays."}
    ]
    ids = await engine.extract(PROJECT, said, {"source": "run 9"}, model)
    assert len(ids) == 1
    assert len(calls) == 1
    assert "supplier ships from Lisbon" in calls[0][1]
    found = await engine.search([PROJECT], "Where does the supplier ship from?", 3)
    assert found[0].text == "The supplier ships from Lisbon on Mondays."


@pytest.mark.parametrize(
    ("answer", "facts"),
    [
        ('{"memory": [{"text": "A fact."}, {"text": " Another. "}]}', ["A fact.", "Another."]),
        ('Sure!\n```json\n{"memory": [{"text": "A fact."}]}\n```', ["A fact."]),
        ('{"memory": []}', []),
        ("I could not find anything.", []),
        ('{"memory": "not a list"', []),
        ('{"memory": [{"note": "no text"}, "loose"]}', []),
    ],
)
def test_MEM_4_a_bad_extractor_answer_stores_nothing(answer: str, facts: list[str]) -> None:
    """MEM-4, P4: the extractor's answer is data. Anything malformed yields no facts."""
    assert parse_facts(answer) == facts


async def test_NFR_1_memory_makes_no_outbound_connection(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-1, MEM-2: with the model on disk, a full round trip through Mem0 opens no
    connection to any host but the database. Mem0's telemetry is off."""
    if not any(shipped_model_directory().glob("models--*")):
        pytest.skip(f"the embedding model is not on disk: {FETCH}")
    reached: list[str] = []
    connect = socket.socket.connect

    def watched(self: socket.socket, address: Any) -> None:
        host = str(cast(tuple[Any, ...], address)[0] if isinstance(address, tuple) else address)
        if host not in ("127.0.0.1", "::1", "localhost") and not host.startswith("/"):
            reached.append(host)
            raise OSError(f"blocked in test: {host}")
        connect(self, address)  # pyright: ignore[reportUnknownArgumentType]

    monkeypatch.setattr(socket.socket, "connect", watched)
    built = Mem0Engine(tmp_path / "data", migrated_url)
    memory_id = await built.add(PROJECT, "The archive is kept for seven years.", {})
    assert (await built.search([PROJECT], "How long is the archive kept?", 1))[0].id == memory_id
    await built.forget(memory_id)
    assert reached == []
