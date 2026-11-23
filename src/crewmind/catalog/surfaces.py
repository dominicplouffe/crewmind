"""The surfaces operations are exposed on, and which operations belong on which (IF-1.2, IF-1.3)."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, get_args

from pydantic import BaseModel, SecretStr

if TYPE_CHECKING:
    from crewmind.catalog.operation import Operation


class Surface(StrEnum):
    API = "api"
    CLI = "cli"
    MCP = "mcp"
    SLASH = "slash"
    SLACK = "slack"
    AGENT_API = "agent_api"


# Surfaces not yet built, each with the phase that builds it. They are exempt as a whole
# (IF-1.3). Remove an entry when its phase starts.
UNBUILT_SURFACES: dict[Surface, str] = {
    Surface.SLACK: "phase 8 (INT-5)",
}


def surfaces_for(operation: Operation) -> frozenset[Surface]:
    """The surfaces an operation belongs on, before exemptions (IF-1.3, IF-4.2).

    A person reaches the API, the CLI and Slack, plus the chat slash command when the
    operation declares one. An MCP client reaches MCP. An agent run reaches the agent API.
    A host-local operation belongs on the CLI only.
    """
    from crewmind.catalog.operation import Principal

    if operation.host_local:
        return frozenset({Surface.CLI})
    surfaces: set[Surface] = set()
    if Principal.PERSON in operation.principals:
        surfaces |= {Surface.API, Surface.CLI, Surface.SLACK}
        if operation.slash_command is not None:
            surfaces.add(Surface.SLASH)
    if Principal.MCP_CLIENT in operation.principals:
        surfaces.add(Surface.MCP)
    if Principal.AGENT_RUN in operation.principals:
        surfaces.add(Surface.AGENT_API)
    return frozenset(surfaces)


def exposed_on(operation: Operation, surface: Surface) -> bool:
    """Whether an adapter for `surface` must expose `operation`."""
    return surface in surfaces_for(operation) and surface not in operation.exemptions


def takes_a_document(model: type[BaseModel]) -> bool:
    """Whether an input holds another model, or a list of them: a whole document, such
    as a project spec, which cannot be sent in a query string. A secret is never sent in
    one either (IF-3.1, INV-6)."""
    for field in model.model_fields.values():
        parts = [field.annotation, *get_args(field.annotation)]
        parts += [inner for part in get_args(field.annotation) for inner in get_args(part)]
        if SecretStr in parts:
            return True
        if any(isinstance(part, type) and issubclass(part, BaseModel) for part in parts):
            return True
    return False
