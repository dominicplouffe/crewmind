"""Database engines for both supported databases (NFR-8).

This is the only place that knows driver names. Domain code never depends on one
database's features except behind the storage adapter.
"""

from __future__ import annotations

import contextlib
import sqlite3
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


SQLITE_BUSY_TIMEOUT_MS = 30_000
"""How long a SQLite transaction waits for the write lock before it fails."""


def _configure_sqlite(connection: Any, _: Any) -> None:
    # The driver's own transaction handling starts a transaction only at the first write,
    # which lets two transactions read the same rows and both write. Transactions are
    # begun explicitly instead (see `_begin_sqlite`).
    connection.isolation_level = None
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    cursor.close()


def _release_sqlite_lock_on_close(connection: Any, _: Any) -> None:
    """Roll back on the SQLite connection itself whenever the pool closes one.

    A task cancelled in the middle of a query leaves a statement unfinished. SQLite then
    puts off the real close until that statement is garbage collected, and the open
    transaction keeps the write lock meanwhile, so every other transaction waits. The
    rollback is queued on the driver's own thread, ahead of the driver's close, and ends
    the transaction whatever statements are pending.
    """
    driver = getattr(connection, "driver_connection", None)
    raw = getattr(driver, "_connection", None)
    queue = getattr(driver, "_tx", None)
    if raw is None or queue is None:
        return

    def roll_back() -> None:
        with contextlib.suppress(sqlite3.Error):
            raw.rollback()

    queue.put_nowait((None, roll_back))


def _begin_sqlite(connection: Any) -> None:
    """Every SQLite transaction takes the write lock when it begins, so transactions run
    one at a time. This is the write lock under which a slim install leases runs (EXE-5)."""
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def create_engine(url: str | URL) -> AsyncEngine:
    """Create the async engine for a SQLite or Postgres URL."""
    engine = create_async_engine(async_url(url), pool_pre_ping=True)
    if database_of(url) is Database.SQLITE:
        event.listen(engine.sync_engine, "connect", _configure_sqlite)
        event.listen(engine.sync_engine, "close", _release_sqlite_lock_on_close)
        event.listen(engine.sync_engine, "begin", _begin_sqlite)
    return engine
