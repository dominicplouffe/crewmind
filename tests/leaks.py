"""Looking for secret values everywhere Nightsquad keeps or says anything (INV-6, CON-8,
CON-16): every row of every table, every file of the data directory, and any other text a
test collected (log lines, model requests, operation answers). A value is looked for raw,
in base64 (standard and URL-safe, with and without padding) and URL-encoded."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from sqlalchemy import select

from nightsquad.storage.models import Base
from tests.support import App


def forms(value: str) -> set[str]:
    raw = value.encode()
    found = {value, quote(value, safe="")}
    for encoded in (base64.b64encode(raw), base64.urlsafe_b64encode(raw)):
        text = encoded.decode()
        found |= {text, text.rstrip("=")}
    return {form for form in found if form}


def _hits(where: str, text: str, values: dict[str, str]) -> list[str]:
    return [
        f"{name} in {where}"
        for name, value in values.items()
        if any(form in text for form in forms(value))
    ]


async def scan(app: App, values: dict[str, str], said: dict[str, Any]) -> list[str]:
    """Every place a value was found, as "name in where". Empty means none leaked."""
    found: list[str] = []
    async with app.runtime.sessions() as session:
        for table in Base.metadata.sorted_tables:
            rows = (await session.execute(select(table))).all()
            if rows:
                text = json.dumps([list(row) for row in rows], default=_text)
                found += _hits(f"table {table.name}", text, values)
    data_dir: Path = app.runtime.config.data_dir
    for path in sorted(data_dir.rglob("*")):
        if path.is_file():
            found += _hits(f"file {path.relative_to(data_dir)}", _text(path.read_bytes()), values)
    for where, thing in said.items():
        found += _hits(where, json.dumps(thing, default=_text), values)
    return found


def _text(thing: Any) -> str:
    if isinstance(thing, bytes | bytearray | memoryview):
        return bytes(cast(bytes, thing)).decode("latin-1")
    return str(thing)
