"""Shared fixtures. `--db` selects the database every storage test runs on (NFR-8)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy
from sqlalchemy.engine import make_url

from crewmind.domain.install.config import Config
from crewmind.runtime import Runtime, build_runtime
from crewmind.storage.engine import sync_url
from crewmind.storage.migrate import migrate
from tests.support import App

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


class FakeClock:
    """A clock tests can move. It starts at a fixed time."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Argon2 at its cheapest, so the suite stays fast. The algorithm is unchanged."""
    from argon2 import PasswordHasher

    from crewmind.domain.accounts import passwords

    hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    monkeypatch.setattr(passwords, "_hasher", hasher)
    monkeypatch.setattr(passwords, "_DUMMY_HASH", hasher.hash("a password nobody has"))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def runtime(database_url: str, tmp_path: Path, clock: FakeClock) -> AsyncIterator[Runtime]:
    """A migrated database and the product's executor on it."""
    migrate(database_url)
    config = Config(
        database_url=database_url,
        data_dir=tmp_path / "data",
        master_key_file=tmp_path / "data" / "master.key",
        host="127.0.0.1",
        port=8420,
        public_url=None,
    )
    built = build_runtime(config, clock, mock_default=True)
    yield built
    await built.close()


@pytest.fixture
async def app(runtime: Runtime) -> App:
    """The product API on a fresh database, with helpers to act as different people."""
    return App(runtime)
