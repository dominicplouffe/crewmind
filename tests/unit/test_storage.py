"""Storage on both databases (NFR-8, NFR-10). Run with --db=sqlite and --db=postgres."""

from __future__ import annotations

import pytest
import sqlalchemy
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from crewmind.storage.engine import Database, create_engine, database_of, sync_url
from crewmind.storage.migrate import alembic_config, migrate
from crewmind.storage.models import Base

HEAD = "0004"


async def test_NFR_10_migrations_apply_and_are_safe_to_repeat(database_url: str) -> None:
    """NFR-8, NFR-10: migrations apply on the selected database, and applying again is a no-op."""
    migrate(database_url)
    migrate(database_url)
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            version = await connection.execute(text("SELECT version_num FROM alembic_version"))
            assert version.scalar_one() == HEAD
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


def test_NFR_10_the_migrations_build_exactly_the_tables_the_code_uses(database_url: str) -> None:
    """NFR-8, NFR-10: on the selected database, the migrated schema and the models agree,
    so a table or column cannot exist in code without a migration."""
    migrate(database_url)
    assert ScriptDirectory.from_config(alembic_config(database_url)).get_current_head() == HEAD
    engine = sqlalchemy.create_engine(sync_url(database_url))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
