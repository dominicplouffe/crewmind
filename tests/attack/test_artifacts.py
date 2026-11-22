"""Attacks on artifacts and uploads (ART-1 to ART-9, CHAT-9, IF-3.9, INV-5)."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from tests.attack.harness import assert_refused
from tests.support import App, agent_call, live_run, running_project, wake

KB = 1024


def detail_kind(message: dict[str, Any]) -> str | None:
    detail: dict[str, Any] = message["detail"] or {}
    return detail.get("kind")


def b64(text: bytes) -> str:
    return base64.b64encode(text).decode()


@pytest.mark.attack("ART-9")
@pytest.mark.attack("ART-3")
async def test_ART_3_a_deliverable_has_a_plain_name_and_one_per_purpose(app: App) -> None:
    """ART-3, ART-9: an agent cannot publish a name with a path. A second deliverable for
    the same purpose must name what it supersedes or say why both are needed. Each
    publication for the chairman is announced in the chat with its opening lines."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner, **{"refusal.cap": 20})
    ceo = await live_run(app, project)
    for name in ("../escape.md", "docs/report.md", "a\\b.md", ".."):
        refused = await agent_call(
            app, ceo.token, "agent.publish_artifact", name=name, content="x", purpose="the report"
        )
        assert_refused(refused, rule="ART-9", code="name_has_path")
    first = await agent_call(
        app, ceo.token, "agent.publish_artifact",
        name="report.md", purpose="the report",
        content="# Findings\n\nDemand is real.\nThird line.\nFourth.",
    )  # fmt: skip
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "delivered"
    rival = await agent_call(
        app,
        ceo.token,
        "agent.publish_artifact",
        name="report-v2.md",
        content="y",
        purpose="the report",
    )
    envelope = assert_refused(rival, rule="ART-3", code="deliverable_exists")
    assert "report.md" in envelope.message
    replaced = await agent_call(
        app, ceo.token, "agent.publish_artifact",
        name="report-v2.md", content="# Better", purpose="the report", supersedes="report.md",
    )  # fmt: skip
    assert replaced.status_code == 200
    listed = await app.ok("artifacts.list", owner, project_id=project, kind="deliverable")
    assert [item["name"] for item in listed["items"]] == ["report-v2.md"]
    everything = await app.ok(
        "artifacts.list", owner, project_id=project, kind="deliverable", include_superseded=True
    )
    assert {item["name"]: item["superseded_by"] for item in everything["items"]} == {
        "report.md": "report-v2.md",
        "report-v2.md": None,
    }
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    announced = [m for m in history if detail_kind(m) == "deliverable"]
    assert "CEO published report.md (version 1)." in announced[0]["body"]
    assert "> # Findings\n> Demand is real.\n> Third line." in announced[0]["body"]
    assert "Fourth" not in announced[0]["body"]


@pytest.mark.attack("ART-5")
async def test_ART_5_agents_cannot_change_a_locked_artifact(app: App) -> None:
    """ART-5: after `/lock`, an agent's publish is refused, and a change made through the
    shell is put back when the run ends. Only a chair unlocks."""
    owner = await app.person("owner@example.com")
    observer = await app.person("observer@example.com")
    project = await running_project(app, owner)
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")
    app.script(
        "CEO",
        {"tools": [{"name": "write_file", "arguments": {"path": "plan.md", "content": "v1"}}]},
        {"text": "done"},
    )
    await wake(app, project)
    await app.work()
    assert (await app.ok("artifacts.read", owner, project_id=project, name="plan.md"))[
        "text"
    ] == "v1"
    assert_refused(
        await app.call("artifacts.lock", observer, project_id=project, name="plan.md"), rule="ACC-5"
    )
    assert (await app.ok("artifacts.lock", owner, project_id=project, name="plan.md"))[
        "locked"
    ] is True

    ceo = await live_run(app, project)
    refused = await agent_call(
        app, ceo.token, "agent.publish_artifact", name="plan.md", content="hacked", purpose="plan"
    )
    assert_refused(refused, rule="ART-5", code="artifact_locked")

    workspace = app.runtime.config.data_dir / "workspaces" / project
    (workspace / "plan.md").chmod(0o644)
    (workspace / "plan.md").write_text("changed through the shell")
    from crewmind.domain.execution import runs

    async with app.runtime.sessions() as session, session.begin():
        await runs.finish(session, ceo.run_id, ceo.runner_id, app.runtime.clock(), failed=False)
    app.script("CEO", {"text": "nothing"})
    await wake(app, project, kind="again")
    await app.work()
    assert (workspace / "plan.md").read_text() == "v1"
    page = await app.ok("artifacts.read", owner, project_id=project, name="plan.md")
    assert (page["text"], page["version"]) == ("v1", 1)
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert any("changed the locked file plan.md; it was put back" in m["body"] for m in history)


