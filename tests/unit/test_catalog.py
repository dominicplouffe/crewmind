"""The operation catalog refuses bad definitions (IF-1.1)."""

from __future__ import annotations

import pytest

from crewmind.catalog import Catalog, CatalogError, Principal, Surface, surfaces_for
from tests.support import Greeter, operation


def test_IF_1_1_an_operation_name_is_registered_once() -> None:
    """IF-1.1, P11: one operation, one definition."""
    catalog = Catalog()
    greeter = Greeter()
    catalog.register(operation("sample.greet", greeter))
    with pytest.raises(CatalogError, match="already registered"):
        catalog.register(operation("sample.greet", greeter))


@pytest.mark.parametrize("name", ["greet", "Sample.greet", "sample.greet.twice", "sample.", ""])
def test_IF_1_1_names_are_group_dot_verb(name: str) -> None:
    """IF-1.1: every surface derives its route, command and tool from the name."""
    with pytest.raises(CatalogError, match=r"group\.verb"):
        operation(name, Greeter())


def test_IF_1_1_an_operation_serves_a_principal_unless_host_local() -> None:
    """IF-1.1, IF-4.2: an operation nobody can call is refused."""
    with pytest.raises(CatalogError, match="serves no principal"):
        operation("sample.greet", Greeter(), principals=frozenset())


def test_IF_1_3_an_exemption_needs_a_written_reason() -> None:
    """IF-1.3: an exemption without a reason is refused."""
    with pytest.raises(CatalogError, match="without a written reason"):
        operation("sample.greet", Greeter(), exemptions={Surface.MCP: "  "})


def test_IF_1_1_a_slash_command_needs_a_person() -> None:
    """IF-1.1: slash commands are typed by people in the chat."""
    with pytest.raises(CatalogError, match="slash command but no person"):
        operation(
            "sample.greet",
            Greeter(),
            principals=frozenset({Principal.MCP_CLIENT}),
            slash_command="/greet",
        )


def test_IF_1_3_surfaces_follow_from_principals() -> None:
    """IF-1.3: a person reaches API, CLI and Slack (and slash when declared); MCP and agents
    reach their own surface; host-local operations are CLI only (IF-4.2)."""
    greeter = Greeter()
    person = operation("sample.a", greeter, principals=frozenset({Principal.PERSON}))
    assert surfaces_for(person) == {Surface.API, Surface.CLI, Surface.SLACK}
    slash = operation(
        "sample.b", greeter, principals=frozenset({Principal.PERSON}), slash_command="/b"
    )
    assert Surface.SLASH in surfaces_for(slash)
    agent = operation("sample.c", greeter, principals=frozenset({Principal.AGENT_RUN}))
    assert surfaces_for(agent) == {Surface.AGENT_API}
    machine = operation("sample.d", greeter, principals=frozenset({Principal.MCP_CLIENT}))
    assert surfaces_for(machine) == {Surface.MCP}
    assert surfaces_for(operation("sample.e", greeter, host_local=True)) == {Surface.CLI}
