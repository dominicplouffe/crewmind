"""Attacks on secrets given to the agent: delivery to the right run only, and masking
everywhere agent text comes back (CON-3, CON-4, CON-7, CON-8, CON-16, INV-6)."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import pytest
from sqlalchemy import select

from nightsquad.domain.connections import delivery
from nightsquad.domain.secrets.store import ensure_master_key
from nightsquad.gateway.protocol import CompletionRequest
from nightsquad.storage.models import ArtifactVersion, Event, Message, Run, RunStep
from tests.attack.test_connections import blog_project, seats
from tests.support import Actor, App, agent_call, live_run, quiet_start, wake

WP = "wp-given-password-7781-unguessable"
OTHER = "ceo-only-key-5512-unguessable"
CERT = "-----BEGIN KEY-----\ncert-body-3391-unguessable\n-----END KEY-----"


@pytest.fixture(autouse=True)
def master_key(app: App) -> None:
    ensure_master_key(app.runtime.config.master_key_file)


async def given_project(app: App, owner: Actor) -> tuple[str, str]:
    """A started blog project: the writer is given the WordPress password and a key file;
    a variable goes to every role; a key goes to the CEO only. Returns the project and the
    writer's seat name."""
    project = await blog_project(app, owner)
    found = await seats(app, project)
    writer = next(name for name, seat in found.items() if name != "CEO" and seat.kind != "reviewer")
    slug = "blog-writer"
    await app.ok(
        "connections.add_secret", owner, name="wordpress", description="WordPress password.",
        value=WP, delivery="given", env_name="WP_PASSWORD", project_id=project,
    )  # fmt: skip
    await app.ok(
        "connections.add_secret", owner, name="site-cert", description="Client certificate.",
        value=CERT, delivery="given", shape="file", env_name="SITE_CERT", project_id=project,
        roles=[slug],
    )  # fmt: skip
    await app.ok(
        "connections.add_variable", owner, name="region", description="Where readers are.",
        value="ca-east", project_id=project, roles=["*"],
    )  # fmt: skip
    await app.ok(
        "connections.add_secret", owner, name="ceo-key", description="For the CEO only.",
        value=OTHER, delivery="given", env_name="CEO_KEY", project_id=project, roles=["ceo"],
    )  # fmt: skip
    await app.ok("projects.start", owner, project_id=project)
    await quiet_start(app, project)
    return project, writer


def leaks(text: str) -> list[str]:
    forms = [WP, base64.b64encode(WP.encode()).decode(), "cert-body-3391", OTHER]
    return [form for form in forms if form in text]


async def stored_text(app: App) -> str:
    """Everything the platform stored that agent text could reach, as one text."""
    async with app.runtime.sessions() as session:
        parts: list[Any] = []
        parts += [step.data for step in await session.scalars(select(RunStep))]
        parts += [[m.body, m.detail] for m in await session.scalars(select(Message))]
        parts += [[e.before, e.after, e.detail] for e in await session.scalars(select(Event))]
        parts += [[r.context_pack, r.system_prompt] for r in await session.scalars(select(Run))]
        hashes = list(await session.scalars(select(ArtifactVersion.content_hash)))
    memory = app.runtime.services.memory
    parts += [row.text for row in getattr(memory, "_rows", {}).values()]
    blobs = [
        app.runtime.services.blobs.read(digest).decode("utf-8", "replace") for digest in hashes
    ]
    return json.dumps(parts, default=str) + "\n".join(blobs)


