"""Database engines for both supported databases (NFR-8).

This is the only place that knows driver names. Domain code never depends on one
database's features except behind the storage adapter.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class Database(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


_ASYNC_DRIVER = {Database.SQLITE: "sqlite+aiosqlite", Database.POSTGRES: "postgresql+psycopg"}
_SYNC_DRIVER = {Database.SQLITE: "sqlite", Database.POSTGRES: "postgresql+psycopg"}


def database_of(url: str | URL) -> Database:
    backend = make_url(url).get_backend_name()
    if backend == "sqlite":
        return Database.SQLITE
    if backend == "postgresql":
        return Database.POSTGRES
    raise ValueError(f"unsupported database {backend!r}: use SQLite or Postgres (NFR-8)")


def async_url(url: str | URL) -> URL:
    return make_url(url).set(drivername=_ASYNC_DRIVER[database_of(url)])


def sync_url(url: str | URL) -> URL:
    """The URL migrations run with."""
    return make_url(url).set(drivername=_SYNC_DRIVER[database_of(url)])


def _configure_sqlite(connection: Any, _: Any) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_engine(url: str | URL) -> AsyncEngine:
    """Create the async engine for a SQLite or Postgres URL."""
    engine = create_async_engine(async_url(url), pool_pre_ping=True)
    if database_of(url) is Database.SQLITE:
        event.listen(engine.sync_engine, "connect", _configure_sqlite)
    return engine
