"""What handlers need from the running install: its configuration and registries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from crewmind.domain.settings.registry import SettingsRegistry, load_registry
from crewmind.domain.settings.service import SettingsService


@dataclass(frozen=True)
class Services:
    """Install-wide values handed to every handler through the call context."""

    base_url: str
    data_dir: Path
    master_key_file: Path
    database_url: str
    registry: SettingsRegistry = field(default_factory=load_registry)

    @property
    def settings(self) -> SettingsService:
        return SettingsService(self.registry)


def services_of(context: Any) -> Services:
    services = context.services
    assert isinstance(services, Services)
    return services
