"""Declaring an operation next to its handler (IF-1.1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, get_type_hints

from pydantic import BaseModel

from crewmind.catalog.caller import Authority
from crewmind.catalog.operation import CatalogError, Operation, Principal, Reversibility
from crewmind.catalog.registry import Catalog
from crewmind.catalog.registry import catalog as product_catalog
from crewmind.catalog.surfaces import Surface

PERSON = frozenset({Principal.PERSON})
PERSON_AND_MCP = frozenset({Principal.PERSON, Principal.MCP_CLIENT})
HUMAN_ONLY = "human-only: needs the person, not their model client (IF-5.6)"


class Empty(BaseModel):
    """An operation with no input."""


def operation[Input: BaseModel, Output: BaseModel](
    name: str,
    *,
    summary: str,
    authority: Authority,
    reversibility: Reversibility,
    principals: frozenset[Principal] = PERSON,
    mcp_scope: str | None = None,
    slash_command: str | None = None,
    exemptions: Mapping[Surface, str] | None = None,
    prepare: Callable[[Any, Any, Any], Awaitable[Any]] | None = None,
    into: Catalog = product_catalog,
) -> Callable[
    [Callable[[Any, Input], Awaitable[Output]]], Callable[[Any, Input], Awaitable[Output]]
]:
    """Register the decorated handler as an operation. Input and output models come from
    its annotations. A host-operator authority makes the operation host-local (IF-4.2)."""

    def register(
        handler: Callable[[Any, Input], Awaitable[Output]],
    ) -> Callable[[Any, Input], Awaitable[Output]]:
        hints = get_type_hints(handler)
        parameters = [key for key in hints if key != "return"]
        if len(parameters) != 2 or "return" not in hints:
            raise CatalogError(f"handler of {name} must be annotated as (context, input) -> output")
        host_local = authority is Authority.HOST_OPERATOR
        into.register(
            Operation(
                name=name,
                summary=summary,
                input=hints[parameters[1]],
                output=hints["return"],
                handler=handler,
                authority=authority,
                reversibility=reversibility,
                audit_actor="host operator" if host_local else "caller",
                principals=frozenset() if host_local else principals,
                slash_command=slash_command,
                mcp_scope=mcp_scope,
                host_local=host_local,
                exemptions=exemptions or {},
                prepare=prepare,
            )
        )
        return handler

    return register
