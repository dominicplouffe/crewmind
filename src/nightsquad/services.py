"""What handlers need from the running install: its configuration and registries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nightsquad.domain.artifacts.service import BlobStore
from nightsquad.domain.memory.engine import InProcessEngine, MemoryEngine
from nightsquad.domain.settings.registry import SettingsRegistry, load_registry
from nightsquad.domain.settings.service import SettingsService
from nightsquad.runner.check_sandbox import CheckRunner, ProcessCheckRunner

SESSIONS = "sessions"
"""Where `wired` holds the session factory, for an operation's `prepare` step: slow work
that needs its own short transactions before the operation's own one opens."""
CLOCK = "clock"
"""Where `wired` holds the platform clock, for the same `prepare` step."""


@dataclass(frozen=True)
class Services:
    """Install-wide values handed to every handler through the call context."""

    base_url: str
    data_dir: Path
    master_key_file: Path
    database_url: str
    registry: SettingsRegistry = field(default_factory=load_registry)
    memory: MemoryEngine = field(default_factory=InProcessEngine)
    checks: CheckRunner = field(default_factory=ProcessCheckRunner)
    """What runs a task's pinned check (WRK-7)."""
    allow_agent_checks_unisolated: bool = False
    wired: dict[str, Any] = field(default_factory=dict[str, Any])
    """What is built after the services and needs them: the model gateway, under
    `gateway`, for the few operations that make a platform model call (LLM-14)."""
    """Recall memory (MEM-2). The default keeps nothing on disk; a server uses Mem0."""

    @property
    def blobs(self) -> BlobStore:
        """The content-addressed store for artifact bytes (ART-2)."""
        return BlobStore(self.data_dir / "artifacts")

    @property
    def settings(self) -> SettingsService:
        return SettingsService(self.registry)


def services_of(context: Any) -> Services:
    services = context.services
    assert isinstance(services, Services)
    return services