@pytest.mark.attack("ART-6")
async def test_ART_6_files_and_project_storage_stay_within_their_limits(app: App) -> None:
    """ART-6, ART-2: a file over the limit is refused; identical bytes are stored once; a
    flag is posted at 80% of the quota; at the quota, publishing is refused."""
    admin = await app.admin()
    owner = await app.person("owner@example.com")
    await app.ok(
        "settings.change_install", admin,
        changes={"upload.max_size": 1024 * KB, "artifact.max_size": 1024 * KB},
        reason="Small limits for the test.",
    )  # fmt: skip
    project = await running_project(app, owner)
    big = await app.call(
        "artifacts.upload",
        owner,
        project_id=project,
        name="big.bin",
        content_base64=b64(b"x" * (1025 * KB)),
    )
    envelope = assert_refused(big, rule="ART-6", code="file_too_large")
    assert "1,049,600 bytes and the limit per file is 1,048,576" in envelope.message

    for name in ("a.bin", "copy-of-a.bin"):
        await app.ok(
            "artifacts.upload",
            owner,
            project_id=project,
            name=name,
            content_base64=b64(b"a" * 1000),
        )
    listed = await app.ok("artifacts.list", owner, project_id=project)
    assert listed["storage_used"] == 1000
    again = await app.ok(
        "artifacts.upload", owner, project_id=project, name="a.bin", content_base64=b64(b"a" * 1000)
    )
    assert again["versions"] == 1

    from sqlalchemy import update

    from crewmind.storage.models import ArtifactVersion

    async with app.runtime.sessions() as session, session.begin():
        await session.execute(update(ArtifactVersion).values(size=20 * 1024**3 - 500))
    full = await app.call(
        "artifacts.upload",
        owner,
        project_id=project,
        name="more.bin",
        content_base64=b64(b"m" * 600),
    )
    assert_refused(full, rule="ART-6", code="storage_quota")


