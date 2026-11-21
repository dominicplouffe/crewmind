"""Key rotation, update, and moving a slim install to Postgres (ACC-6, NFR-3, NFR-23)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Literal

import sqlalchemy
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import func, select

import crewmind
from crewmind.catalog.caller import Authority
from crewmind.catalog.define import Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.install.backup import write_backup
from crewmind.domain.install.config import load_config
from crewmind.domain.install.process import require_stopped, running_server
from crewmind.domain.secrets.store import SecretStore
from crewmind.services import services_of
from crewmind.storage.engine import Database, database_of, sync_url
from crewmind.storage.events import event_type
from crewmind.storage.migrate import migrate
from crewmind.storage.models import Base

MASTER_KEY_ROTATED = event_type("install.master_key_rotated", "The master key was rotated.")

NFR_3 = rules.register(Rule("NFR-3", "Update refuses a dirty checkout and backs up first."))
NFR_23 = rules.register(Rule("NFR-23", "A slim install moves to Postgres with no data loss."))


class Rotated(BaseModel):
    secrets_reencrypted: int


class UpdateInput(BaseModel):
    dry_run: bool = Field(False, description="Show the steps without doing them.")


class UpdatePlan(BaseModel):
    dry_run: bool
    steps: list[str]


class MigrateInput(BaseModel):
    to: Literal["postgres"] = Field(description="Where to move the install. Only postgres.")
    url: SecretStr = Field(description="The Postgres URL to move into. It holds a password.")


class Migrated(BaseModel):
    rows_copied: dict[str, int]
    next: str


@operation(
    "install.rotate_key",
    summary="Rotate the master key: re-encrypt every secret, all or nothing.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def rotate_key(context: Context, payload: Empty) -> Rotated:
    """ACC-6: if one value fails, nothing changes."""
    store = SecretStore(services_of(context).master_key_file)
    await store.recover_rotation(context.session)
    try:
        count = await store.rotate(context.session)
        context.record(
            MASTER_KEY_ROTATED, subject=("install", "master key"), detail={"secrets": count}
        )
        await context.session.commit()
    except BaseException:
        store.abandon_rotation()
        raise
    store.finish_rotation()
    return Rotated(secrets_reencrypted=count)


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, text=True, check=False
    )


def checkout_root() -> Path | None:
    """The git checkout crewmind runs from, or None when it was installed as a package."""
    package = Path(crewmind.__file__).resolve().parent
    result = _git(package, "rev-parse", "--show-toplevel")
    return Path(result.stdout.strip()) if result.returncode == 0 else None


@operation(
    "install.update",
    summary="Update a source checkout: back up, pull, migrate, restart.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def update(context: Context, payload: UpdateInput) -> UpdatePlan:
    """NFR-3: refuses a dirty checkout, backs up first, and has a dry run."""
    root = checkout_root()
    if root is None:
        raise Refusal(
            "not_a_checkout",
            "crewmind is installed as a package here, not from a source checkout.",
            rule=NFR_3.id,
            hint="Run `uv tool upgrade crewmind`; `crewmind up` then migrates on start.",
        )
    dirty = _git(root, "status", "--porcelain").stdout.strip()
    if dirty:
        raise Refusal(
            "dirty_checkout",
            f"The checkout at {root} has {len(dirty.splitlines())} uncommitted change(s).",
            rule=NFR_3.id,
            hint="Commit or discard them, then update again.",
        )
    config = load_config()
    server = running_server(config.data_dir)
    archive = (
        config.data_dir / "backups" / f"crewmind-before-update-{context.now:%Y%m%dT%H%M%SZ}.tar.gz"
    )
    steps = [
        f"Back up to {archive}.",
        f"Pull the newest code into {root} (fast-forward only).",
        "Install its dependencies with `uv sync`.",
        "Migrate the database.",
        "Restart the server." if server else "The server is not running; nothing to restart.",
    ]
    if payload.dry_run:
        return UpdatePlan(dry_run=True, steps=steps)
    write_backup(config, archive, context.now)
    for command in (
        ["git", "-C", str(root), "pull", "--ff-only"],
        ["uv", "sync", "--project", str(root)],
    ):
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise Refusal(
                "update_failed",
                f"`{' '.join(command[:2])}` failed: {result.stderr.strip()}",
                rule=NFR_3.id,
                hint=f"Nothing was migrated. Your backup is at {archive}.",
            )
    restart = [sys.executable, "-m", "crewmind", "up", *[str(a) for a in _arguments(server)]]
    if server is not None:
        os.kill(int(str(server["pid"])), signal.SIGTERM)
    subprocess.run([sys.executable, "-m", "crewmind", "setup"], check=False, capture_output=True)
    if server is not None:
        subprocess.Popen(restart, start_new_session=True)
    return UpdatePlan(dry_run=False, steps=steps)


def _arguments(server: dict[str, object] | None) -> list[object]:
    if server is None:
        return []
    argv = server.get("argv", [])
    assert isinstance(argv, list)
    return [argument for argument in argv if argument != "up"]  # pyright: ignore[reportUnknownVariableType]


@operation(
    "install.migrate",
    summary="Move a slim install from SQLite to Postgres, with nothing lost.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def migrate_to_postgres(context: Context, payload: MigrateInput) -> Migrated:
    """NFR-23: every table is copied in one transaction; a non-empty target is refused."""
    config = load_config()
    target_url = payload.url.get_secret_value()
    if config.database is not Database.SQLITE or database_of(target_url) is not Database.POSTGRES:
        raise Refusal(
            "wrong_databases",
            f"This moves a SQLite install to Postgres. This install uses {config.database.value}.",
            rule=NFR_23.id,
            hint="Run it on a slim install, with a Postgres URL.",
        )
    require_stopped(config.data_dir, "migrate")
    await context.session.close()
    migrate(target_url)
    source = sqlalchemy.create_engine(sync_url(config.database_url))
    target = sqlalchemy.create_engine(sync_url(target_url))
    copied: dict[str, int] = {}
    try:
        with source.connect() as reading, target.begin() as writing:
            for table in Base.metadata.sorted_tables:
                if writing.execute(select(func.count()).select_from(table)).scalar_one():
                    raise Refusal(
                        "target_not_empty",
                        f"The target database already has rows in {table.name}.",
                        rule=NFR_23.id,
                        hint="Give an empty database.",
                    )
            for table in Base.metadata.sorted_tables:
                rows = [dict(row._mapping) for row in reading.execute(select(table))]  # pyright: ignore[reportPrivateUsage]
                if rows:
                    writing.execute(table.insert(), rows)
                copied[table.name] = len(rows)
                for column in table.primary_key.columns:
                    if column.autoincrement is True:
                        writing.execute(
                            sqlalchemy.text(
                                f"SELECT setval(pg_get_serial_sequence('{table.name}', "
                                f"'{column.name}'), COALESCE(MAX({column.name}), 1), "
                                f"MAX({column.name}) IS NOT NULL) FROM {table.name}"
                            )
                        )
    finally:
        source.dispose()
        target.dispose()
    return Migrated(
        rows_copied=copied,
        next="Set CREWMIND_DATABASE_URL to the Postgres URL, then run `crewmind up`.",
    )
