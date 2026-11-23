"""Adding an MCP server started from a command (CON-11, CON-15). Human-only (IF-5.6): it
runs third-party code, in its own container, with the variables the person chose for it."""

from __future__ import annotations

import re
import shlex
import uuid
from dataclasses import dataclass

from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Authority, Caller
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.connections import attach, mcp, mcp_client, service
from crewmind.domain.connections.item_operations import Placement, new_item, record_added
from crewmind.domain.connections.mcp import AuthKind, ServerState
from crewmind.domain.connections.mcp_client import (
    CommandSpec,
    Probe,
    Target,
    Unreachable,
    probe_target,
)
from crewmind.domain.connections.mcp_operations import limits
from crewmind.domain.connections.mcp_sign_in import sessions_of
from crewmind.domain.connections.model import (
    SECRET_NAME,
    SECRET_OWNER,
    ConnectionState,
    Kind,
    check_env_name,
)
from crewmind.domain.connections.views import ConnectionView, item_view
from crewmind.domain.secrets.store import SecretStore
from crewmind.services import Services
from crewmind.storage.models import ConnectionVariable, McpServer

CON_11 = rules.register(
    Rule("CON-11", "A command MCP server runs alone, with only the variables it was given.")
)
IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/:@-]{0,299}$")


class AddCommandInput(Placement):
    name: str = Field(description="What it is called, such as filesystem.")
    description: str = Field(min_length=1, max_length=300, description="What it is for.")
    command: str = Field(
        min_length=1, max_length=2000, description="The command line, such as `npx -y some-mcp`."
    )
    image: str | None = Field(
        default=None,
        description="The container image. By default, the tool image (Node, Python, uv).",
    )
    environment: dict[str, str] = Field(
        default_factory=dict,
        description="Each environment variable the server needs, and the secret or variable "
        "(by name or id) that fills it.",
    )


@dataclass(frozen=True)
class Prepared:
    probe: Probe
    argv: tuple[str, ...]
    environment: dict[str, str]
    """Each variable and the id of the connection that fills it."""


async def _values(
    session: AsyncSession, caller: Caller, store: SecretStore, payload: AddCommandInput
) -> tuple[dict[str, str], dict[str, str]]:
    """CON-11, CON-7: each variable named safely, filled by a secret or variable the person
    can see. Returns the values, and which connection fills each."""
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for env, ref in payload.environment.items():
        check_env_name(env)
        item = await service.find(session, caller, ref, payload.project_id)
        if item.kind not in (Kind.SECRET, Kind.VARIABLE) or item.state != ConnectionState.ACTIVE:
            raise Refusal(
                "command_env_not_usable",
                f"{item.name} cannot fill {env}: give a secret or a variable.",
                rule=CON_11.id,
            )  # fmt: skip
        if item.kind == Kind.VARIABLE:
            variable = await session.get(ConnectionVariable, item.id)
            value = variable.value if variable is not None else ""
        else:
            value = await store.reveal(session, (SECRET_OWNER, item.id), SECRET_NAME) or ""
        values[env], sources[env] = value, item.id
    return values, sources


async def _prepare(caller: Caller, payload: AddCommandInput, services: Services) -> Prepared:
    """CON-11, CON-15: tested before anything is saved, in a server started for the test and
    stopped after it, with no database transaction open."""
    argv = tuple(shlex.split(payload.command))
    if not argv:
        raise Refusal("command_empty", "Give the command that starts the server.", rule=CON_11.id)
    if payload.image is not None and not IMAGE.match(payload.image):
        raise Refusal("image_invalid", f"{payload.image!r} is not an image name.", rule=CON_11.id)
    store = SecretStore(services.master_key_file)
    async with sessions_of(services)() as session:
        await service.check_project(session, caller, payload.project_id)
        values, sources = await _values(session, caller, store, payload)
        seconds, most = await limits(session, services, payload.project_id)
    spec = CommandSpec(f"test-{uuid.uuid4().hex}", payload.image, argv, values)
    try:
        found = await probe_target(
            Target("", {}, False, None, spec), seconds=seconds, description_max=most
        )
    except Unreachable as error:
        raise Refusal(
            "mcp_unreachable", f"The command server did not start or answer: {error}.",
            rule=CON_11.id, hint="Check the command, the image and the variables, then try again.",
        ) from None  # fmt: skip
    finally:
        runner = mcp_client.command_runner[0]
        if runner is not None:
            await runner.stop(spec.server_id)
    return Prepared(found, argv, sources)


@operation(
    "connections.add_command_mcp_server",
    summary="Add an MCP server started from a command, in its own container; tested first.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
    prepare=_prepare,
)
async def add_command_mcp_server(context: Context, payload: AddCommandInput) -> ConnectionView:
    """CON-11, CON-12, IF-5.6: saved once it works; its tools classified like any server's."""
    await service.check_project(context.session, context.caller, payload.project_id)
    prepared: Prepared = context.prepared
    item, project = await new_item(
        context, Kind.MCP_SERVER, payload, payload.name, payload.description
    )
    mcp.SERVER_MACHINE.check("(new)", ServerState.ACTIVE)
    server = McpServer(
        connection_id=item.id, kind="command", url=None, auth_kind=AuthKind.NONE,
        private_allowed=False, state=ServerState.ACTIVE, oauth={}, command=list(prepared.argv),
        image=payload.image, environment=prepared.environment,
    )  # fmt: skip
    context.session.add(server)
    await context.session.flush()
    record_added(
        context, item,
        {"kind": "command", "command": prepared.argv[0], "variables": sorted(prepared.environment)},
    )  # fmt: skip
    await mcp.sync_tools(context.session, server, item, prepared.probe, context.now, context.caller)
    if project is not None:
        await attach.attach(context, project, item, payload.roles, None)
    return await item_view(context.session, context.caller, item)
