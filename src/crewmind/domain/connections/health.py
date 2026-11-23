"""What broke in a project's connections, each with its fix (CON-14, CON-16): an expired
secret, an MCP server that needs sign-in or is failing, and a need with nothing to meet it
once the project has started. Read only; the holds themselves come from the needs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.domain.connections import needs, service
from crewmind.domain.connections.mcp import ServerState
from crewmind.domain.connections.model import KIND_WORDS, ConnectionState, Kind
from crewmind.domain.projects import operations as projects
from crewmind.domain.projects.model import ProjectState
from crewmind.storage.models import McpServer, Project, ProjectNeed

FIX = "Open Connections in this project (`crewmind connections for-project`)"


async def findings(session: AsyncSession, project: Project) -> list[str]:
    """CON-14: one line per broken thing, naming it and the fix."""
    found: list[str] = []
    for _, item in await service.attached(session, project.id):
        kind = KIND_WORDS.get(Kind(item.kind), item.kind)
        if item.state == ConnectionState.EXPIRED:
            found.append(
                f"The {kind} {item.name} has expired: runs no longer receive it, and seats "
                f"whose role needs it are held. "
                f"{FIX} and replace its value."
            )
            continue
        if item.kind != Kind.MCP_SERVER:
            continue
        server = await session.get(McpServer, item.id)
        if server is None:
            continue
        if server.state == ServerState.NEEDS_SIGN_IN:
            found.append(
                f"The MCP server {item.name} needs you to sign in again: its tools are not "
                f"offered, and seats whose role needs it are held. {FIX} and sign in."
            )
        elif server.state == ServerState.FAILING:
            reason = f": {server.last_error}" if server.last_error else ""
            found.append(
                f"The MCP server {item.name} is failing{reason}. Its tools are offered again "
                f"once it answers. {FIX} and test it."
            )
    if project.state == ProjectState.DRAFT:
        return found  # a draft's missing needs are shown where it is started (CON-5)
    rows = await session.scalars(
        select(ProjectNeed)
        .where(ProjectNeed.project_id == project.id, ProjectNeed.state.in_(needs.UNMET))
        .order_by(ProjectNeed.kind, ProjectNeed.name)
    )
    for need in rows:
        found.append(
            f"Missing {needs.describe(need)}: their seats are held until it is added. "
            f"{FIX} and add it."
        )
    return found


projects.health_checks.append(findings)
