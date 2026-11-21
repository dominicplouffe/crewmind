"""Alembic environment. Migrations run on SQLite and on Postgres (NFR-8)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

target_metadata = None


def run_migrations() -> None:
    url = context.config.get_main_option("sqlalchemy.url")
    assert url is not None
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
