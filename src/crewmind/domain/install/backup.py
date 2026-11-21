"""Backup and restore: one owner-readable archive (NFR-4, IF-4.2).

The archive holds the database, the master key and the artifacts. Restore saves the
current state first and needs a typed confirmation word.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.engine import make_url

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.install.config import Config, load_config
from crewmind.domain.install.process import require_stopped
from crewmind.storage.engine import Database

NFR_4 = rules.register(Rule("NFR-4", "A restore saves the current state and needs confirmation."))

CONFIRMATION_WORD = "restore"
_DATABASE = {Database.SQLITE: "database.sqlite", Database.POSTGRES: "database.pgdump"}
_KEY = "master.key"
_ARTIFACTS = "artifacts"
_MEMORY = "memory"
_MANIFEST = "manifest.json"


class BackupInput(BaseModel):
    output: str | None = Field(
        None, description="Where to write the archive. Default: the data directory."
    )


class BackupDone(BaseModel):
    archive: str
    database: str
    bytes: int


class RestoreInput(BaseModel):
    archive: str = Field(description="The backup archive to restore.")
    confirm: str = Field(
        description=f"Type the word `{CONFIRMATION_WORD}`: this replaces everything."
    )


class RestoreDone(BaseModel):
    restored_from: str
    previous_state_saved_to: str


def _postgres_url(config: Config) -> str:
    return make_url(config.database_url).set(drivername="postgresql").render_as_string(False)


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise Refusal(
            "tool_failed",
            f"`{command[0]}` failed: {result.stderr.strip() or 'no output'}",
            rule=NFR_4.id,
            hint=f"Check that {command[0]} is installed and the database is reachable.",
        )


def _dump_database(config: Config, target: Path) -> None:
    if config.database is Database.SQLITE:
        path = make_url(config.database_url).database
        assert path is not None
        with sqlite3.connect(path) as source, sqlite3.connect(target) as copy:
            source.backup(copy)
    else:
        _run(["pg_dump", "--format=custom", f"--file={target}", _postgres_url(config)])


def _load_database(config: Config, source: Path) -> None:
    if config.database is Database.SQLITE:
        path = make_url(config.database_url).database
        assert path is not None
        for suffix in ("", "-wal", "-shm"):
            Path(path + suffix).unlink(missing_ok=True)
        shutil.copyfile(source, path)
    else:
        # Extensions (pgvector, for memory) belong to the database, not to the backup: a
        # database user who is not a superuser can neither drop nor create them. They are
        # left out of the restore and stay as the database has them (MEM-2).
        listing = subprocess.run(
            ["pg_restore", "--list", str(source)], capture_output=True, text=True, check=False
        )
        keep = source.with_suffix(".list")
        keep.write_text(
            "\n".join(line for line in listing.stdout.splitlines() if " EXTENSION " not in line)
        )
        _run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                f"--use-list={keep}",
                f"--dbname={_postgres_url(config)}",
                str(source),
            ]
        )


def write_backup(config: Config, archive: Path, now: datetime) -> int:
    """Write the archive, readable only by its owner. Returns its size in bytes."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        dump = Path(scratch) / _DATABASE[config.database]
        _dump_database(config, dump)
        manifest = Path(scratch) / _MANIFEST
        manifest.write_text(
            json.dumps({"database": config.database.value, "created": now.isoformat()}),
            encoding="utf-8",
        )
        descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as file, tarfile.open(fileobj=file, mode="w:gz") as tar:
            tar.add(manifest, _MANIFEST)
            tar.add(dump, dump.name)
            if config.master_key_file.exists():
                tar.add(config.master_key_file, _KEY)
            artifacts = config.data_dir / _ARTIFACTS
            if artifacts.is_dir():
                tar.add(artifacts, _ARTIFACTS)
            # MEM-2: the memory engine's own files (its history, and on SQLite its index).
            memory = config.data_dir / _MEMORY
            if memory.is_dir():
                tar.add(memory, _MEMORY)
    return archive.stat().st_size


def _default_archive(config: Config, now: datetime, label: str) -> Path:
    return config.data_dir / "backups" / f"crewmind-{label}-{now.strftime('%Y%m%dT%H%M%SZ')}.tar.gz"


@operation(
    "install.backup",
    summary="Back up the database, the master key and the artifacts into one archive.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.REVERSIBLE,
)
async def backup(context: Context, payload: BackupInput) -> BackupDone:
    """NFR-4: one archive, readable only by its owner."""
    config = load_config()
    archive = (
        Path(payload.output).expanduser()
        if payload.output
        else _default_archive(config, context.now, "backup")
    )
    size = write_backup(config, archive, context.now)
    return BackupDone(archive=str(archive), database=config.database.value, bytes=size)


@operation(
    "install.restore",
    summary="Restore a backup archive. Saves the current state first.",
    authority=Authority.HOST_OPERATOR,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def restore(context: Context, payload: RestoreInput) -> RestoreDone:
    """NFR-4: needs the confirmation word, a stopped server and a matching database kind."""
    config = load_config()
    if payload.confirm != CONFIRMATION_WORD:
        raise Refusal(
            "not_confirmed",
            f"A restore replaces the database, the master key and the artifacts. Type the "
            f"word `{CONFIRMATION_WORD}` to confirm.",
            rule=NFR_4.id,
            hint=f"Run it again with --confirm {CONFIRMATION_WORD}.",
        )
    require_stopped(config.data_dir, "restore")
    archive = Path(payload.archive).expanduser()
    with tempfile.TemporaryDirectory() as scratch:
        try:
            with tarfile.open(archive, mode="r:gz") as tar:
                tar.extractall(scratch, filter="data")
            manifest = json.loads((Path(scratch) / _MANIFEST).read_text(encoding="utf-8"))
        except (OSError, tarfile.TarError, ValueError):
            raise Refusal(
                "archive_unreadable",
                f"{archive} is not a crewmind backup archive.",
                rule=NFR_4.id,
                hint="Give the path of an archive made by `crewmind backup`.",
            ) from None
        if manifest["database"] != config.database.value:
            raise Refusal(
                "database_kind_differs",
                f"The archive holds a {manifest['database']} database; this install uses "
                f"{config.database.value}.",
                rule=NFR_4.id,
                hint="Restore into an install of the same kind, then migrate.",
            )
        saved = _default_archive(config, context.now, "before-restore")
        write_backup(config, saved, context.now)
        await context.session.close()
        _load_database(config, Path(scratch) / _DATABASE[config.database])
        key = Path(scratch) / _KEY
        if key.exists():
            shutil.copyfile(key, config.master_key_file)
            config.master_key_file.chmod(0o600)
        artifacts = Path(scratch) / _ARTIFACTS
        if artifacts.is_dir():
            shutil.rmtree(config.data_dir / _ARTIFACTS, ignore_errors=True)
            shutil.copytree(artifacts, config.data_dir / _ARTIFACTS)
        memory = Path(scratch) / _MEMORY
        if memory.is_dir():
            shutil.rmtree(config.data_dir / _MEMORY, ignore_errors=True)
            shutil.copytree(memory, config.data_dir / _MEMORY)
    return RestoreDone(restored_from=str(archive), previous_state_saved_to=str(saved))
