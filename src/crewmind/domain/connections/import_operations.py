"""Adding many secrets and variables from pasted `.env` text, reviewed before anything is
saved (CON-2). The review carries names, kinds and problems, never values."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.domain.connections import dotenv, needs, service
from crewmind.domain.connections.item_operations import (
    AddSecretInput,
    AddVariableInput,
    Placement,
    add_secret,
    add_variable,
)
from crewmind.domain.connections.model import (
    CON_2,
    Delivery,
    Kind,
    check_env_name,
    check_name,
)
from crewmind.services import services_of
from crewmind.storage.models import Connection, Project


class ImportEnvInput(Placement):
    text: SecretStr = Field(description="The pasted KEY=value lines.")
    secrets: list[str] = Field(
        default_factory=list, description="Keys to add as secrets, whatever their name."
    )
    variables: list[str] = Field(
        default_factory=list, description="Keys to add as variables, whatever their name."
    )
    skip: list[str] = Field(default_factory=list, description="Keys to leave out.")


class ImportLine(BaseModel):
    line: int
    name: str = Field(description="The KEY of the line: the connection's name.")
    kind: str = Field(description="secret or variable.")
    skipped: bool
    problem: str | None = Field(description="What stops this line being saved, in plain words.")


class ImportReview(BaseModel):
    lines: list[ImportLine]
    saved: int = Field(description="How many were saved; 0 for a review.")


async def _problem(
    context: Context, line: dotenv.Line, kind: Kind, payload: ImportEnvInput
) -> str | None:
    if line.problem:
        return line.problem
    try:
        check_name(line.key)
        check_env_name(line.key)
        if kind == Kind.SECRET:
            await service.check_value(
                context.session, services_of(context).settings, line.value, line.key
            )
    except Refusal as refusal:
        return refusal.envelope.message
    owner = await service.check_owner(
        context.session, context.caller, payload.scope, payload.project_id
    )
    taken = await context.session.scalar(
        select(Connection.id).where(
            Connection.scope == payload.scope,
            Connection.owner_id == owner,
            Connection.name_key == line.key.lower(),
            Connection.state.in_(service.LIVE),
        )
    )
    if taken:
        return "a connection with this name already exists"
    if payload.project_id is not None and not payload.roles:
        project = await context.session.get(Project, payload.project_id)
        assert project is not None
        declared = await needs.declared(context.session, project)
        if not any(
            kind == need_kind and line.key.lower() == name.lower() for need_kind, name in declared
        ):
            return "no role needs it: choose the roles that may use it"
    return None


async def _review(
    context: Context, payload: ImportEnvInput
) -> tuple[list[dotenv.Line], list[ImportLine]]:
    await service.check_project(context.session, context.caller, payload.project_id)
    review: list[ImportLine] = []
    parsed = dotenv.parse(payload.text.get_secret_value())
    for line in parsed:
        kind = line.guess
        if line.key in payload.secrets:
            kind = Kind.SECRET
        elif line.key in payload.variables:
            kind = Kind.VARIABLE
        skipped = line.key in payload.skip
        problem = None if skipped else await _problem(context, line, kind, payload)
        line.guess = kind
        review.append(
            ImportLine(line=line.number, name=line.key, kind=kind, skipped=skipped, problem=problem)
        )
    return parsed, review


@operation(
    "connections.review_env",
    summary="Review pasted KEY=value lines before adding them: names, kinds and problems.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
)
async def review_env(context: Context, payload: ImportEnvInput) -> ImportReview:
    """CON-2: the review carries names, kinds and problems, never a value. Nothing is saved."""
    _, review = await _review(context, payload)
    return ImportReview(lines=review, saved=0)


@operation(
    "connections.import_env",
    summary="Add many secrets and variables from pasted KEY=value lines: all or none.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def import_env(context: Context, payload: ImportEnvInput) -> ImportReview:
    """CON-2: saving adds every line not skipped, or none when one has a problem. Secrets
    added this way are given to the agent under their own name, as a `.env` file is read."""
    parsed, review = await _review(context, payload)
    blocked = [line for line in review if line.problem and not line.skipped]
    if blocked:
        raise Refusal(
            "import_has_problems",
            f"{len(blocked)} line(s) cannot be saved: "
            + "; ".join(f"line {line.line} ({line.name}): {line.problem}" for line in blocked),
            rule=CON_2.id,
            hint="Fix them in the text, or skip them.",
        )
    if not [line for line in review if not line.skipped]:
        raise Refusal("import_empty", "There is nothing to save.", rule=CON_2.id)
    saved = 0
    for line, shown in zip(parsed, review, strict=True):
        if shown.skipped:
            continue
        description = f"Imported from a .env file as {line.key}."
        if line.guess == Kind.SECRET:
            await add_secret(
                context,
                AddSecretInput(
                    name=line.key, description=description, value=SecretStr(line.value),
                    delivery=Delivery.GIVEN, env_name=line.key, scope=payload.scope,
                    project_id=payload.project_id, roles=payload.roles,
                ),
            )  # fmt: skip
        else:
            await add_variable(
                context,
                AddVariableInput(
                    name=line.key, description=description, value=line.value,
                    env_name=line.key, scope=payload.scope,
                    project_id=payload.project_id, roles=payload.roles,
                ),
            )  # fmt: skip
        saved += 1
    return ImportReview(lines=review, saved=saved)
