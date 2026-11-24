"""What a run is given, for its harness, and what its context pack says about it (CON-3,
CON-7, CON-14, CON-16). The environment is never offered to the model as a tool: the
harness asks once per run and hands the values only to the commands it runs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Principal, Reversibility
from nightsquad.domain.connections import delivery, mcp_calls, needs, sending
from nightsquad.domain.execution import context_pack
from nightsquad.domain.execution.agent import AgentView, agent_of
from nightsquad.domain.secrets.store import SecretStore
from nightsquad.services import services_of
from nightsquad.storage.models import Connection, RunStep

GIVEN_STEP = "connections given"
EGRESS = "egress"
"""Where `services.wired` holds the egress proxy's address for sandboxes (CON-6)."""
SECRETS_DIR = "NIGHTSQUAD_SECRETS_DIR"
"""The variable that names the run's private directory of file secrets."""


class RunEnvironment(BaseModel):
    """INV-6's one exception (CON-7): the values given to this run's agent. The platform
    masks every one of them in all agent text it receives (CON-8)."""

    variables: dict[str, str] = Field(description="Environment variables, by name.")
    files: dict[str, str] = Field(description="Files for the run's private directory, by name.")
    proxy: str | None = Field(
        default=None,
        description="CON-6: the egress proxy to send the run's web traffic through, when it "
        "has a secret sent for it. The run token is the proxy credential.",
    )
    authority: str | None = Field(
        default=None,
        description="The certificate (PEM, public) of the authority the proxy signs with.",
    )


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
    sent = await sending.sent_values(context.session, store, view.run)
    delivery.given_runs.remember(view.run.id, delivery.Masker.of(given, sent))
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
    proxy, certificate = None, None
    egress: str | None = services_of(context).wired.get(EGRESS)
    if egress is not None and await sending.has_sending(context.session, view.run):
        proxy = egress
        certificate = (await sending.authority(context.session, store, context.now)).certificate_pem
    return RunEnvironment(
        variables={item.env: item.value for item in given if not item.as_file},
        files={item.env: item.value for item in given if item.as_file},
        proxy=proxy,
        authority=certificate.decode() if certificate else None,
    )


async def context_section(session: AsyncSession, view: AgentView) -> str | None:
    """CON-3, CON-7, CON-14: the pack names what the run may use (what it is given, the
    sites its secrets are sent to, its MCP tools) and what its role needs but lacks; never
    a secret's value."""
    given = await delivery.given_for_run(session, None, view.run)
    sent = await sending.sites_for(session, view.run)
    tools = await mcp_calls.offered(session, view.run)
    lacking = needs.unmet_for(await needs.preview(session, view.project), view.role.slug)
    if not (given or sent or tools or lacking):
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
    for connection, sites in sent:
        lines.append(
            f"- {connection.name} (secret, sent for you to {', '.join(sites)}): "
            f"{connection.description}"
        )
    by_server: dict[str, list[str]] = {}
    for tool in tools:
        by_server.setdefault(tool.connection.name, []).append(tool.name)
    for server, names in by_server.items():
        lines.append(f"- {server} (MCP server): your tools {', '.join(names)}")
    if given:
        lines += [
            "",
            "Secrets are available to the commands you run. Never print, write or send a "
            "secret's value; Nightsquad replaces it with [secret: NAME] in everything you write.",
        ]
    if sent:
        lines += [
            "",
            "A secret sent for you is added by Nightsquad to your HTTPS requests to its sites: "
            "call the site without it. You never see its value.",
        ]
    if lacking:
        lines += ["", "Your role needs, and does not have yet:"]
        lines += [f"- {needs.describe(need)}" for need in lacking]
        lines.append("Ask the chairman for anything else with agent_request_access.")
    return "\n".join(lines)


context_pack.added_sections.append(context_section)
