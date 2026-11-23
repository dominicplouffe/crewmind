"""How a connection is shown: names, kinds, how it is used and its health. Never a secret's
value (CON-2, INV-6)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller
from crewmind.domain.connections import service
from crewmind.domain.connections.model import Kind
from crewmind.storage.models import (
    Connection,
    ConnectionSecret,
    ConnectionVariable,
    McpServer,
    McpTool,
    ProjectConnection,
)


class McpToolView(BaseModel):
    name: str
    title: str | None
    description: str = Field(description="As the server describes it: untrusted, cut to size.")
    classification: str = Field(description="read, or write when it may change things.")
    permission: str = Field(description="allowed or denied.")
    gone: bool = Field(description="The server no longer offers it.")


class McpView(BaseModel):
    url: str | None
    transport: str | None
    auth_kind: str
    header_name: str | None
    private_allowed: bool
    state: str = Field(description="active, needs sign-in, failing or deleted.")
    server_name: str | None
    server_version: str | None
    last_error: str | None = Field(description="Why the last test or call failed.")
    tools_refreshed_at: datetime | None
    tools: list[McpToolView]


class ConnectionView(BaseModel):
    id: str
    name: str
    kind: str = Field(description="secret, variable or mcp_server.")
    scope: str = Field(description="install, person or project.")
    description: str = Field(description="What it is for. Agents read it.")
    state: str = Field(description="active, expired or deleted.")
    delivery: str | None = Field(default=None, description="For a secret: sent_for_you or given.")
    sites: list[str] = Field(
        default_factory=list, description="For a secret sent for you: the sites it is sent to."
    )
    header_kind: str | None = Field(default=None, description="bearer, basic or header.")
    header_name: str | None = None
    basic_user: str | None = None
    shape: str | None = Field(default=None, description="For a given secret: text or file.")
    env_name: str | None = Field(
        default=None, description="The variable or file name a run gets it under."
    )
    value: str | None = Field(
        default=None, description="A variable's value. A secret's value is never shown."
    )
    value_set_at: datetime | None = Field(
        default=None, description="When a secret's value was last set."
    )
    expires_on: date | None = None
    expires_soon: bool = Field(
        default=False, description="Its expiry is within secret.expiry_warning: people were told."
    )
    created_at: datetime
    changed_at: datetime
    last_used_at: datetime | None = None
    used_in: int = Field(description="How many projects it is attached to.")
    mcp: McpView | None = Field(default=None, description="For an MCP server: its details.")
    yours: bool = Field(description="You may change or delete it.")


async def item_view(session: AsyncSession, caller: Caller, item: Connection) -> ConnectionView:
    view = ConnectionView(
        id=item.id,
        name=item.name,
        kind=item.kind,
        scope=item.scope,
        description=item.description,
        state=item.state,
        env_name=item.env_name,
        expires_on=item.expires_on,
        expires_soon=bool(item.warned),
        created_at=item.created_at,
        changed_at=item.changed_at,
        last_used_at=item.last_used_at,
        value_set_at=item.value_set_at,
        used_in=int(
            await session.scalar(
                select(func.count())
                .select_from(ProjectConnection)
                .where(ProjectConnection.connection_id == item.id)
            )
            or 0
        ),
        yours=await service.can_manage(session, caller, item),
    )
    if item.kind == Kind.SECRET:
        secret = await session.get(ConnectionSecret, item.id)
        if secret is not None:
            view.delivery = secret.delivery
            view.sites = [str(site) for site in secret.sites or []]
            view.header_kind = secret.header_kind
            view.header_name = secret.header_name
            view.basic_user = secret.basic_user
            view.shape = secret.shape
    elif item.kind == Kind.MCP_SERVER:
        server = await session.get(McpServer, item.id)
        if server is not None:
            tools = await session.scalars(
                select(McpTool).where(McpTool.server_id == item.id).order_by(McpTool.name)
            )
            view.mcp = McpView(
                url=server.url, transport=server.transport, auth_kind=server.auth_kind,
                header_name=server.header_name, private_allowed=server.private_allowed,
                state=server.state, server_name=server.server_name,
                server_version=server.server_version, last_error=server.last_error,
                tools_refreshed_at=server.tools_refreshed_at,
                tools=[
                    McpToolView(
                        name=tool.name, title=tool.title, description=tool.description,
                        classification=tool.classification, permission=tool.permission,
                        gone=tool.gone,
                    )
                    for tool in tools
                ],
            )  # fmt: skip
    elif item.kind == Kind.VARIABLE:
        variable = await session.get(ConnectionVariable, item.id)
        view.value = variable.value if variable is not None else None
    return view
