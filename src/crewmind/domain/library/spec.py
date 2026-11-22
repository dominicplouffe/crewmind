"""The project spec: one portable document that describes a project completely (LIB-4,
LIB-5). Import, export, clone, rehearsal and grading all read and write this format."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.conversation.orders import MAX_CHARACTERS as ORDER_MAX_CHARACTERS
from crewmind.domain.library.documents import MEMBERS_MAX, RoleDoc, Slug
from crewmind.domain.projects.model import GOAL_MAX_LENGTH, ProjectType

LIB_4 = rules.register(
    Rule("LIB-4", "A project spec names credentials and never holds a secret value.")
)

SECRET_KEYS = frozenset({"value", "key", "secret", "password", "token", "api_key"})


def _no_values(entry: Any, where: str) -> None:
    if not isinstance(entry, dict):
        return
    held = sorted(SECRET_KEYS & {str(name).lower() for name in cast(dict[str, Any], entry)})
    if held:
        raise Refusal(
            "spec_holds_a_secret",
            f"A spec names credentials and never holds their values; {where} sets {held[0]}.",
            rule=LIB_4.id,
            hint="Remove the value. Add the credential itself with `crewmind credentials add`.",
        )


class Deadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: datetime
    source: str = Field(
        min_length=1, max_length=500, description="The outside fact, or whose wish it is."
    )


class SpecCeo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Slug = "ceo"


class SpecTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    role: Slug
    version: int | None = Field(None, ge=1, description="The role version to pin. Default: newest.")
    members: list[str] = Field(min_length=1, max_length=MEMBERS_MAX)
    stand_down_when: str | None = Field(None, max_length=40)


class CredentialGrant(BaseModel):
    """A credential the project needs, by name, and the roles that receive it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    roles: list[Slug] = Field(default_factory=list[str])

    @model_validator(mode="before")
    @classmethod
    def holds_no_value(cls, entry: Any) -> Any:
        _no_values(entry, "a credential")
        return entry


class ProjectSpec(BaseModel):
    """One project, as a file (LIB-4)."""

    model_config = ConfigDict(extra="forbid")

    crewmind_spec: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=GOAL_MAX_LENGTH)
    type: ProjectType
    deadline: Deadline | None = None
    budget_tokens: int | None = Field(None, ge=1, description="Default: the type's budget.")
    quality: Literal["fast", "balanced", "best"] | None = None
    paying_credential: str | None = Field(None, description="The credential that pays, by name.")
    settings: dict[str, Any] = Field(
        default_factory=dict[str, Any], description="Settings that differ from the defaults."
    )
    ceo: SpecCeo = Field(default_factory=SpecCeo)
    teams: list[SpecTeam] = Field(default_factory=list[SpecTeam])
    standing_orders: list[str] = Field(default_factory=list[str])
    controlled_domains: list[str] = Field(default_factory=list[str])
    integrations: list[str] = Field(default_factory=list[str])
    roles: list[RoleDoc] = Field(
        default_factory=list[RoleDoc], description="Custom roles the spec brings with it."
    )
    credentials: list[CredentialGrant] = Field(default_factory=list[CredentialGrant])

    @model_validator(mode="before")
    @classmethod
    def holds_no_value(cls, document: Any) -> Any:
        _no_values(document, "the spec")
        return document

    @model_validator(mode="after")
    def orders_are_sentences(self) -> ProjectSpec:
        for order in self.standing_orders:
            if not 1 <= len(order.strip()) <= ORDER_MAX_CHARACTERS:
                raise ValueError(
                    f"a standing order is 1 to {ORDER_MAX_CHARACTERS} characters: {order[:40]!r}"
                )
        return self
