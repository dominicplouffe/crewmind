"""The Founder on a real server, from the real terminal (section 13, IF-4.6, IF-4.7,
FND-12): a scripted model in place of a paid one, everything else as shipped."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.acceptance.test_slim import PASSWORD, Install
from tests.founder_support import BRIEF, DECISIONS, ROLE_WORDS, grades, propose, question, tool

pytestmark = pytest.mark.slow

QUICK_SECONDS_MOST = 120  # FND-12, section 1.3: quick mode in under 2 minutes


def draft(install: Install, *arguments: str, typed: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "crewmind", "draft", *arguments],
        env=install.env,
        input=typed,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def test_IF_4_6_a_project_is_drafted_in_the_terminal_and_quick_mode_takes_under_two_minutes(
    tmp_path: Path,
) -> None:
    """Section 13 (Founder), IF-4.6, IF-4.7, FND-1, FND-12, FND-13: `crewmind draft` asks
    each question with its recommended answer, Enter accepts it, the rest are accepted on
    request, the draft is rehearsed for real, and the chairman creates and starts the
    project from the terminal. Quick mode then creates and starts a second project in
    under two minutes. No paid model is called."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    decided = {**DECISIONS, "chairman_role": {"value": "Answers questions.", "quote": ROLE_WORDS}}
    turns = [
        propose(decisions=decided),
        tool("ask", questions=[question("finish_line")]),
        {"text": "Here is a first draft. What record shows the guide is finished?"},
        tool("rehearse_spec"),
        {"text": "I have rehearsed the draft."},
    ]
    (scripts / "founder.draft.json").write_text(json.dumps(turns))
    (scripts / "founder.grade.json").write_text(
        json.dumps([{"text": json.dumps(grades("reference-goal"))}])
    )
    install = Install(tmp_path / "data")
    install.env["CREWMIND_SANDBOX_MODE"] = "unisolated"
    install.env["CREWMIND_MOCK_SCRIPT_DIR"] = str(scripts)
    install.env["CREWMIND_MEMORY_ENGINE"] = "in-process"
    try:
        setup = install.run("setup", "--slim", "--admin-email", "dom@example.com")
        install.start("--slim")
        password = f"{PASSWORD}\n"
        install.run("accept", "--link", setup["setup_link"], "--password-stdin", stdin=password)
        install.run("login", "--email", "dom@example.com", "--password-stdin", stdin=password)
        install.run(
            "credentials", "add", "--name", "main", "--provider", "mock", "--key-stdin",
            stdin="sk-mock-0123456789\n",
        )  # fmt: skip

        talked = draft(install, "--brief", BRIEF, typed="\n/rest\ny\ny\n")
        assert talked.returncode == 0, talked.stderr + talked.stdout
        shown = talked.stdout
        assert "a. Yes, as recommended  (recommended)" in shown
        assert "Founder: Here is a first draft." in shown
        assert "The draft is ready. The ledger:" in shown
        assert "finish_line: Yes, as recommended (answer)" in shown
        assert "Started. The project is running." in shown
        projects = install.run("projects", "list")["items"]
        assert [(p["name"], p["state"]) for p in projects] == [
            ("Hollin Valley bird guide", "running")
        ]

        began = time.monotonic()
        quick = draft(install, "--quick", "--brief", BRIEF)
        took = time.monotonic() - began
        assert quick.returncode == 0, quick.stderr + quick.stdout
        assert took < QUICK_SECONDS_MOST, f"quick mode took {took:.0f} s"
        print(f"quick mode: {took:.1f} s")
        states = sorted(p["state"] for p in install.run("projects", "list")["items"])
        assert states == ["running", "running"]
        draftings = install.run("founder", "list")["items"]
        assert sorted(d["state"] for d in draftings) == ["created", "started"]
    finally:
        install.stop()
