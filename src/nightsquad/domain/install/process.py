"""Knowing whether the server is running on this host, through its pid file."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.install.account_operations import IF_4_2


def pid_file(data_dir: Path) -> Path:
    return data_dir / "server.pid"


def write_pid(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    pid_file(data_dir).write_text(
        json.dumps({"pid": os.getpid(), "argv": sys.argv[1:]}), encoding="utf-8"
    )


def clear_pid(data_dir: Path) -> None:
    pid_file(data_dir).unlink(missing_ok=True)


def running_server(data_dir: Path) -> dict[str, object] | None:
    """The pid and arguments of the server running from this data directory, if any."""
    try:
        record = json.loads(pid_file(data_dir).read_text(encoding="utf-8"))
        pid = int(record["pid"])
        os.kill(pid, 0)
    except (OSError, ValueError, KeyError):
        return None
    # A file that names this very process was left by an earlier server that died without
    # clearing it. In a container the server always has the same pid, so without this a
    # killed container could never start again.
    return None if pid == os.getpid() else record


def require_stopped(data_dir: Path, action: str) -> None:
    record = running_server(data_dir)
    if record is not None:
        raise Refusal(
            "server_running",
            f"The server is running (pid {record['pid']}). Stop it before you {action}.",
            rule=IF_4_2.id,
            hint="Stop `squad up`, then run this again.",
        )
