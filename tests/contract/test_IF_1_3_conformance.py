"""The conformance test (IF-1.3, P11): every operation is on every surface it belongs on."""

from __future__ import annotations

from collections.abc import Set

import pytest

from crewmind.catalog import (
    UNBUILT_SURFACES,
    Catalog,
    Principal,
    Surface,
    Violation,
    catalog,
    check_conformance,
)
from crewmind.catalog.registry import load_domain_modules
from crewmind.surfaces.api import app as api
from crewmind.surfaces.cli import main as cli
from crewmind.surfaces.mcp import server as mcp
from tests.support import Greeter, invoker_for, operation, sample_catalog


async def built_surfaces(source: Catalog) -> dict[Surface, Set[str]]:
    """Build each real adapter from `source` and read back what it actually exposes."""
    api_app = api.build_api(source)
    return {
        Surface.API: api.exposed_operations(api_app),
        Surface.CLI: cli.exposed_operations(cli.build_cli(source, invoker_for(api_app))),
        Surface.MCP: await mcp.exposed_operations(mcp.build_mcp(source), source),
    }


async def test_IF_1_3_the_catalog_conforms_on_every_built_surface() -> None:
    """IF-1.3, P11: the product catalog is fully exposed on the API, the CLI and MCP."""
    load_domain_modules()
    assert check_conformance(catalog, await built_surfaces(catalog)) == []


async def test_IF_1_3_sample_operations_conform() -> None:
    """IF-1.3: generated adapters expose every operation that belongs on them."""
    source = sample_catalog(Greeter())
    built = await built_surfaces(source)
    assert built[Surface.API] == {"sample.greet", "sample.read_greeting"}
    assert check_conformance(source, built) == []


@pytest.mark.parametrize("surface", [Surface.API, Surface.CLI, Surface.MCP])
async def test_IF_1_3_an_operation_without_an_adapter_fails(surface: Surface) -> None:
    """IF-1.3: an operation registered without an adapter on a surface it belongs on fails."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    built = await built_surfaces(source)
    source.register(operation("sample.unadapted", greeter))
    violations = check_conformance(source, built)
    assert Violation("sample.unadapted", surface, "missing") in violations


async def test_IF_1_3_a_written_exemption_covers_one_operation_on_one_surface() -> None:
    """IF-1.3: an exemption with a reason removes the operation from that surface only."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    source.register(
        operation("sample.app_only", greeter, exemptions={Surface.MCP: "needs a person present"})
    )
    built = await built_surfaces(source)
    assert "sample.app_only" not in built[Surface.MCP]
    assert "sample.app_only" in built[Surface.API]
    assert check_conformance(source, built) == []
    built[Surface.MCP] = {*built[Surface.MCP], "sample.app_only"}
    assert check_conformance(source, built) == [
        Violation("sample.app_only", Surface.MCP, "not expected")
    ]


async def test_IF_1_3_a_surface_not_yet_built_is_exempt_as_a_whole() -> None:
    """IF-1.3: slash, Slack and the agent API are exempt until their phases build them."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    source.register(
        operation(
            "sample.agent_step",
            greeter,
            principals=frozenset({Principal.AGENT_RUN, Principal.PERSON}),
            slash_command="/step",
        )
    )
    assert set(UNBUILT_SURFACES) == {Surface.SLASH, Surface.SLACK, Surface.AGENT_API}
    assert check_conformance(source, await built_surfaces(source)) == []


async def test_IF_1_3_a_built_surface_cannot_also_be_listed_as_unbuilt() -> None:
    """IF-1.3: once a phase builds a surface, its whole-surface exemption must be removed."""
    source = sample_catalog(Greeter())
    built = {**await built_surfaces(source), Surface.SLACK: set[str]()}
    with pytest.raises(ValueError, match="both built and listed as not yet built"):
        check_conformance(source, built)


async def test_IF_1_3_every_surface_is_accounted_for() -> None:
    """IF-1.3: a surface that is neither built nor listed as unbuilt cannot be skipped."""
    source = sample_catalog(Greeter())
    built = await built_surfaces(source)
    del built[Surface.MCP]
    with pytest.raises(ValueError, match="neither built nor listed"):
        check_conformance(source, built)


async def test_IF_4_2_a_host_local_operation_belongs_on_the_cli_only() -> None:
    """IF-4.2, IF-1.3: host-local operations are on the CLI and never on the API or MCP."""
    greeter = Greeter()
    source = sample_catalog(greeter)
    source.register(operation("sample.backup", greeter, host_local=True))
    built = await built_surfaces(source)
    assert "sample.backup" in built[Surface.CLI]
    assert "sample.backup" not in built[Surface.API]
    assert "sample.backup" not in built[Surface.MCP]
    assert check_conformance(source, built) == []


async def test_IF_1_2_an_adapter_with_no_operation_behind_it_fails() -> None:
    """IF-1.2: a route, command or tool that no catalog operation defines is reported."""
    source = sample_catalog(Greeter())
    api_app = api.build_api(source)

    @api_app.post("/v1/sample/handwritten")
    async def handwritten() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    built = {**await built_surfaces(source), Surface.API: api.exposed_operations(api_app)}
    assert check_conformance(source, built) == [
        Violation("sample.handwritten", Surface.API, "unknown operation")
    ]
