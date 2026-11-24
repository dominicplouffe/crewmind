"""Doctor's check for settings and data left from before the product was renamed.

NFR-5, NFR-7: the variables, the data directory, the SQLite file and the server's state
root all changed name (ADR-0011). An install that still uses an old one starts as if it
were new, so doctor names each one it finds and how to move it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from nightsquad.domain.install.config import Config

OLD_NAME = "crew" + "mind"
OLD_PREFIX = OLD_NAME.upper() + "_"
NEW_PREFIX = "NIGHTSQUAD_"
SERVER_STATE_ROOT = Path("/var/lib") / OLD_NAME
OLD_DATABASE_FILE = f"{OLD_NAME}.sqlite"


def leftovers(
    config: Config, env: Mapping[str, str] | None = None, home: Path | None = None
) -> list[str]:
    """One sentence per leftover, each with its fix; empty when there are none."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    found: list[str] = []
    old_variables = sorted(name for name in env if name.startswith(OLD_PREFIX))
    if old_variables:
        renamed = ", ".join(
            f"{name} to {NEW_PREFIX}{name[len(OLD_PREFIX) :]}" for name in old_variables
        )
        found.append(f"Rename {renamed}; the old names are no longer read.")
    for path in (home / f".{OLD_NAME}", SERVER_STATE_ROOT):
        if path.is_dir() and path.resolve() != config.data_dir.resolve():
            found.append(
                f"Data from before the rename is in {path}. Stop the server and move it to "
                f"{config.data_dir}, or set NIGHTSQUAD_DATA_DIR to {path}."
            )
    old_database = config.data_dir / OLD_DATABASE_FILE
    if old_database.is_file() and not (config.data_dir / "nightsquad.sqlite").is_file():
        found.append(
            f"The database is still named {old_database.name}. Stop the server and rename it "
            "to nightsquad.sqlite."
        )
    return found
