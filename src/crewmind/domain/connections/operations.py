"""Operations on what a project needs and who would wait for it (CON-5, PRJ-1)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.domain.connections import holds
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef


class BlockerItem(BaseModel):
    text: str = Field(description="What is missing, or why a seat cannot run, in plain words.")
    seats: list[str] = Field(description="The names of the agents who would wait for it.")


class Readiness(BaseModel):
    ready: bool = Field(description="Every agent could work if the project started now.")
    waiting: list[BlockerItem] = Field(
        description="What would hold agents, and who. Starting without it holds exactly them."
    )


@operation(
    "projects.readiness",
    summary="Show what the crew would wait for if the project started now, and who.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def readiness(context: Context, payload: ProjectRef) -> Readiness:
    """CON-5, PRJ-1: the start check's findings, read without starting or changing anything."""
    project = view_of(context).project
    found = await holds.blockers(context.session, project, context.now, context.caller, keep=False)
    return Readiness(
        ready=not found,
        waiting=[BlockerItem(text=item.text, seats=item.seats) for item in found],
    )
