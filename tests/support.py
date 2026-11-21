"""Sample operations for exercising the catalog and its adapters. Not product operations."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

from crewmind.catalog import Catalog, Operation, Principal, Refusal, Reversibility, Surface
from crewmind.surfaces.cli.invoke import HttpInvoker

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

    async def greet(self, payload: GreetInput) -> GreetOutput:
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
    *,
    reversibility: Reversibility = Reversibility.REVERSIBLE,
    principals: frozenset[Principal] = EVERYONE,
    host_local: bool = False,
    exemptions: dict[Surface, str] | None = None,
    slash_command: str | None = None,
) -> Operation:
    return Operation(
        name=name,
        summary=f"Sample operation {name}.",
        input=GreetInput,
        output=GreetOutput,
        handler=greeter.greet,
        authority="member",
        reversibility=reversibility,
        audit_actor="person",
        principals=frozenset() if host_local else principals,
        slash_command=slash_command,
        host_local=host_local,
        exemptions=exemptions or {},
    )


def sample_catalog(greeter: Greeter) -> Catalog:
    catalog = Catalog()
    catalog.register(operation("sample.greet", greeter))
    catalog.register(operation("sample.read_greeting", greeter, reversibility=Reversibility.READ))
    return catalog


def api_client_factory(app: FastAPI) -> Callable[[], httpx.AsyncClient]:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    return factory


def invoker_for(app: FastAPI) -> HttpInvoker:
    return HttpInvoker(api_client_factory(app))
