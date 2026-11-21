"""The phase 2 exit demo on one real provider (LLM-2, LLM-8, P3, INV-6, GOV-2).

Skipped unless pytest is run with `--live` and `ANTHROPIC_API_KEY` is set, so the default
suite never calls a paid model. The key goes in by standard input and is then held only by
the server.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.acceptance.test_chat import Items, all_finished, first_reply, wait_for
from tests.acceptance.test_slim import Install
from tests.support import PASSWORD

KEY_VARIABLE = "ANTHROPIC_API_KEY"


def test_LLM_8_the_ceo_answers_on_a_real_provider_and_the_key_stays_in_the_server(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """LLM-2, LLM-8, P3, INV-6, GOV-2: with an Anthropic credential the CEO answers a chat
    message through the gateway; the run is metered by token kind; the key is in no
    sandbox file, no event and no server output."""
    key = os.environ.get(KEY_VARIABLE)
    if not request.config.getoption("--live") or not key:
        pytest.skip(f"needs --live and {KEY_VARIABLE}")
    install = Install(tmp_path / "data")
    install.env["CREWMIND_SANDBOX_MODE"] = "unisolated"
    for name in (KEY_VARIABLE, "ANTHROPIC_BASE_URL", "ANTHROPIC_API_BASE"):
        install.env.pop(name, None)
    try:
        setup = install.run("setup", "--slim", "--admin-email", "dom@example.com")
        install.start("--slim")
        password = f"{PASSWORD}\n"
        install.run("accept", "--link", setup["setup_link"], "--password-stdin", stdin=password)
        install.run("login", "--email", "dom@example.com", "--password-stdin", stdin=password)
        install.run(
            "credentials", "add", "--name", "main", "--provider", "anthropic", "--key-stdin",
            stdin=f"{key}\n",
        )  # fmt: skip
        project = install.run(
            "projects", "create", "--name", "Atlas", "--type", "deliver", "--goal", "Say hello."
        )["project_id"]
        install.run("models", "set-payer", "--project-id", project, "--credential", "main")
        install.run("chat", "quality", "--project-id", project, "--level", "fast")
        install.run("projects", "start", "--project-id", project)
        install.run(
            "chat", "send", "--project-id", project, "--body", "Reply with one word: ready."
        )

        def history() -> Items:
            return install.run("chat", "history", "--project-id", project)["items"]

        def runs_now() -> Items:
            return install.run("runs", "list", "--project-id", project)["items"]

        reply = wait_for(history, first_reply, "reply from the CEO")
        assert reply["body"].strip()
        wait_for(runs_now, all_finished, "finished run")
        budget = install.run("budget", "show", "--project-id", project)
        assert budget["spent"] > 0
        assert budget["by_kind"]["output"] > 0
        seats = install.run("models", "show", "--project-id", project)["seats"]
        assert seats[0]["paid_by"] == "main"

        events = install.run("record", "list", "--project-id", project, "--limit", "200")
        assert key not in str(events)
        for file in install.data_dir.rglob("*"):
            if file.is_file() and file.suffix not in (".sqlite", ".key"):
                assert key not in file.read_text(errors="ignore"), file
    finally:
        install.stop()
        output = install.output
    assert key not in output
