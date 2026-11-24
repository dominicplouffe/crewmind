"""The file formats of the library: one role, one squad (LIB-1, LIB-2, LIB-3)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.rules import Rule, rules
from nightsquad.gateway.registry import ModelClass

LIB_1 = rules.register(
    Rule("LIB-1", "A role is a versioned template that names no model and no effort level.")
)

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,98}[a-z0-9]$|^[a-z0-9]$")]
Tool = Literal["files", "shell", "web", "data", "browser", "a2a"]
"""What a role may be granted. Browser and A2A grant nothing until those arrive (EXE-17,
INT-11)."""
MEMBERS_MAX = 12  # EXE-1: a team has 1 to 12 members

NAMES_A_MODEL = frozenset({"model", "models", "effort", "provider", "temperature"})


class RoleDoc(BaseModel):
    """One role, as a file (LIB-1)."""

    model_config = ConfigDict(extra="forbid")

    nightsquad_role: Literal[1] = 1

    @model_validator(mode="before")
    @classmethod
    def names_no_model(cls, document: Any) -> Any:
        if not isinstance(document, dict):
            return document
        fields = cast(dict[str, Any], document)
        named = sorted(NAMES_A_MODEL & set(fields))
        if named:
            raise Refusal(
                "role_names_a_model",
                f"A role names no model and no effort level; this one sets {', '.join(named)}.",
                rule=LIB_1.id,
                hint="Remove the field. Set `min_class` if the role needs a stronger model.",
            )
        return fields

    slug: Slug = Field(description="The role's short id, in lower case with hyphens.")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["ceo", "worker", "reviewer"] = Field(
        description="ceo: can be the CEO. reviewer: reads others' work. worker: does tasks."
    )
    category: str = Field(max_length=40)
    domains: list[str] = Field(default_factory=list[str])
    description: str = Field(min_length=1, max_length=2000)
    min_class: ModelClass | None = Field(
        None, description="The lowest model class this role may run on, whatever the dial says."
    )
    needs_vision: bool = False
    tools: list[Tool] = Field(description="What the role may use inside its sandbox.")
    skills: list[str] = Field(
        default_factory=list[str], description="Skills it may use, each pinned by version."
    )
    credential_names: list[str] = Field(
        default_factory=list[str], description="The credentials it receives, by name only."
    )
    charter: str = Field(min_length=1, max_length=40_000, description="Its standing brief.")


class SquadTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    role: Slug
    members: list[str] = Field(min_length=1, max_length=MEMBERS_MAX)


class Estimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: int = Field(ge=1)
    tokens: int = Field(ge=1)


class SquadDoc(BaseModel):
    """One squad, as a file (LIB-2)."""

    model_config = ConfigDict(extra="forbid")

    nightsquad_squad: Literal[1] = 1
    slug: Slug
    name: str = Field(min_length=1, max_length=200)
    outcome: str = Field(min_length=1, max_length=2000, description="What the squad delivers.")
    ceo_role: Slug
    domains: list[str] = Field(default_factory=list[str])
    teams: list[SquadTeam]
    estimate: Estimate | None = Field(
        None, description="Reference runs and tokens for the job, when known (GOV-4)."
    )


def parse[T: BaseModel](kind: type[T], document: dict[str, Any], what: str) -> T:
    """Read one library document, refusing one that is not in the format."""
    try:
        return kind.model_validate(document)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "the document"
        raise Refusal(
            "document_invalid",
            f"This is not a valid {what}: {where}: {first['msg']}.",
            rule=LIB_1.id if kind is RoleDoc else None,
        ) from error
