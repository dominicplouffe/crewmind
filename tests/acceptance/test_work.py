"""Phase 4 as real processes (WRK-5, WRK-7, INV-2, EXE-12): the reference competent squad
runs in `squad up --slim` with agents as separate processes, and the server's own job
runs the pinned check in a process with no token and no key."""

from __future__ import annotations

import json
from pathlib import Path

from tests.acceptance.test_chat import Items, wait_for
from tests.acceptance.test_slim import Install
from tests.support import PASSWORD

SCRIPTS = Path(__file__).parents[2] / "acceptance" / "scripts"


def test_INV_2_a_real_squad_finishes_a_job_the_platform_verifies(tmp_path: Path) -> None:
    """INV-2, WRK-5, WRK-7, P5: the CEO's process creates a task whose test fails first; the
    lead's process claims it, writes the file and completes it; the server runs the pinned
    check and only then is the task done, labelled verified."""
    finish_a_verified_job(tmp_path, {"NIGHTSQUAD_SANDBOX_MODE": "unisolated"})


def finish_a_verified_job(tmp_path: Path, environment: dict[str, str]) -> None:
    """The reference competent squad takes one task from planned to verified, in the
    sandbox mode the environment names."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    squad = json.loads((SCRIPTS / "competent-squad.json").read_text())
    for key, turns in squad.items():
        if key != "about":
            (scripts / f"{key.replace('/', '.')}.json").write_text(json.dumps(turns))
    install = Install(tmp_path / "data")
    install.env.update(environment)
    for name, value in environment.items():
        install.env[name] = value.replace("{port}", str(install.port))
    install.env["NIGHTSQUAD_MOCK_SCRIPT_DIR"] = str(scripts)
    install.env["NIGHTSQUAD_MEMORY_ENGINE"] = "in-process"
    try:
        setup = install.run("setup", "--slim", "--admin-email", "dom@example.com")
        install.start("--slim")
        password = f"{PASSWORD}\n"
        install.run("accept", "--link", setup["setup_link"], "--password-stdin", stdin=password)
        install.run("login", "--email", "dom@example.com", "--password-stdin", stdin=password)
        project = install.run(
            "projects", "create", "--name", "Atlas", "--type", "deliver", "--goal", "Ship it."
        )["project_id"]
        workspace = install.data_dir / "workspaces" / project
        workspace.mkdir(parents=True)
        (workspace / "check.sh").write_text("grep -q 41 report.txt\n")
        install.run("projects", "start", "--project-id", project)
        install.run("directives", "issue", "--project-id", project, "--instruction", "Plan it.")

        def tasks() -> Items:
            return install.run("tasks", "list", "--project-id", project)["items"]

        def created(items: Items) -> Items | None:
            return items or None

        def verified(items: Items) -> Items | None:
            return items if items and items[0]["state"] == "done" else None

        wait_for(tasks, created, "task from the CEO")
        # The CEO has planned; a later wake must not plan the same task again.
        (scripts / "CEO.work.json").write_text(json.dumps([{"text": "Nothing more to plan."}]))
        (task,) = wait_for(tasks, verified, "verified task")
        assert (task["label"], task["claimant"], task["failures"]) == ("verified", "build", 0)
        assert (workspace / "report.txt").read_text() == "Third quarter: 41 orders.\n"
    finally:
        install.stop()
