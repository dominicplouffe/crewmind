"""Adapters are thin: every surface reaches the one handler (IF-1.2, P11)."""

from __future__ import annotations

import json

import httpx
from mcp import Client
from typer.testing import CliRunner

from nightsquad.catalog.caller import HOST_OPERATOR
from nightsquad.catalog.execute import Executor
from nightsquad.runtime import Runtime
from nightsquad.surfaces.cli.invoke import HttpInvoker, LocalInvoker
from nightsquad.surfaces.cli.main import ExitCode, build_cli
from nightsquad.surfaces.mcp.server import build_mcp
from tests.contract.test_IF_1_3_conformance import every_scope
from tests.support import (
    Greeter,
    api_client_factory,
    invoker_for,
    operation,
    sample_api,
    sample_catalog,
)


def local(runtime: Runtime) -> LocalInvoker:
    async def executor() -> Executor:
        return runtime.executor

    return LocalInvoker(executor)


async def test_IF_1_2_api_cli_and_mcp_reach_the_same_handler(runtime: Runtime) -> None:
    """IF-1.2, IF-4.1: the API route, the MCP tool and the CLI (through the API) share a handler."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    app = sample_api(runtime, source)

    async with api_client_factory(app)() as client:
        response = await client.post("/v1/sample/greet", json={"name": "ada", "times": 2})
    assert response.status_code == 200
    assert response.json() == {"text": "hello ada hello ada", "calls": 1}

    async with Client(build_mcp(source, runtime.executor, every_scope)) as client:
        result = await client.call_tool("sample_greet", {"name": "ada"})
    assert result.is_error is False
    assert result.structured_content == {"text": "hello ada", "calls": 2}
    assert greeter.calls == 2


def test_IF_1_2_cli_command_goes_through_the_api(runtime: Runtime) -> None:
    """IF-4.1, IF-4.3: a CLI command calls the API route and prints JSON with --json."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    invoker = invoker_for(sample_api(runtime, source))
    cli = build_cli(source, invoker, invoker)
    result = CliRunner().invoke(cli, ["sample", "greet", "--name", "ada", "--json"])
    assert result.exit_code == ExitCode.OK, result.output
    assert json.loads(result.stdout) == {"text": "hello ada", "calls": 1}
    assert greeter.calls == 1


async def test_IF_3_1_read_operations_are_get_routes(runtime: Runtime) -> None:
    """IF-3.1: an operation of class read is a GET with query parameters."""
    source = sample_catalog(Greeter())
    async with api_client_factory(sample_api(runtime, source))() as client:
        response = await client.get("/v1/sample/read_greeting", params={"name": "ada"})
        refused = await client.post("/v1/sample/read_greeting", json={"name": "ada"})
    assert response.json()["text"] == "hello ada"
    assert refused.status_code == 405


def test_IF_3_1_openapi_schema_comes_from_the_catalog(runtime: Runtime) -> None:
    """IF-3.1, IF-3.2: the OpenAPI schema lists each operation under its catalog name, with
    the authority it requires."""
    schema = sample_api(runtime, sample_catalog(Greeter())).openapi()
    greet = schema["paths"]["/v1/sample/greet"]["post"]
    assert greet["operationId"] == "sample.greet"
    assert greet["description"] == "Requires: anyone."
    assert schema["paths"]["/v1/sample/read_greeting"]["get"]["operationId"] == (
        "sample.read_greeting"
    )


def test_IF_4_3_cli_accepts_the_whole_input_as_json(runtime: Runtime) -> None:
    """IF-4.3: --input gives the whole input, so every field is reachable."""
    source = sample_catalog(Greeter())
    invoker = invoker_for(sample_api(runtime, source))
    cli = build_cli(source, invoker, invoker)
    result = CliRunner().invoke(
        cli, ["sample", "greet", "--input", '{"name": "ada", "times": 2}', "--json"]
    )
    assert json.loads(result.stdout)["text"] == "hello ada hello ada"


def unreachable() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://127.0.0.1:1")


def test_IF_4_2_host_local_commands_run_without_the_server(runtime: Runtime) -> None:
    """IF-4.2: a host-local command is top-level, runs on the host and does not call the API."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    operation("install.sample_backup", greeter, source, host_local=True)
    cli = build_cli(source, HttpInvoker(unreachable), local(runtime))
    result = CliRunner().invoke(cli, ["sample-backup", "--name", "ada", "--json"])
    assert result.exit_code == ExitCode.OK, result.output
    assert greeter.calls == 1


async def test_IF_4_2_host_local_operations_refuse_every_other_caller(runtime: Runtime) -> None:
    """IF-4.2: only the host operator may run a host-local operation."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    operation("install.sample_backup", greeter, source, host_local=True)
    backup = source.get("install.sample_backup")
    done = await runtime.executor.execute(backup, HOST_OPERATOR, backup.input(name="ada"))
    assert done.model_dump()["calls"] == 1


def test_IF_4_4_server_unreachable_has_its_own_exit_code(runtime: Runtime) -> None:
    """IF-4.4: an unreachable server is distinct from a refusal."""
    source = sample_catalog(Greeter())
    cli = build_cli(source, HttpInvoker(unreachable), local(runtime))
    result = CliRunner().invoke(cli, ["sample", "greet", "--name", "ada"])
    assert result.exit_code == ExitCode.UNREACHABLE
    assert result.stdout == ""
