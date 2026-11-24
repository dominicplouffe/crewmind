"""Wiring: one engine, one executor and one authenticator per process."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from nightsquad.catalog.execute import Clock, Executor, utc_now
from nightsquad.catalog.registry import load_domain_modules
from nightsquad.domain.accounts.credentials import Authenticator
from nightsquad.domain.connections import mcp_client
from nightsquad.domain.connections.delivery import Masker, given_runs, masker_for_run
from nightsquad.domain.execution import runs
from nightsquad.domain.execution.agent import RunAuthenticator
from nightsquad.domain.install.config import Config, load_config
from nightsquad.domain.memory import recall
from nightsquad.domain.memory.engine import InProcessEngine, Mem0Engine
from nightsquad.domain.models.service import SeatResolver, provider_is_saturated
from nightsquad.domain.projects.access import MembershipAccess
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.domain.settings.registry import Scope as SettingScope
from nightsquad.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from nightsquad.gateway.mock import MockProvider
from nightsquad.gateway.service import Gateway
from nightsquad.live import StreamHub
from nightsquad.runner.check_sandbox import ContainerCheckRunner, ProcessCheckRunner
from nightsquad.runner.containers import install_id
from nightsquad.runner.mcp_commands import CommandPool
from nightsquad.services import CLOCK, SESSIONS, Services
from nightsquad.storage.engine import create_engine


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
    commands: CommandPool
    hub: StreamHub

    async def masker(self, run_id: str) -> Masker:
        """The masking of one run's given secrets (CON-8). Held in memory once the run's
        values were handed over, so most calls touch no database."""
        kept = given_runs.get(run_id)
        if kept is not None:
            return kept
        if not self.config.master_key_file.exists():
            return Masker()
        async with self.sessions() as session, session.begin():
            return await masker_for_run(session, SecretStore(self.config.master_key_file), run_id)

    async def close(self) -> None:
        await self.commands.close()
        await self.engine.dispose()


SANDBOX_IMAGE = "nightsquad-agent"
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
        checks=ContainerCheckRunner(
            SANDBOX_IMAGE, config.data_dir / "checks", install_id(config.data_dir)
        )
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
    gateway = Gateway(sessions, services.settings, clock, mock, config.master_key_file, hub)
    services.wired["gateway"] = gateway
    services.wired[SESSIONS] = sessions
    services.wired[CLOCK] = clock

    async def command_idle() -> float:
        async with sessions() as session:
            install = Subject(SettingScope.INSTALL, INSTALL_SUBJECT)
            return float(await services.settings.get(session, install, "mcp.command_idle"))

    commands = CommandPool(
        containers=config.sandbox_mode == "container",
        idle_seconds=command_idle,
        default_image=SANDBOX_IMAGE,
        install_id=install_id(config.data_dir),
        cpus=config.sandbox_cpus,
        memory_bytes=config.sandbox_memory,
    )
    mcp_client.command_runner[0] = commands
    return Runtime(
        commands=commands,
        hub=hub,
        settings=services.settings,
        run_authenticator=RunAuthenticator(sessions),
        mock=mock,
        gateway=gateway,
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
