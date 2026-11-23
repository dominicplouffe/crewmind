"""Operational configuration, read from the environment at start (NFR-7, Appendix A).

Every variable, its default and its range come from the operational table of the settings
registry. Nothing here is a governed setting.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crewmind.catalog.rules import Rule, rules
from crewmind.domain.settings.registry import (
    OperationalSetting,
    SettingType,
    SettingValueError,
    load_registry,
)
from crewmind.storage.engine import Database, database_of

NFR_6 = rules.register(Rule("NFR-6", "The server is published only with TLS and a public URL."))

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class ConfigError(ValueError):
    """An environment variable is missing or outside its allowed values."""


@dataclass(frozen=True)
class Config:
    database_url: str
    data_dir: Path
    master_key_file: Path
    host: str
    port: int
    public_url: str | None
    sandbox_mode: str = "container"
    sandbox_cpus: int = 2
    sandbox_memory: int = 2 * 1024**3
    agent_api_url: str | None = None
    egress_port: int = 0
    """CON-6: where the egress proxy listens, on the server's own host (`CREWMIND_EGRESS_PORT`)."""
    mock_script_dir: Path | None = None
    memory_engine: str = "mem0"
    allow_agent_checks_unisolated: bool = False

    @property
    def agent_api(self) -> str:
        """Where a sandbox reaches the agent API and the model gateway."""
        return self.agent_api_url or f"http://{self.host}:{self.port}"

    @property
    def base_url(self) -> str:
        """Where people reach this install: the public URL, or the local address."""
        return self.public_url or f"http://{self.host}:{self.port}"

    @property
    def database(self) -> Database:
        return database_of(self.database_url)


def _parse(definition: OperationalSetting, raw: str) -> Any:
    value: Any = raw
    if definition.is_whole_number:
        try:
            value = int(raw)
        except ValueError:
            raise ConfigError(f"{definition.name} must be a whole number, not {raw!r}") from None
    elif definition.type is SettingType.BOOL:
        if raw.lower() not in _TRUE | _FALSE:
            raise ConfigError(f"{definition.name} must be on or off, not {raw!r}")
        value = raw.lower() in _TRUE
    try:
        return definition.validate_value(value)
    except SettingValueError as error:
        raise ConfigError(str(error)) from None


def read(name: str, env: Mapping[str, str]) -> Any:
    """One operational variable: the environment's value if set, else the registry default."""
    definition = load_registry().operational[name]
    raw = env.get(name)
    return definition.default if raw is None or raw == "" else _parse(definition, raw)


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def load_config(env: Mapping[str, str] | None = None, *, slim: bool = False) -> Config:
    """Read the configuration. In slim mode the database is SQLite in the data directory
    (NFR-23). Binding beyond localhost needs an https public URL (NFR-6)."""
    env = os.environ if env is None else env
    data_dir = Path(read("CREWMIND_DATA_DIR", env)).expanduser()
    database_url = read("CREWMIND_DATABASE_URL", env)
    if slim or database_url is None:
        if slim and database_url is not None and database_of(database_url) is not Database.SQLITE:
            raise ConfigError(
                "Slim mode runs on SQLite; unset CREWMIND_DATABASE_URL or drop --slim."
            )
        database_url = database_url or f"sqlite:///{data_dir / 'crewmind.sqlite'}"
    key_file = read("CREWMIND_MASTER_KEY_FILE", env)
    host, public_url = read("CREWMIND_HOST", env), read("CREWMIND_PUBLIC_URL", env)
    if not is_loopback(host) and not (public_url or "").startswith("https://"):
        raise ConfigError(
            f"Binding to {host} publishes the server. That needs TLS and CREWMIND_PUBLIC_URL "
            "set to its https address (NFR-6)."
        )
    return Config(
        database_url=database_url,
        data_dir=data_dir,
        master_key_file=Path(key_file).expanduser() if key_file else data_dir / "master.key",
        host=host,
        port=read("CREWMIND_PORT", env),
        public_url=public_url,
        sandbox_mode=read("CREWMIND_SANDBOX_MODE", env),
        sandbox_cpus=read("CREWMIND_SANDBOX_CPUS", env),
        sandbox_memory=read("CREWMIND_SANDBOX_MEMORY", env),
        agent_api_url=read("CREWMIND_AGENT_API_URL", env),
        egress_port=read("CREWMIND_EGRESS_PORT", env),
        mock_script_dir=Path(scripts).expanduser()
        if (scripts := read("CREWMIND_MOCK_SCRIPT_DIR", env))
        else None,
        memory_engine=read("CREWMIND_MEMORY_ENGINE", env),
        allow_agent_checks_unisolated=read("CREWMIND_ALLOW_AGENT_CHECKS_UNISOLATED", env),
    )
