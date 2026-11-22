"""Test helpers: the product app with people to act as, and sample operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

from crewmind.catalog import Catalog, Principal, Refusal, Reversibility, Surface, catalog
from crewmind.catalog.caller import HOST_OPERATOR, Authority
from crewmind.catalog.define import operation as define
from crewmind.catalog.execute import Context
from crewmind.gateway.mock import ScriptedTurn
from crewmind.jobs.dispatcher import Dispatcher
from crewmind.jobs.planning import PlanningJobs
from crewmind.jobs.platform_work import PlatformWorker
from crewmind.jobs.scheduler import Scheduler
from crewmind.jobs.work import WorkJobs
from crewmind.runner.sandbox import InProcessSandbox
from crewmind.runner.supervisor import Runner
from crewmind.runtime import Runtime
from crewmind.surfaces.agent_api.app import add_agent_api
from crewmind.surfaces.api.app import build_api, route_method, route_path
from crewmind.surfaces.api.files import add_file_routes
from crewmind.surfaces.cli.invoke import HttpInvoker

PASSWORD = "correct horse battery staple"
ADMIN_EMAIL = "admin@example.com"


@dataclass(frozen=True)
class Actor:
    """A signed-in person in a test. `token` is a session credential sent as a bearer."""

    person_id: str
    email: str
    token: str


class App:
    """The product API on a test database."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.api = build_api(
            catalog, runtime.executor, runtime.authenticator, base_url=runtime.config.base_url
        )
        add_agent_api(
            self.api,
            catalog,
            runtime.executor,
            runtime.run_authenticator,
            runtime.gateway,
            runtime.settings,
        )
        add_file_routes(self.api, runtime.executor, runtime.authenticator, runtime.services)
        self._admin: Actor | None = None
        self.dispatcher = Dispatcher(runtime.sessions, runtime.settings, runtime.clock)
        self.scheduler = Scheduler(runtime.sessions, runtime.clock, runtime.settings)
        self.work_jobs = WorkJobs(runtime.sessions, runtime.clock, runtime.services)
        self.planning = PlanningJobs(runtime.sessions, runtime.clock, runtime.services)
        self.platform = PlatformWorker(
            runtime.sessions,
            runtime.clock,
            runtime.gateway,
            runtime.settings,
            runtime.services.memory,
        )

    def runner(self, workers: int = 4, heartbeat_seconds: float = 0.05) -> Runner:
        """A runner whose sandboxes run in this process, against this app."""
        return Runner(
            self.runtime.sessions,
            self.runtime.settings,
            self.runtime.clock,
            InProcessSandbox(httpx.ASGITransport(app=self.api)),
            api_url=self.runtime.config.base_url,
            workspaces=self.runtime.config.data_dir / "workspaces",
            blobs=self.runtime.services.blobs,
            workers=workers,
            heartbeat_seconds=heartbeat_seconds,
        )

    def script(self, key: str, *turns: dict[str, Any]) -> None:
        """Give the mock provider a script: `key` is a seat name, `seat/kind` or `*`."""
        self.runtime.mock.scripts[key] = [ScriptedTurn.model_validate(turn) for turn in turns]

    async def work(self, runner: Runner | None = None) -> int:
        """Dispatch, lease and run everything that is due, to the end. Returns runs started."""
        runner = runner or self.runner()
        await self.dispatcher.tick()
        started = await runner.step()
        await runner.idle()
        return started

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.api), base_url=self.runtime.config.base_url
        )

    async def call(
        self, name: str, actor: Actor | str | None = None, /, **values: Any
    ) -> httpx.Response:
        """Call an operation over HTTP as `actor` (an Actor, a raw token, or nobody)."""
        token = actor.token if isinstance(actor, Actor) else actor
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        operation = catalog.get(name)
        async with self.client() as client:
            if route_method(operation) == "GET":
                return await client.get(route_path(name), params=values, headers=headers)
            return await client.post(route_path(name), json=values, headers=headers)

    async def ok(
        self, name: str, actor: Actor | str | None = None, /, **values: Any
    ) -> dict[str, Any]:
        response = await self.call(name, actor, **values)
        assert response.status_code == 200, response.text
        return response.json()

    async def host(self, name: str, /, **values: Any) -> Any:
        """Run a host-local operation as the host operator."""
        operation = catalog.get(name)
        return await self.runtime.executor.execute(
            operation, HOST_OPERATOR, operation.input(**values)
        )

    async def accept(self, link: str, email: str) -> Actor:
        accepted = await self.ok("auth.use_link", link=link, password=PASSWORD)
        return await self.login(email, accepted["person_id"])

    async def login(self, email: str, person_id: str = "") -> Actor:
        session = await self.ok("auth.login", email=email, password=PASSWORD)
        return Actor(person_id or session["person_id"], email, session["session"])

    async def admin(self) -> Actor:
        """The install's first admin, bootstrapped from the host."""
        if self._admin is None:
            link = await self.host("install.bootstrap_admin", email=ADMIN_EMAIL)
            self._admin = await self.accept(link.link, ADMIN_EMAIL)
            return self._admin
        return await self.login(ADMIN_EMAIL, self._admin.person_id)

    async def person(self, email: str, role: str = "member") -> Actor:
        """An active person, invited by the admin."""
        invite = await self.ok(
            "people.invite", await self.admin(), email=email, name=email.split("@")[0], role=role
        )
        return await self.accept(invite["link"], email)

    async def project(self, chairman: Actor, type: str = "deliver", name: str = "Atlas") -> str:
        created = await self.ok(
            "projects.create", chairman, name=name, type=type, goal="Ship the atlas."
        )
        return created["project_id"]

    async def events(self, actor: Actor, project_id: str) -> list[dict[str, Any]]:
        return (await self.ok("record.list", actor, project_id=project_id, limit=200))["items"]


