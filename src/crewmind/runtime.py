"""Wiring: one engine, one executor and one authenticator per process."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from crewmind.catalog.execute import Clock, Executor, utc_now
from crewmind.catalog.registry import load_domain_modules
from crewmind.domain.accounts.credentials import Authenticator
from crewmind.domain.execution import runs
from crewmind.domain.execution.agent import RunAuthenticator
from crewmind.domain.install.config import Config, load_config
from crewmind.domain.memory import recall
from crewmind.domain.memory.engine import InProcessEngine, Mem0Engine
from crewmind.domain.models.service import SeatResolver, provider_is_saturated
from crewmind.domain.projects.access import MembershipAccess
from crewmind.domain.settings.service import SettingsService
from crewmind.gateway.mock import MockProvider
from crewmind.gateway.service import Gateway
from crewmind.live import StreamHub
from crewmind.runner.check_sandbox import ContainerCheckRunner, ProcessCheckRunner
from crewmind.services import Services
from crewmind.storage.engine import create_engine


@dataclass
class Runtime:
    config: Config
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    services: Services
    executor: Executor
    authenticator: Authenticator
    clock: Clock
    settings: SettingsService
    run_authenticator: RunAuthenticator
    mock: MockProvider
    gateway: Gateway
    hub: StreamHub

    async def close(self) -> None:
        await self.engine.dispose()


SANDBOX_IMAGE = "crewmind-agent"
"""The image agent sandboxes and check sandboxes run in, in container mode (EXE-12)."""


def build_runtime(
    config: Config,
    clock: Clock = utc_now,
    *,
    mock_default: bool = False,
    mock: MockProvider | None = None,
) -> Runtime:
    load_domain_modules()
    engine = create_engine(config.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    services = Services(
        base_url=config.base_url,
        data_dir=config.data_dir,
        master_key_file=config.master_key_file,
        database_url=config.database_url,
        memory=Mem0Engine(config.data_dir, config.database_url)
        if config.memory_engine == "mem0"
        else InProcessEngine(clock),
        checks=ContainerCheckRunner(SANDBOX_IMAGE)
        if config.sandbox_mode == "container"
        else ProcessCheckRunner(),
        allow_agent_checks_unisolated=config.allow_agent_checks_unisolated,
    )
    recall.purge_engine = services.memory
    mock = mock or MockProvider(config.mock_script_dir)
    runs.seat_resolver = SeatResolver(
        services.settings, clock, mock_default=mock_default or config.mock_script_dir is not None
    )
    runs.provider_saturated = provider_is_saturated
    hub = StreamHub()
    return Runtime(
        hub=hub,
        settings=services.settings,
        run_authenticator=RunAuthenticator(sessions),
        mock=mock,
        gateway=Gateway(sessions, services.settings, clock, mock, config.master_key_file, hub),
        config=config,
        engine=engine,
        sessions=sessions,
        services=services,
        executor=Executor(sessions, MembershipAccess(), services=services, clock=clock),
        authenticator=Authenticator(sessions, clock),
        clock=clock,
    )


async def host_executor() -> Executor:
    """The executor host-local commands run on, built from the environment (IF-4.2)."""
    return build_runtime(load_config()).executor
