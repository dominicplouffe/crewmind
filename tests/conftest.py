"""Shared fixtures. `--db` selects the database every storage test runs on (NFR-8)."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import uuid
from collections.abc import AsyncIterator, Generator, Iterator
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
    parser.addoption(
        "--live",
        action="store_true",
        help="Also run tests that call a paid model. They read ANTHROPIC_API_KEY.",
    )


def _postgres_admin() -> tuple[sqlalchemy.URL, sqlalchemy.Engine]:
    base = make_url(os.environ.get("CREWMIND_TEST_POSTGRES_URL", DEFAULT_POSTGRES_URL))
    return base, sqlalchemy.create_engine(sync_url(base), isolation_level="AUTOCOMMIT")


@contextlib.contextmanager
def _postgres_database(template: str | None = None) -> Generator[str]:
    """A new Postgres database, dropped afterwards. With `template`, a copy of that one."""
    base, admin = _postgres_admin()
    name = f"crewmind_test_{uuid.uuid4().hex}"
    copy = f' TEMPLATE "{template}"' if template else ""
    with admin.connect() as connection:
        connection.execute(sqlalchemy.text(f'CREATE DATABASE "{name}"{copy}'))
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(sqlalchemy.text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


TEST_SECONDS_LIMIT = 10
"""The longest one test may run unless it is marked `slow`. A suite of quick, independent
tests stays fast in parallel however many are added; one slow test does not."""


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Everything under tests/acceptance starts real processes, so it is `slow`."""
    for item in items:
        if "acceptance" in Path(str(item.fspath)).parts:
            item.add_marker(pytest.mark.slow)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Fail a passing test that ran longer than the limit, naming the remedy."""
    report = yield
    too_slow = call.when == "call" and report.passed and call.duration > TEST_SECONDS_LIMIT
    if too_slow and item.get_closest_marker("slow") is None:
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} took {call.duration:.1f} s; the limit is {TEST_SECONDS_LIMIT} s. "
            "Make it smaller or faster, or move it to tests/acceptance."
        )
    return report


@pytest.fixture
def database_url(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[str]:
    """The URL of a fresh, empty database of the selected kind, removed afterwards. Only
    tests of the migrations themselves need this; the rest use `migrated_url`."""
    if request.config.getoption("--db") == "sqlite":
        yield f"sqlite:///{tmp_path / 'crewmind.sqlite'}"
        return
    with _postgres_database() as url:
        yield url


@pytest.fixture(scope="session")
def migrated_template(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[str]:
    """One migrated database per test process. Each test copies it, which is far cheaper
    than running every migration again, so the suite stays fast as it grows."""
    if request.config.getoption("--db") == "sqlite":
        path = tmp_path_factory.mktemp("template") / "crewmind.sqlite"
        migrate(f"sqlite:///{path}")
        yield str(path)
        return
    with _postgres_database() as url:
        migrate(url)
        yield make_url(url).database or ""


@pytest.fixture
def migrated_url(
    request: pytest.FixtureRequest, migrated_template: str, tmp_path: Path
) -> Iterator[str]:
    """The URL of a fresh, fully migrated database for one test."""
    if request.config.getoption("--db") == "sqlite":
        target = tmp_path / "crewmind.sqlite"
        with (
            contextlib.closing(sqlite3.connect(migrated_template)) as source,
            contextlib.closing(sqlite3.connect(target)) as copy,
        ):
            source.backup(copy)
        yield f"sqlite:///{target}"
        return
    with _postgres_database(template=migrated_template) as url:
        yield url


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
async def runtime(migrated_url: str, tmp_path: Path, clock: FakeClock) -> AsyncIterator[Runtime]:
    """A migrated database and the product's executor on it."""
    config = Config(
        database_url=migrated_url,
        data_dir=tmp_path / "data",
        master_key_file=tmp_path / "data" / "master.key",
        host="127.0.0.1",
        port=8420,
        public_url=None,
        memory_engine="in-process",
    )
    built = build_runtime(config, clock, mock_default=True)
    yield built
    await built.close()


@pytest.fixture
async def app(runtime: Runtime) -> App:
    """The product API on a fresh database, with helpers to act as different people."""
    return App(runtime)
