# ADR-0002: Postgres for full servers, SQLite for slim installs

- **Status:** Accepted (21 Nov 2026, owner: Dominic)
- **Spec:** NFR-8, NFR-23, EXE-5, MEM-2

## Context

The owner wants nightsquad to run slim when needed. v1 shipped both databases, but SQLite could not run half the migrations, so tests passed for a database nobody deployed.

## Decision

Both databases are first-class from the first commit. Every test and migration runs on both in CI. Domain logic never relies on one database's features except behind the storage adapter. Slim mode is one process on SQLite; `squad migrate --to postgres` moves up.

## Consequences

Leasing differs (skip-locking on Postgres, one in-process runner under a write lock on SQLite). Mem0 needs an embedded vector store on SQLite (spec question Q-001).
