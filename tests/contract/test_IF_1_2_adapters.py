"""Adapters are thin: every surface reaches the one handler (IF-1.2, P11)."""

from __future__ import annotations

import json

import httpx
from mcp import Client
from typer.testing import CliRunner

from crewmind.surfaces.api.app import build_api
from crewmind.surfaces.cli.invoke import HttpInvoker
from crewmind.surfaces.cli.main import ExitCode, build_cli
from crewmind.surfaces.mcp.server import build_mcp
from tests.support import Greeter, api_client_factory, invoker_for, operation, sample_catalog


async def test_IF_1_2_api_cli_and_mcp_reach_the_same_handler() -> None:
    """IF-1.2, IF-4.1: the API route, the MCP tool and the CLI (through the API) share a handler."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    app = build_api(source)

    async with api_client_factory(app)() as client:
        response = await client.post("/v1/sample/greet", json={"name": "ada", "times": 2})
    assert response.status_code == 200
    assert response.json() == {"text": "hello ada hello ada", "calls": 1}

    async with Client(build_mcp(source)) as client:
        result = await client.call_tool("sample_greet", {"name": "ada"})
    assert result.is_error is False
    assert result.structured_content == {"text": "hello ada", "calls": 2}
    assert greeter.calls == 2


def test_IF_1_2_cli_command_goes_through_the_api() -> None:
    """IF-4.1, IF-4.3: a CLI command calls the API route and prints JSON with --json."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    cli = build_cli(source, invoker_for(build_api(source)))
    result = CliRunner().invoke(cli, ["sample", "greet", "--name", "ada", "--json"])
    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {"text": "hello ada", "calls": 1}
    assert greeter.calls == 1


async def test_IF_3_1_read_operations_are_get_routes() -> None:
    """IF-3.1: an operation of class read is a GET with query parameters."""
    source = sample_catalog(Greeter())
    async with api_client_factory(build_api(source))() as client:
        response = await client.get("/v1/sample/read_greeting", params={"name": "ada"})
        refused = await client.post("/v1/sample/read_greeting", json={"name": "ada"})
    assert response.json()["text"] == "hello ada"
    assert refused.status_code == 405


def test_IF_3_1_openapi_schema_comes_from_the_catalog() -> None:
    """IF-3.1: the published OpenAPI schema lists each operation under its catalog name."""
    schema = build_api(sample_catalog(Greeter())).openapi()
    assert schema["paths"]["/v1/sample/greet"]["post"]["operationId"] == "sample.greet"
    assert schema["paths"]["/v1/sample/read_greeting"]["get"]["operationId"] == (
        "sample.read_greeting"
    )


def test_IF_4_3_cli_accepts_the_whole_input_as_json() -> None:
    """IF-4.3: --input gives the whole input, so non-scalar fields are reachable."""
    source = sample_catalog(Greeter())
    cli = build_cli(source, invoker_for(build_api(source)))
    result = CliRunner().invoke(
        cli, ["sample", "greet", "--input", '{"name": "ada", "times": 2}', "--json"]
    )
    assert json.loads(result.stdout)["text"] == "hello ada hello ada"


def test_IF_4_2_host_local_commands_run_without_the_server() -> None:
    """IF-4.2: a host-local command runs on the host and does not call the API."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    source.register(operation("sample.backup", greeter, host_local=True))

    def unreachable() -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url="http://127.0.0.1:1")

    cli = build_cli(source, HttpInvoker(unreachable))
    result = CliRunner().invoke(cli, ["sample", "backup", "--name", "ada", "--json"])
    assert result.exit_code == ExitCode.OK
    assert greeter.calls == 1


def test_IF_4_4_server_unreachable_has_its_own_exit_code() -> None:
    """IF-4.4: an unreachable server is distinct from a refusal."""
    source = sample_catalog(Greeter())

    def unreachable() -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url="http://127.0.0.1:1")

    cli = build_cli(source, HttpInvoker(unreachable))
    result = CliRunner().invoke(cli, ["sample", "greet", "--name", "ada"])
    assert result.exit_code == ExitCode.UNREACHABLE
    assert result.stdout == ""