# Sample operations, for exercising the catalog and adapters without the product's own.

REFUSED_NAME = "forbidden"
SAMPLE_REFUSAL = {
    "kind": "rule",
    "code": "sample_refused",
    "message": "Greeting that name is refused by rule SAMPLE-1.",
    "rule": "SAMPLE-1",
    "hint": "Greet someone else.",
}


class GreetInput(BaseModel):
    name: str = Field(description="Who to greet.")
    times: int = 1


class GreetOutput(BaseModel):
    text: str
    calls: int


class Greeter:
    """The one handler behind every surface. It counts calls, so tests can see who reached it."""

    def __init__(self) -> None:
        self.calls = 0

    async def greet(self, context: Context, payload: GreetInput) -> GreetOutput:
        self.calls += 1
        if payload.name == REFUSED_NAME:
            raise Refusal(
                "sample_refused",
                "Greeting that name is refused by rule SAMPLE-1.",
                rule="SAMPLE-1",
                hint="Greet someone else.",
            )
        return GreetOutput(text=" ".join(["hello", payload.name] * payload.times), calls=self.calls)


EVERYONE = frozenset({Principal.PERSON, Principal.MCP_CLIENT})


def operation(
    name: str,
    greeter: Greeter,
    into: Catalog,
    *,
    reversibility: Reversibility = Reversibility.REVERSIBLE,
    principals: frozenset[Principal] = EVERYONE,
    host_local: bool = False,
    exemptions: dict[Surface, str] | None = None,
    slash_command: str | None = None,
    authority: Authority = Authority.ANYONE,
) -> None:
    """Register a sample operation in `into`."""

    async def handler(context: Context, payload: GreetInput) -> GreetOutput:
        return await greeter.greet(context, payload)

    define(
        name,
        summary=f"Sample operation {name}.",
        authority=Authority.HOST_OPERATOR if host_local else authority,
        reversibility=reversibility,
        principals=principals,
        mcp_scope="read" if Principal.MCP_CLIENT in principals and not host_local else None,
        slash_command=slash_command,
        exemptions=exemptions,
        into=into,
    )(handler)


def sample_catalog(greeter: Greeter) -> Catalog:
    source = Catalog()
    operation("sample.greet", greeter, source)
    operation("sample.read_greeting", greeter, source, reversibility=Reversibility.READ)
    return source


def sample_api(runtime: Runtime, source: Catalog) -> FastAPI:
    return build_api(
        source, runtime.executor, runtime.authenticator, base_url=runtime.config.base_url
    )


def api_client_factory(app: FastAPI) -> Callable[[], httpx.AsyncClient]:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8420"
        )

    return factory


def invoker_for(app: FastAPI, token: str | None = None) -> HttpInvoker:
    return HttpInvoker(api_client_factory(app), lambda: token)


def sample_input(model: type[BaseModel], **known: Any) -> dict[str, Any]:
    """A valid input for an operation, for tests that walk the catalog. `known` supplies
    fields by name, such as project_id."""
    import types
    from enum import Enum
    from typing import Literal, Union, get_args, get_origin

    values: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if name in known:
            values[name] = known[name]
            continue
        if not field.is_required():
            continue
        annotation = field.annotation
        if get_origin(annotation) in (Union, types.UnionType):
            annotation = next(a for a in get_args(annotation) if a is not type(None))
        if get_origin(annotation) is Literal:
            values[name] = get_args(annotation)[0]
        elif isinstance(annotation, type) and issubclass(annotation, Enum):
            values[name] = next(iter(annotation)).value
        elif get_origin(annotation) is dict:
            values[name] = {"run.concurrency": 5}
        elif annotation is bool:
            values[name] = True
        elif annotation is int:
            values[name] = 1
        elif get_origin(annotation) is list:
            values[name] = []
        elif "email" in name:
            values[name] = "someone@example.com"
        else:
            values[name] = "a sample value, long enough"
    return values


