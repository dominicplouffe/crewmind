"""What people do with project specs: check, import, export and clone (LIB-4, LIB-5,
PRJ-9)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.domain.library import transfer
from crewmind.domain.library.spec import ProjectSpec
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.storage.models import Project


class SpecCheck(BaseModel):
    ok: bool
    problems: list[str] = Field(description="What stops the spec from becoming a project.")


class Created(BaseModel):
    project_id: str
    name: str
    type: str
    state: str
    missing: list[str] = Field(
        description="What is still needed before the project can start, in plain sentences."
    )


class CloneInput(ProjectRef):
    name: str = Field(min_length=1, max_length=200, description="The new project's name.")


def _created(project: Project, missing: list[str]) -> Created:
    return Created(
        project_id=project.id,
        name=project.name,
        type=project.type,
        state=project.state,
        missing=missing,
    )


@operation(
    "specs.check",
    summary="Check a project spec without creating anything.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def check(context: Context, payload: ProjectSpec) -> SpecCheck:
    """LIB-5: the same check an import runs first."""
    problems = await transfer.check(context, payload)
    return SpecCheck(ok=not problems, problems=problems)


@operation(
    "projects.import_spec",
    summary="Create a project in draft from a project spec. You become its chairman.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def import_spec(context: Context, payload: ProjectSpec) -> Created:
    """LIB-4, LIB-5: each step is the operation a person would call by hand; a refusal
    at any step leaves nothing created. Secret values are never in a spec, so what is
    still missing is listed."""
    project, missing = await transfer.create(context, payload)
    return _created(project, missing)


@operation(
    "projects.export",
    summary="Export a project as a spec: its goal, settings, roster and standing orders.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def export(context: Context, payload: ProjectRef) -> ProjectSpec:
    """PRJ-9, LIB-4: no history and no secret value."""
    return await transfer.export(context, view_of(context).project)


@operation(
    "projects.clone",
    summary="Create a new draft project set up like this one, with none of its history.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def clone(context: Context, payload: CloneInput) -> Created:
    """PRJ-9: clone copies the settings, roster, pinned role versions, standing orders and
    credential grants, and no history."""
    spec = await transfer.export(context, view_of(context).project)
    project, missing = await transfer.create(
        context, spec.model_copy(update={"name": payload.name, "roles": []})
    )
    return _created(project, missing)
