"""Storage on both databases (NFR-8, NFR-10). Run with --db=sqlite and --db=postgres."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from crewmind.storage.engine import Database, create_engine, database_of
from crewmind.storage.migrate import migrate


async def test_NFR_10_migrations_apply_and_are_safe_to_repeat(database_url: str) -> None:
    """NFR-8, NFR-10: migrations apply on the selected database, and applying again is a no-op."""
    migrate(database_url)
    migrate(database_url)
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            version = await connection.execute(text("SELECT version_num FROM alembic_version"))
            assert version.scalar_one() == "0001"
    finally:
        await engine.dispose()


async def test_NFR_8_the_engine_runs_on_the_selected_database(
    database_url: str, request: pytest.FixtureRequest
) -> None:
    """NFR-8: the engine factory serves SQLite and Postgres from one URL form."""
    assert database_of(database_url) == Database(request.config.getoption("--db"))
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


def test_NFR_8_other_databases_are_refused() -> None:
    """NFR-8: only SQLite and Postgres are supported."""
    with pytest.raises(ValueError, match="use SQLite or Postgres"):
        database_of("mysql://localhost/crewmind")