class OnLoop:
    """Runs another invoker's calls on the test's event loop. The CLI is synchronous and
    starts its own loop, so an async test drives it from a thread through this bridge."""

    def __init__(self, invoker: Any) -> None:
        import asyncio

        self._invoker = invoker
        self._loop = asyncio.get_running_loop()

    async def invoke(
        self, operation: Any, payload: BaseModel, *, bearer: str | None = None
    ) -> BaseModel:
        import asyncio

        future = asyncio.run_coroutine_threadsafe(
            self._invoker.invoke(operation, payload, bearer=bearer), self._loop
        )
        return await asyncio.wrap_future(future)


async def run_cli(app: Any, arguments: list[str], **options: Any) -> Any:
    """Invoke a CLI command from an async test, in a thread."""
    import asyncio

    from typer.testing import CliRunner

    return await asyncio.to_thread(CliRunner().invoke, app, arguments, **options)


@dataclass(frozen=True)
class LiveRun:
    """A leased, running run in a test, with its token, as a sandbox would hold it."""

    run_id: str
    token: str
    runner_id: str
    seat: str


async def wake(app: App, project_id: str, seat: str = "CEO", kind: str = "test notice") -> None:
    """Give an agent a reason to run: an urgent notice (EXE-2)."""
    from sqlalchemy import select

    from crewmind.domain.execution import notices
    from crewmind.storage.models import Seat

    async with app.runtime.sessions() as session, session.begin():
        row = await session.scalar(
            select(Seat).where(Seat.project_id == project_id, Seat.name == seat)
        )
        assert row is not None
        notices.notify(
            session,
            project_id,
            row.id,
            kind,
            "Something needs you.",
            app.runtime.clock(),
            urgent=True,
        )


async def live_run(
    app: App, project_id: str, seat: str = "CEO", runner_id: str = "test-runner"
) -> LiveRun:
    """Wake an agent, then lease and start its work run by hand, without a sandbox."""
    from crewmind.domain.execution import runs

    stash: dict[tuple[str, str], list[LiveRun]] = app.__dict__.setdefault("_live_runs", {})
    handed: dict[tuple[str, str], LiveRun] = app.__dict__.setdefault("_handed_runs", {})
    key = (project_id, seat)
    earlier = handed.pop(key, None)
    if earlier is not None:
        # A second run for the same agent: the earlier one ends first, as it would.
        async with app.runtime.sessions() as session, session.begin():
            await runs.finish(
                session, earlier.run_id, earlier.runner_id, app.runtime.clock(), failed=False
            )
    if not stash.get(key):
        await wake(app, project_id, seat)
        await app.dispatcher.tick()
        now = app.runtime.clock()
        async with app.runtime.sessions() as session, session.begin():
            leases = await runs.lease(session, app.runtime.settings, runner_id, 50, now)
        for lease in leases:
            async with app.runtime.sessions() as session, session.begin():
                await runs.started(session, lease.run_id, runner_id, now)
        from sqlalchemy import select as _select

        from crewmind.storage.models import Seat as _Seat

        async with app.runtime.sessions() as session:
            names = {
                row.id: row.name
                for row in await session.scalars(
                    _select(_Seat).where(_Seat.project_id == project_id)
                )
            }
        # An agent can have a chat run and a work run at once. Both are kept, the work
        # run first, so a test gets the same one every time.
        for lease in sorted(leases, key=lambda lease: (lease.kind != "work", lease.run_id)):
            if lease.project_id == project_id:
                name = names[lease.seat_id]
                stash.setdefault((project_id, name), []).append(
                    LiveRun(lease.run_id, lease.token, runner_id, name)
                )
    assert stash.get(key), "no run was leased"
    handed[key] = stash[key].pop(0)
    return handed[key]


async def agent_call(app: App, token: str | None, name: str, /, **values: Any) -> httpx.Response:
    """Call the agent API as a sandbox would, with a run token."""
    from crewmind.surfaces.agent_api.app import route_path as agent_path

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with app.client() as client:
        return await client.post(agent_path(name), json=values, headers=headers)


async def run_state(app: App, run_id: str) -> str:
    from crewmind.storage.models import Run

    async with app.runtime.sessions() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        return run.state


async def running_project(app: App, owner: Actor, **settings: Any) -> str:
    project = await app.project(owner)
    if settings:
        await app.ok(
            "settings.change_project",
            owner,
            project_id=project,
            changes=settings,
            reason="Set up for the test.",
        )
    await app.ok("projects.start", owner, project_id=project)
    return project