@pytest.mark.attack("CON-8")
@pytest.mark.attack("CON-7")
async def test_CON_8_a_given_secret_reaches_its_commands_and_nothing_else(
    app: App, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """CON-7, CON-8, CON-4, CON-16, INV-6: the writer's commands see its secret, its file
    and the variable; not the CEO's key. Everything it prints, encodes or writes comes back
    as [secret: NAME]: the model provider never receives a value, and no trace, file,
    message or record keeps one. The run's trace names what it was given."""
    owner = await app.person("owner@example.com")
    project, writer = await given_project(app, owner)
    sent: list[CompletionRequest] = []
    complete = app.runtime.mock.complete

    async def recording(request: CompletionRequest, **kwargs: Any) -> Any:
        sent.append(request)
        return await complete(request, **kwargs)

    monkeypatch.setattr(app.runtime.mock, "complete", recording)
    command = (
        'echo "pw=$WP_PASSWORD"; printf %s "$WP_PASSWORD" | base64; '
        'cat "$NIGHTSQUAD_SECRETS_DIR/SITE_CERT"; echo "region=$REGION ceo=[$CEO_KEY]"; '
        'echo "$WP_PASSWORD" > notes.txt'
    )
    app.script(
        writer, {"tools": [{"name": "shell", "arguments": {"command": command}}]}, {"text": "done"}
    )
    await wake(app, project, seat=writer)
    await app.work()

    said = json.dumps([request.model_dump(mode="json") for request in sent])
    assert "[secret: wordpress]" in said
    assert "[secret: site-cert]" in said
    assert "region=ca-east ceo=[]" in said
    assert leaks(said) == []
    assert leaks(await stored_text(app)) == []

    async with app.runtime.sessions() as session:
        given = list(
            await session.scalars(select(RunStep).where(RunStep.kind == "connections given"))
        )
        writer_run = await session.scalar(select(Run).where(Run.id == given[-1].run_id))
    names = {entry["name"] for entry in given[-1].data["given"]}
    assert names == {"wordpress", "site-cert", "region"}
    assert writer_run is not None
    assert writer_run.context_pack is not None
    assert "WP_PASSWORD" in writer_run.context_pack
    assert "ca-east" in writer_run.context_pack
    page = await app.ok("artifacts.read", owner, project_id=project, name="notes.txt")
    assert page["text"].strip() == "[secret: wordpress]"
    workspace = app.runtime.config.data_dir / "workspaces" / project
    assert WP not in (workspace / "notes.txt").read_text()
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert any("wordpress" in m["body"] and "notes.txt" in m["body"] for m in history)
    shown = await app.ok("connections.show", owner, connection="wordpress")
    assert shown["item"]["last_used_at"] is not None

    with caplog.at_level(logging.INFO):
        delivery.install_log_masking()
        logging.getLogger("nightsquad.test").warning("the provider said %s", WP)
    assert WP not in caplog.text
    assert "[secret: wordpress]" in caplog.text


@pytest.mark.attack("CON-8")
async def test_CON_8_an_agent_that_sends_a_value_on_purpose_leaves_no_copy(app: App) -> None:
    """CON-8, INV-6: a sandbox that calls the agent API or the gateway itself with the
    value, plain or encoded, in a post, a memory or a model request, is masked on the way
    in; the harness-only environment is never offered to the model as a tool."""
    owner = await app.person("owner@example.com")
    project, writer = await given_project(app, owner)
    run = await live_run(app, project, seat=writer)
    encoded = base64.urlsafe_b64encode(WP.encode()).decode().rstrip("=")
    posted = await agent_call(
        app, run.token, "agent.post_message", body=f"the password is {WP}", channel="team Desk"
    )
    # Refused (nobody else is in the room): the refusal keeps the arguments, masked.
    assert posted.status_code == 403, posted.text
    await agent_call(app, run.token, "agent.remember", text=f"remember {encoded}", scope="agent")
    async with app.client() as client:
        tools = (
            await client.get("/agent/v1/tools", headers={"Authorization": f"Bearer {run.token}"})
        ).json()
        await client.post(
            "/gateway/v1/complete",
            headers={"Authorization": f"Bearer {run.token}"},
            json={"system": "s", "messages": [{"role": "user", "content": f"key {WP}"}]},
        )
    assert "agent_environment" not in tools["paths"]
    assert "agent_context" not in tools["paths"]
    assert leaks(await stored_text(app)) == []
    assert "the password is [secret: wordpress]" in await stored_text(app)


@pytest.mark.attack("CON-4")
async def test_CON_4_a_run_is_given_only_what_its_role_is_granted(app: App) -> None:
    """CON-4, CON-7: the CEO is given its own key and the variable, never the writer's
    secret; a detached secret is gone from the next run; another project's run gets none."""
    owner = await app.person("owner@example.com")
    project, writer = await given_project(app, owner)
    ceo = await live_run(app, project)
    environment = (await agent_call(app, ceo.token, "agent.environment")).json()
    assert (environment["variables"], environment["files"]) == (
        {"REGION": "ca-east", "CEO_KEY": OTHER},
        {},
    )
    run = await live_run(app, project, seat=writer)
    mine = (await agent_call(app, run.token, "agent.environment")).json()
    assert mine["variables"] == {"WP_PASSWORD": WP, "REGION": "ca-east"}
    assert mine["files"] == {"SITE_CERT": CERT}

    await app.ok("connections.detach", owner, project_id=project, connection="site-cert")
    again = await live_run(app, project, seat=writer)
    assert (await agent_call(app, again.token, "agent.environment")).json()["files"] == {}

    other = await app.project(owner, name="Other")
    await app.ok("projects.start", owner, project_id=other)
    await quiet_start(app, other)
    elsewhere = await live_run(app, other)
    nothing = (await agent_call(app, elsewhere.token, "agent.environment")).json()
    assert (nothing["variables"], nothing["files"], nothing["proxy"]) == ({}, {}, None)


@pytest.mark.attack("CON-8")
async def test_CON_8_a_value_replaced_mid_run_stays_masked_for_the_run_that_holds_it(
    app: App,
) -> None:
    """CON-8: a run keeps the value it was handed even if the secret is replaced while it
    works; that value is still masked in everything the run sends."""
    owner = await app.person("owner@example.com")
    project, writer = await given_project(app, owner)
    run = await live_run(app, project, seat=writer)
    assert (await agent_call(app, run.token, "agent.environment")).json()["variables"][
        "WP_PASSWORD"
    ] == WP
    await app.ok(
        "connections.replace_secret", owner, connection="wordpress", value="a-new-value-0099-x"
    )
    await agent_call(app, run.token, "agent.remember", text=f"old one was {WP}", scope="agent")
    assert leaks(await stored_text(app)) == []
