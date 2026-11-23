"""Operations on remote MCP servers: test before saving, add, test again, and allow or
deny each tool (CON-9, CON-12, CON-15, INT-4). Adding a server, testing one with a value,
and allowing a tool are the person's own (IF-5.6)."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.connections import attach, mcp, service
from crewmind.domain.connections.item_operations import (
    ConnectionRef,
    Placement,
    new_item,
    record_added,
)
from crewmind.domain.connections.mcp import AuthKind, Permission, ServerState
from crewmind.domain.connections.mcp_client import CON_9, Unreachable, check_url, probe
from crewmind.domain.connections.model import Kind, check_header_name
from crewmind.domain.connections.views import ConnectionView, item_view
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.registry import Scope as SettingScope
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.services import services_of
from crewmind.storage.models import Connection, McpServer, McpTool, Project


class McpTarget(BaseModel):
    url: str = Field(description="The server's address, such as https://mcp.example.com/mcp.")
    auth_kind: AuthKind = Field(
        default=AuthKind.NONE, description="none, bearer, header (a named header) or oauth."
    )
    header_name: str | None = Field(default=None, description="For header: its name.")
    value: SecretStr | None = Field(
        default=None, description="For bearer or header: the token or header value."
    )
    private_network: bool = Field(
        default=False, description="Admins only: allow a private address for this server."
    )


class ToolView(BaseModel):
    name: str
    title: str | None
    description: str = Field(description="As the server describes it: untrusted, cut to size.")
    reads_only: bool = Field(description="The server marks it as only reading.")


class ProbeView(BaseModel):
    transport: str
    server_name: str | None
    server_version: str | None
    tools: list[ToolView]


class AddMcpInput(Placement, McpTarget):
    name: str = Field(description="What it is called, such as github.")
    description: str = Field(min_length=1, max_length=300, description="What it is for.")


class ToolRef(ConnectionRef):
    tool: str = Field(description="The tool's name, as the server gives it.")


async def _limits(context: Context, project_id: str | None) -> tuple[float, int]:
    """The call time limit (per project) and the description length (install)."""
    settings = services_of(context).settings
    session = context.session
    project = await session.get(Project, project_id) if project_id else None
    if project is not None:
        seconds = await settings.get(
            session, Subject(SettingScope.PROJECT, project.id, project.type), "mcp.call_timeout"
        )
    else:
        seconds = int(str(settings.registry.settings["mcp.call_timeout"].default))
    most = await settings.get(
        session, Subject(SettingScope.INSTALL, INSTALL_SUBJECT), "mcp.description_max"
    )
    return float(seconds), int(most)


def _check_target(context: Context, target: McpTarget) -> dict[str, str]:
    """CON-9: the address, who may allow a private one, and the sign-in it needs."""
    if target.private_network and not context.caller.is_admin:
        raise Refusal(
            "admin_only",
            "Only an admin may allow a private address for an MCP server.",
            kind=RefusalKind.FORBIDDEN,
            rule=CON_9.id,
        )
    check_url(target.url, target.private_network)
    value = target.value.get_secret_value() if target.value is not None else ""
    if target.auth_kind in (AuthKind.BEARER, AuthKind.HEADER) and not value:
        raise Refusal("mcp_value_required", "Give the token or header value.", rule=CON_9.id)
    if target.auth_kind in (AuthKind.NONE, AuthKind.OAUTH) and value:
        raise Refusal(
            "mcp_value_unexpected",
            "No value is needed for this kind of sign-in; it was not saved.",
            rule=CON_9.id,
        )
    if target.auth_kind == AuthKind.BEARER:
        return {"Authorization": f"Bearer {value}"}
    if target.auth_kind == AuthKind.HEADER:
        return {check_header_name(target.header_name or ""): value}
    return {}


async def _probe(
    context: Context, target: McpTarget, headers: dict[str, str], project_id: str | None
):
    seconds, most = await _limits(context, project_id)
    try:
        return await probe(
            target.url, headers, private_allowed=target.private_network, seconds=seconds,
            description_max=most,
        )  # fmt: skip
    except Unreachable as error:
        raise Refusal(
            "mcp_unreachable",
            f"The MCP server at {target.url} did not work: {error}.",
            rule=CON_9.id,
            hint="Check the address and the sign-in, then test again.",
        ) from None


@operation(
    "connections.test_mcp_server",
    summary="Test an MCP server before adding it: its name and the tools it offers.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def test_mcp_server(context: Context, payload: McpTarget) -> ProbeView:
    """CON-15: tested, and its tools listed, before anything is saved."""
    if payload.auth_kind == AuthKind.OAUTH:
        raise Refusal(
            "mcp_needs_sign_in",
            "An OAuth server is tested when you sign in, after it is added.",
            rule=CON_9.id,
        )
    found = await _probe(context, payload, _check_target(context, payload), None)
    return ProbeView(
        transport=found.transport,
        server_name=found.name,
        server_version=found.version,
        tools=[
            ToolView(name=t.name, title=t.title, description=t.description, reads_only=t.reads_only)
            for t in found.tools
        ],
    )


@operation(
    "connections.add_mcp_server",
    summary="Add a remote MCP server. It is tested and its tools are listed before it is saved.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def add_mcp_server(context: Context, payload: AddMcpInput) -> ConnectionView:
    """CON-9, CON-12, CON-15: saved only once it works (or, for OAuth, waiting for sign-in);
    tools that only read start allowed, the others denied; with a project, attached."""
    await service.check_project(context.session, context.caller, payload.project_id)
    headers = _check_target(context, payload)
    found = None
    if payload.auth_kind != AuthKind.OAUTH:
        found = await _probe(context, payload, headers, payload.project_id)
    item, project = await new_item(
        context, Kind.MCP_SERVER, payload, payload.name, payload.description
    )
    state = ServerState.ACTIVE if found is not None else ServerState.NEEDS_SIGN_IN
    mcp.SERVER_MACHINE.check("(new)", state)
    server = McpServer(
        connection_id=item.id, kind="remote", url=payload.url.strip(), auth_kind=payload.auth_kind,
        header_name=payload.header_name if payload.auth_kind == AuthKind.HEADER else None,
        private_allowed=payload.private_network, state=state, oauth={},
    )  # fmt: skip
    context.session.add(server)
    if payload.value is not None and payload.auth_kind in (AuthKind.BEARER, AuthKind.HEADER):
        store = SecretStore(services_of(context).master_key_file)
        await service.put_value(
            context.session, store, item, payload.value.get_secret_value(), context.now
        )
    await context.session.flush()
    record_added(context, item, {"auth": payload.auth_kind, "state": state})
    if found is not None:
        await mcp.sync_tools(context.session, server, item, found, context.now, context.caller)
    if project is not None:
        await attach.attach(context, project, item, payload.roles, None)
    return await item_view(context.session, context.caller, item)


async def _server(
    context: Context, ref: ConnectionRef, *, manage: bool
) -> tuple[Connection, McpServer]:
    finder = service.manageable if manage else service.find
    item = await finder(context.session, context.caller, ref.connection, ref.project_id)
    server = await context.session.get(McpServer, item.id)
    if item.kind != Kind.MCP_SERVER or server is None:
        raise Refusal("not_an_mcp_server", f"{item.name} is not an MCP server.", rule=CON_9.id)
    return item, server


@operation(
    "connections.test_mcp",
    summary="Test an MCP server again and read its tools; new tools start by their kind.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def test_mcp(context: Context, payload: ConnectionRef) -> ConnectionView:
    """CON-12, CON-14, LLM-11: a test that works refreshes the tools and closes the breaker;
    one that fails counts toward it, and the reason is kept for the chairman."""
    item, server = await _server(context, payload, manage=False)
    if server.state == ServerState.NEEDS_SIGN_IN:
        raise Refusal(
            "mcp_needs_sign_in", f"{item.name} needs someone to sign in first.", rule=CON_9.id,
            hint="Sign in from its card in Connections.",
        )  # fmt: skip
    store = SecretStore(services_of(context).master_key_file)
    headers = await mcp.headers_for(context.session, store, server)
    seconds, most = await _limits(context, payload.project_id)
    try:
        found = await probe(
            server.url or "", headers, private_allowed=server.private_allowed, seconds=seconds,
            description_max=most, transport=server.transport,
        )  # fmt: skip
    except Unreachable as error:
        mcp.failed(context.session, server, item, str(error), context.now, context.caller)
        context.record(
            mcp.TESTED,
            subject=("connection", item.id),
            after={"name": item.name, "worked": False, "why": str(error)},
        )
        return await item_view(context.session, context.caller, item)
    mcp.worked(context.session, server, item, context.now, context.caller)
    await mcp.sync_tools(context.session, server, item, found, context.now, context.caller)
    context.record(
        mcp.TESTED,
        subject=("connection", item.id),
        after={"name": item.name, "worked": True, "tools": len(found.tools)},
    )
    return await item_view(context.session, context.caller, item)


async def _set_permission(context: Context, payload: ToolRef, target: Permission) -> ConnectionView:
    item, server = await _server(context, payload, manage=True)
    tool = await context.session.scalar(
        select(McpTool).where(
            McpTool.server_id == server.connection_id, McpTool.name == payload.tool
        )
    )
    if tool is None:
        raise Refusal(
            "mcp_tool_not_found", f"{item.name} has no tool named {payload.tool}.",
            kind=RefusalKind.NOT_FOUND, rule=mcp.INT_4.id,
        )  # fmt: skip
    if tool.permission != target:
        mcp.TOOL_MACHINE.check(tool.permission, target)
        context.record(
            mcp.TOOL_CHANGED, subject=("connection", item.id),
            before={"tool": tool.name, "permission": tool.permission},
            after={"tool": tool.name, "permission": target, "classification": tool.classification},
        )  # fmt: skip
        tool.permission = target
    return await item_view(context.session, context.caller, item)


@operation(
    "connections.allow_tool",
    summary="Allow agents to call one tool of an MCP server.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def allow_tool(context: Context, payload: ToolRef) -> ConnectionView:
    """INT-4, IF-5.6: allowing a tool is the person's own, never a model client's."""
    return await _set_permission(context, payload, Permission.ALLOWED)


@operation(
    "connections.deny_tool",
    summary="Stop agents calling one tool of an MCP server.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def deny_tool(context: Context, payload: ToolRef) -> ConnectionView:
    """INT-4: any owner, or a model client acting for one, may deny."""
    return await _set_permission(context, payload, Permission.DENIED)
