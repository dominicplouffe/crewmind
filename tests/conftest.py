"""Shared fixtures. `--db` selects the database every storage test runs on (NFR-8)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy
from sqlalchemy.engine import make_url

from crewmind.storage.engine import sync_url

DEFAULT_POSTGRES_URL = "postgresql://crewmind:crewmind@localhost:5432/crewmind_test"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--db",
        choices=("sqlite", "postgres"),
        default="sqlite",
        help="The database to run on. Postgres reads CREWMIND_TEST_POSTGRES_URL.",
    )


@pytest.fixture
def database_url(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[str]:
    """The URL of a fresh, empty database of the selected kind, removed afterwards."""
    if request.config.getoption("--db") == "sqlite":
        yield f"sqlite:///{tmp_path / 'crewmind.sqlite'}"
        return
    base = make_url(os.environ.get("CREWMIND_TEST_POSTGRES_URL", DEFAULT_POSTGRES_URL))
    name = f"crewmind_test_{uuid.uuid4().hex}"
    admin = sqlalchemy.create_engine(sync_url(base), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(sqlalchemy.text(f'CREATE DATABASE "{name}"'))
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(sqlalchemy.text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
