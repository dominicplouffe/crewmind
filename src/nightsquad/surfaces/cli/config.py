"""What the CLI remembers between runs: the server address and a personal token (IF-4.1)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:8420"


def data_dir() -> Path:
    return Path(os.environ.get("NIGHTSQUAD_DATA_DIR", "~/.nightsquad")).expanduser()


@dataclass
class CliState:
    """Stored by `squad login` in a file only the owner can read."""

    token: str | None = None
    token_id: str | None = None

    @staticmethod
    def path() -> Path:
        return data_dir() / "cli.json"

    @classmethod
    def load(cls) -> CliState:
        try:
            return cls(**json.loads(cls.path().read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        path.write_text(json.dumps(asdict(self)), encoding="utf-8")

    @classmethod
    def clear(cls) -> None:
        cls.path().unlink(missing_ok=True)


def api_address() -> str:
    return os.environ.get("NIGHTSQUAD_API", DEFAULT_API)


def current_token() -> str | None:
    """`NIGHTSQUAD_TOKEN` wins over the token stored by `squad login` (IF-4.1)."""
    return os.environ.get("NIGHTSQUAD_TOKEN") or CliState.load().token
