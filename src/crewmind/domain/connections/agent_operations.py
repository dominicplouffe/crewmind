"""What a run is given, for its harness, and what its context pack says about it (CON-3,
CON-7, CON-14, CON-16). The environment is never offered to the model as a tool: the
harness asks once per run and hands the values only to the commands it runs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.domain.connections import delivery
from crewmind.domain.execution import context_pack
from crewmind.domain.execution.agent import AgentView, agent_of
from crewmind.domain.secrets.store import SecretStore
from crewmind.services import services_of
from crewmind.storage.models import Connection, RunStep

GIVEN_STEP = "connections given"
SECRETS_DIR = "CREWMIND_SECRETS_DIR"
"""The variable that names the run's private directory of file secrets."""


class RunEnvironment(BaseModel):
    """INV-6's one exception (CON-7): the values given to this run's agent. The platform
    masks every one of them in all agent text it receives (CON-8)."""

    variables: dict[str, str] = Field(description="Environment variables, by name.")
    files: dict[str, str] = Field(description="Files for the run's private directory, by name.")


@operation(
    "agent.environment",
    summary="The variables and files this run is given. For the harness, not the model.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=frozenset({Principal.AGENT_RUN}),
)
async def environment(context: Context, payload: Empty) -> RunEnvironment:
    """CON-4, CON-7, CON-16: only what is granted to this run's role in its own project.
    The run's trace names each one, never its value; each is marked as used."""
    view = await agent_of(context)
    store = SecretStore(services_of(context).master_key_file)
    given = await delivery.given_for_run(context.session, store, view.run)
    if given:
        context.session.add(
            RunStep(
                run_id=view.run.id,
                kind=GIVEN_STEP,
                data={
                    "given": [
                        {
                            "name": item.name,
                            "as": item.env,
                            "secret": item.secret,
                            "file": item.as_file,
                        }
                        for item in given
                    ]
                },
                at=context.now,
            )
        )
        await context.session.execute(
            update(Connection)
            .where(Connection.id.in_([item.id for item in given]))
            .values(last_used_at=context.now)
        )
    return RunEnvironment(
        variables={item.env: item.value for item in given if not item.as_file},
        files={item.env: item.value for item in given if item.as_file},
    )


async def context_section(session: AsyncSession, view: AgentView) -> str | None:
    """CON-3, CON-7: the pack names what the run is given, its description and its
    variable or file; never a secret's value."""
    given = await delivery.given_for_run(session, None, view.run)
    if not given:
        return None
    lines = ["# What you are given", ""]
    for item in given:
        if item.as_file:
            where = f"the file ${SECRETS_DIR}/{item.env}"
        else:
            where = f"the environment variable {item.env}"
        shown = "" if item.secret else f" = {item.value}"
        kind = "secret" if item.secret else "variable"
        lines.append(f"- {item.name} ({kind}, {where}{shown}): {item.description}")
    lines += [
        "",
        "Secrets are available to the commands you run. Never print, write or send a "
        "secret's value; crewmind replaces it with [secret: NAME] in everything you write.",
    ]
    return "\n".join(lines)


context_pack.added_sections.append(context_section)