async def test_CHAT_9_an_upload_becomes_an_artifact_every_agent_can_read(app: App) -> None:
    """CHAT-9, ART-1, ART-7, ART-8, P4: an upload is an artifact of kind upload, versioned
    with a content hash and its author, shown in the chat, readable by any agent in 64 KB
    pages, and can be marked reference or example. A missing file is `exists: false`."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    text = ("line of the brief\n" * 5000).encode()
    await app.ok(
        "artifacts.upload", owner, project_id=project, name="brief.txt", content_base64=b64(text)
    )
    await app.ok(
        "artifacts.upload",
        owner,
        project_id=project,
        name="brief.txt",
        content_base64=b64(text + b"more"),
    )
    versions = await app.ok("artifacts.versions", owner, project_id=project, name="brief.txt")
    assert [v["version"] for v in versions["items"]] == [1, 2]
    assert versions["items"][0]["content_hash"] != versions["items"][1]["content_hash"]
    assert {v["author_kind"] for v in versions["items"]} == {"person"}
    marked = await app.ok(
        "artifacts.mark", owner, project_id=project, name="brief.txt", mark="example"
    )
    assert (marked["kind"], marked["mark"]) == ("upload", "example")
    history = (await app.ok("chat.history", owner, project_id=project))["items"]
    assert [m["detail"]["artifact"] for m in history if detail_kind(m) == "upload"] == [
        "brief.txt"
    ] * 2

    await app.ok("roster.hire_team", owner, project_id=project, team="research", role="Generalist")
    worker = await live_run(app, project, seat="research")
    page = (
        await agent_call(app, worker.token, "agent.read_artifact", name="brief.txt", version=1)
    ).json()
    assert (page["exists"], page["more"], len(page["text"])) == (True, True, 64 * KB)
    rest = (
        await agent_call(
            app, worker.token, "agent.read_artifact", name="brief.txt", version=1, offset=64 * KB
        )
    ).json()
    assert (rest["more"], len(rest["text"])) == (False, len(text) - 64 * KB)
    missing = await agent_call(app, worker.token, "agent.read_artifact", name="nope.txt")
    assert missing.status_code == 200
    assert missing.json()["exists"] is False


async def test_IF_3_9_a_large_upload_resumes_where_it_stopped(app: App) -> None:
    """IF-3.9, INV-5: a resumable upload takes chunks at the offset it has reached, tells a
    client where to resume, refuses another person, and becomes an artifact on finish.
    The download is the same bytes, never served as active content."""
    owner = await app.person("owner@example.com")
    outsider = await app.person("outsider@example.com")
    project = await running_project(app, owner)
    content = b"<script>alert(1)</script>" * 4000
    begun = await app.ok(
        "uploads.begin",
        owner,
        project_id=project,
        name="page.html",
        size=len(content),
        media_type="text/html",
    )
    path = f"/files/v1/uploads/{begun['upload_id']}"
    auth = {"Authorization": f"Bearer {owner.token}"}
    half = len(content) // 2
    async with app.client() as client:
        assert (await client.put(path, content=content[:half], headers=auth)).json()[
            "received"
        ] == half
        wrong = await client.put(path, params={"offset": 0}, content=content[:half], headers=auth)
        assert (wrong.status_code, wrong.json()["received"]) == (409, half)
        foreign = await client.put(
            path,
            params={"offset": half},
            content=b"x",
            headers={"Authorization": f"Bearer {outsider.token}"},
        )
        assert foreign.status_code == 404
        assert (await client.put(path, params={"offset": half}, content=b"x")).status_code == 401
    early = await app.call(
        "uploads.finish", owner, project_id=project, upload_id=begun["upload_id"]
    )
    assert_refused(early, rule="ART-6", code="upload_incomplete")
    status = await app.ok("uploads.status", owner, project_id=project, upload_id=begun["upload_id"])
    async with app.client() as client:
        await client.put(
            path, params={"offset": status["received"]}, content=content[half:], headers=auth
        )
    done = await app.ok("uploads.finish", owner, project_id=project, upload_id=begun["upload_id"])
    assert (done["kind"], done["size"]) == ("upload", len(content))

    download = f"/files/v1/projects/{project}/artifacts/page.html"
    async with app.client() as client:
        got = await client.get(download, headers=auth)
        hidden = await client.get(download, headers={"Authorization": f"Bearer {outsider.token}"})
    assert got.content == content
    assert got.headers["content-type"].startswith("text/plain")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert (hidden.status_code, hidden.json()["code"]) == (404, "project_not_found")


async def test_CHAT_9_an_upload_alone_starts_no_reply_and_costs_nothing(app: App) -> None:
    """CHAT-9, P8, INV-11: an upload shows in the chat but is not a question, so no run
    starts for it and no tokens are spent. The next message is answered as usual."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    await app.ok(
        "artifacts.upload", owner, project_id=project, name="notes.txt", content_base64="aGk="
    )
    assert await app.work() == 0
    assert (await app.ok("budget.show", owner, project_id=project))["spent"] == 0
    await app.ok("chat.send", owner, project_id=project, body="Please read the notes.")
    assert await app.work() == 1
