"""Who may see and act on a project (INV-5, IF-3.3, ACC-5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Authority, Caller
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.accounts.model import ProjectRole
from crewmind.domain.accounts.people import ACC_5
from crewmind.domain.projects.model import INV_5
from crewmind.storage.models import Membership, Project

_RANK = {ProjectRole.OBSERVER: 1, ProjectRole.CO_CHAIR: 2, ProjectRole.CHAIRMAN: 3}
_NEEDED = {
    Authority.PROJECT_OBSERVER: ProjectRole.OBSERVER,
    Authority.PROJECT_CHAIR: ProjectRole.CO_CHAIR,
    Authority.PROJECT_CHAIRMAN_ONLY: ProjectRole.CHAIRMAN,
}
_ROLE_WORDS = {
    Authority.PROJECT_CHAIR: "the chairman or a co-chair",
    Authority.PROJECT_CHAIRMAN_ONLY: "the chairman",
}


@dataclass(frozen=True)
class ProjectView:
    """A project the caller can see, with their role. An admin who is not a member reads
    every project (section 3) and has no role."""

    project: Project
    role: ProjectRole | None


def project_not_found() -> Refusal:
    """The one answer for a project that does not exist and for one the caller cannot see."""
    return Refusal(
        "project_not_found",
        "There is no project with that id.",
        kind=RefusalKind.NOT_FOUND,
        hint="List your projects with `crewmind projects list`.",
    )


async def role_in(
    session: AsyncSession, person_id: str | None, project_id: str
) -> ProjectRole | None:
    role = await session.scalar(
        select(Membership.role).where(
            Membership.project_id == project_id,
            Membership.person_id == person_id,
            Membership.state == "member",
        )
    )
    return None if role is None else ProjectRole(role)


class MembershipAccess:
    """Resolves the project an operation names, for the executor (INV-5, IF-3.3)."""

    async def resolve(
        self, session: AsyncSession, caller: Caller, project_id: str, authority: Authority
    ) -> ProjectView:
        project = await session.get(Project, project_id)
        role = None if project is None else await role_in(session, caller.person_id, project_id)
        if project is None or (role is None and not caller.is_admin):
            raise project_not_found()
        needed = _NEEDED[authority]
        rank = _RANK[role] if role is not None else _RANK[ProjectRole.OBSERVER]
        if rank < _RANK[needed]:
            raise Refusal(
                "role_required",
                f"This needs {_ROLE_WORDS[authority]} of the project.",
                kind=RefusalKind.FORBIDDEN,
                rule=ACC_5.id,
                hint=f"Ask {_ROLE_WORDS[authority]} to do it.",
            )
        return ProjectView(project, role)


def view_of(context: Any) -> ProjectView:
    view = context.project
    assert isinstance(view, ProjectView)
    return view


__all__ = ["INV_5", "MembershipAccess", "ProjectView", "project_not_found", "role_in", "view_of"]
