"""Refusals are identical on every surface (IF-1.4, IF-3.4)."""

from __future__ import annotations

import json

from mcp import Client
from typer.testing import CliRunner

from nightsquad.runtime import Runtime
from nightsquad.surfaces.cli.main import ExitCode, build_cli
from nightsquad.surfaces.mcp.server import build_mcp
from tests.contract.test_IF_1_3_conformance import every_scope
from tests.support import (
    REFUSED_NAME,
    SAMPLE_REFUSAL,
    Greeter,
    api_client_factory,
    invoker_for,
    sample_api,
    sample_catalog,
)


async def test_IF_1_4_a_refusal_is_the_same_on_api_cli_and_mcp(runtime: Runtime) -> None:
    """IF-1.4, IF-3.4: the same code, rule, sentence and hint on the API and MCP."""
    source = sample_catalog(Greeter())
    async with api_client_factory(sample_api(runtime, source))() as client:
        response = await client.post("/v1/sample/greet", json={"name": REFUSED_NAME})
    assert response.status_code == 403
    assert response.json() == SAMPLE_REFUSAL

    async with Client(build_mcp(source, runtime.executor, every_scope)) as client:
        result = await client.call_tool("sample_greet", {"name": REFUSED_NAME})
    assert result.is_error is True
    assert result.structured_content == SAMPLE_REFUSAL


def test_IF_1_4_the_cli_reports_the_same_refusal(runtime: Runtime) -> None:
    """IF-1.4, IF-4.3, IF-4.4: the CLI writes the same envelope to stderr and exits as refused."""
    source = sample_catalog(Greeter())
    invoker = invoker_for(sample_api(runtime, source))
    cli = build_cli(source, invoker, invoker)
    result = CliRunner().invoke(cli, ["sample", "greet", "--name", REFUSED_NAME, "--json"])
    assert result.exit_code == ExitCode.REFUSED
    assert result.stdout == ""
    assert json.loads(result.stderr) == SAMPLE_REFUSAL

    plain = CliRunner().invoke(cli, ["sample", "greet", "--name", REFUSED_NAME])
    assert SAMPLE_REFUSAL["message"] in plain.stderr
    assert SAMPLE_REFUSAL["hint"] in plain.stderr


async def test_IF_3_4_invalid_input_uses_the_envelope_on_api_and_mcp(runtime: Runtime) -> None:
    """IF-3.4: input that fails the schema is answered with the same envelope shape."""
    source = sample_catalog(Greeter())
    async with api_client_factory(sample_api(runtime, source))() as client:
        response = await client.post("/v1/sample/greet", json={"times": "many"})
    async with Client(build_mcp(source, runtime.executor, every_scope)) as client:
        result = await client.call_tool("sample_greet", {"times": "many"})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"
    assert result.is_error is True
    assert result.structured_content == response.json()


async def test_IF_5_2_an_unknown_tool_is_answered_as_unknown(runtime: Runtime) -> None:
    """IF-5.2: a tool the server does not list answers as unknown, without reaching a handler."""
    greeter = Greeter()
    server = build_mcp(sample_catalog(greeter), runtime.executor, every_scope)
    async with Client(server) as client:
        result = await client.call_tool("sample_nothing", {})
    assert result.is_error is True
    assert result.structured_content is not None
    assert result.structured_content["code"] == "unknown_tool"
    assert greeter.calls == 0
