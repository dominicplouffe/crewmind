"""The operation catalog refuses bad definitions (IF-1.1)."""

from __future__ import annotations

import pytest

from crewmind.catalog import Catalog, CatalogError, Principal, Surface, surfaces_for
from crewmind.catalog.caller import Authority
from tests.support import Greeter, operation


def test_IF_1_1_an_operation_name_is_registered_once() -> None:
    """IF-1.1, P11: one operation, one definition."""
    catalog = Catalog()
    greeter = Greeter()
    operation("sample.greet", greeter, catalog)
    with pytest.raises(CatalogError, match="already registered"):
        operation("sample.greet", greeter, catalog)


@pytest.mark.parametrize("name", ["greet", "Sample.greet", "sample.greet.twice", "sample.", ""])
def test_IF_1_1_names_are_group_dot_verb(name: str) -> None:
    """IF-1.1: every surface derives its route, command and tool from the name."""
    with pytest.raises(CatalogError, match=r"group\.verb"):
        operation(name, Greeter(), Catalog())


def test_IF_1_1_an_operation_serves_a_principal_unless_host_local() -> None:
    """IF-1.1, IF-4.2: an operation nobody can call is refused."""
    with pytest.raises(CatalogError, match="serves no principal"):
        operation("sample.greet", Greeter(), Catalog(), principals=frozenset())


def test_IF_1_3_an_exemption_needs_a_written_reason() -> None:
    """IF-1.3: an exemption without a reason is refused."""
    with pytest.raises(CatalogError, match="without a written reason"):
        operation("sample.greet", Greeter(), Catalog(), exemptions={Surface.MCP: "  "})


def test_IF_1_1_a_slash_command_needs_a_person() -> None:
    """IF-1.1: slash commands are typed by people in the chat."""
    with pytest.raises(CatalogError, match="slash command but no person"):
        operation(
            "sample.greet",
            Greeter(),
            Catalog(),
            principals=frozenset({Principal.MCP_CLIENT}),
            slash_command="/greet",
        )


def test_IF_1_3_surfaces_follow_from_principals() -> None:
    """IF-1.3: a person reaches API, CLI and Slack (and slash when declared); MCP and agents
    reach their own surface; host-local operations are CLI only (IF-4.2)."""
    greeter, catalog = Greeter(), Catalog()
    operation("sample.a", greeter, catalog, principals=frozenset({Principal.PERSON}))
    operation(
        "sample.b", greeter, catalog, principals=frozenset({Principal.PERSON}), slash_command="/b"
    )
    operation("sample.c", greeter, catalog, principals=frozenset({Principal.AGENT_RUN}))
    operation("sample.d", greeter, catalog, principals=frozenset({Principal.MCP_CLIENT}))
    operation("install.e", greeter, catalog, host_local=True)
    assert surfaces_for(catalog.get("sample.a")) == {Surface.API, Surface.CLI, Surface.SLACK}
    assert Surface.SLASH in surfaces_for(catalog.get("sample.b"))
    assert surfaces_for(catalog.get("sample.c")) == {Surface.AGENT_API}
    assert surfaces_for(catalog.get("sample.d")) == {Surface.MCP}
    assert surfaces_for(catalog.get("install.e")) == {Surface.CLI}


def test_IF_3_2_a_project_operation_must_name_its_project() -> None:
    """IF-3.2, INV-5: an operation with a project authority has a project_id input, so the
    one project lookup always runs before its handler."""
    with pytest.raises(CatalogError, match="no project_id input"):
        operation("sample.greet", Greeter(), Catalog(), authority=Authority.PROJECT_CHAIR)
