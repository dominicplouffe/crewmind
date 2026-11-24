"""Never left in silence, on a real server in real time (section 13, INV-24, P17)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.test_chat import Items, wait_for
from tests.acceptance.test_slim import PASSWORD, Install

pytestmark = pytest.mark.slow

ANSWER_SECONDS_MOST = 60  # INV-24: a reply or a platform status within 60 seconds


def test_INV_24_a_real_server_answers_with_the_provider_down_and_the_project_held(
    tmp_path: Path,
) -> None:
    """Section 13 never-silent criterion, INV-24, INV-20, P17: on a real server, a
    chairman message sent while every model call fails gets a platform status within 60
    seconds, and so does one sent after the project is held."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    down = [{"fail": "The provider is down."}] * 20
    (scripts / "CEO.chat.json").write_text(json.dumps(down))
    install = Install(tmp_path / "data")
    install.env["NIGHTSQUAD_SANDBOX_MODE"] = "unisolated"
    install.env["NIGHTSQUAD_MOCK_SCRIPT_DIR"] = str(scripts)
    install.env["NIGHTSQUAD_MEMORY_ENGINE"] = "in-process"
    try:
        setup = install.run("setup", "--slim", "--admin-email", "dom@example.com")
        install.start("--slim")
        password = f"{PASSWORD}\n"
        install.run("accept", "--link", setup["setup_link"], "--password-stdin", stdin=password)
        install.run("login", "--email", "dom@example.com", "--password-stdin", stdin=password)
        project = install.run(
            "projects", "create", "--name", "Site", "--type", "deliver",
            "--goal", "Publish a one-page site.",
        )["project_id"]  # fmt: skip
        install.run("projects", "start", "--project-id", project)

        def history() -> Items:
            return install.run("chat", "history", "--project-id", project, "--limit", "200")[
                "items"
            ]

        def answered(message: int) -> Any:
            def found(items: Items) -> Items | None:
                replies = [
                    item
                    for item in items
                    if item["reply_to"] == message and item["author_kind"] != "person"
                ]
                return replies or None

            return found

        for body, before in (("Are you there?", None), ("Can you still hear me?", "hold")):
            if before:
                install.run("projects", before, "--project-id", project)
            began = time.monotonic()
            asked = install.run("chat", "send", "--project-id", project, "--body", body)["id"]
            replies = wait_for(history, answered(asked), f"an answer to {body!r}")
            assert time.monotonic() - began <= ANSWER_SECONDS_MOST
            assert replies[0]["body"].strip()
    finally:
        install.stop()
