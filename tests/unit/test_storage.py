"""Storage on both databases (NFR-8, NFR-10). Run with --db=sqlite and --db=postgres."""

from __future__ import annotations

import pytest
import sqlalchemy
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from nightsquad.storage.engine import Database, create_engine, database_of, sync_url
from nightsquad.storage.migrate import alembic_config, migrate
from nightsquad.storage.models import Base

HEAD = "0016"


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
        database_of("mysql://localhost/nightsquad")


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


def _row(table: sqlalchemy.Table, **given: object) -> dict[str, object]:
    """A row with the given values and a placeholder in every other required column."""
    from datetime import UTC, datetime

    row = dict(given)
    for column in table.columns:
        if column.name in row or column.nullable or column.server_default is not None:
            continue
        kind = column.type.python_type
        row[column.name] = (
            datetime.now(UTC)
            if kind is datetime
            else {}
            if kind is dict
            else []
            if kind is list
            else kind()
            if kind in (int, bool)
            else column.name
        )
    return row


def test_EXE_18_the_migration_names_the_seats_that_exist(database_url: str) -> None:
    """EXE-18, NFR-10: on a database from before agent names, team seats show their own
    name, and the CEO and the reviewer draw different first names from the pool, the same
    ones a new project with that id would draw."""
    from alembic import command

    from nightsquad.domain.execution import names

    command.upgrade(alembic_config(database_url), "0014")
    engine = sqlalchemy.create_engine(sync_url(database_url))
    try:
        with engine.begin() as connection:
            tables = sqlalchemy.MetaData()
            tables.reflect(connection, only=["persons", "projects", "roles", "teams", "seats"])
            persons, projects, roles, teams, seats = (
                tables.tables[name] for name in ("persons", "projects", "roles", "teams", "seats")
            )
            connection.execute(persons.insert().values(_row(persons, id="a1")))
            connection.execute(projects.insert().values(_row(projects, id="p1", created_by="a1")))
            connection.execute(roles.insert().values(_row(roles, id="r1", version=1)))
            connection.execute(
                teams.insert().values(_row(teams, id="t1", project_id="p1", role_id="r1"))
            )
            rows = (("s1", "CEO", None), ("s2", "Reviewer", None), ("s3", "Rey", "t1"))
            for seat_id, name, team in rows:
                connection.execute(
                    seats.insert().values(
                        _row(seats, id=seat_id, project_id="p1", team_id=team, name=name,
                             role_id="r1", is_lead=False)
                    )
                )  # fmt: skip
        migrate(database_url)
        with engine.connect() as connection:
            shown = dict(connection.execute(text("SELECT name, display_name FROM seats")).all())
    finally:
        engine.dispose()
    assert shown["Rey"] == "Rey"
    assert shown["CEO"] in names.POOL
    assert shown["Reviewer"] in names.POOL
    assert shown["CEO"] != shown["Reviewer"]
    assert shown["CEO"] == names.draw("p1", {"CEO", "Reviewer", "Rey"})
