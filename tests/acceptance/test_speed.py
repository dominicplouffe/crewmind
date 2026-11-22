"""The speed acceptance criterion (section 13, SPD-1, SPD-2, SPD-3), measured in real time
on a real server with a scripted crew in real processes."""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.test_chat import Items, wait_for
from tests.acceptance.test_slim import PASSWORD, Install

pytestmark = pytest.mark.slow

SCRIPTS = Path(__file__).parents[2] / "acceptance" / "scripts"
ALLOWED = 1.3  # section 13: no more than 1.3 x the chain's own time
LEASE_SECONDS_MOST = 10  # SPD-1: a ready run is leased within 10 seconds


def seconds(later: str, earlier: str) -> float:
    return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()


def test_SPD_1_the_deliver_reference_project_finishes_at_the_speed_of_its_longest_chain(
    tmp_path: Path,
) -> None:
    """Section 13 speed criterion, SPD-1, SPD-2, SPD-3, PRJ-4: the Deliver reference
    project, with `run.concurrency` 4, goes from start to ready in no more than 1.3 x (its
    longest dependency chain x the median scripted run duration), with independent pages
    built in parallel, and no run waits more than 10 seconds for a lease. Starting the
    project is all the chairman does."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    crew: dict[str, Any] = json.loads((SCRIPTS / "deliver-reference.json").read_text())
    chain_runs = int(crew.pop("chain_runs"))
    crew.pop("about")
    for key, turns in crew.items():
        (scripts / f"{key.replace('/', '.')}.json").write_text(json.dumps(turns))
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
        project = install.run(
            "projects", "create", "--name", "Site", "--type", "deliver",
            "--goal", "Publish a four-page site.",
        )["project_id"]  # fmt: skip
        began = time.monotonic()
        install.run("projects", "start", "--project-id", project)

        def status() -> Items:
            return [install.run("projects", "status", "--project-id", project)]

        def ready(items: Items) -> Items | None:
            return items if items[0]["state"] == "ready" else None

        wait_for(status, ready, "the project to become ready")
        watched = time.monotonic() - began
        changes = [
            event
            for event in install.run("record", "list", "--project-id", project, "--limit", "200")[
                "items"
            ]
            if event["type"] == "project.state_changed"
        ]
        at = {event["after"]["state"]: event["at"] for event in changes}
        took = seconds(at["ready"], at["running"])
        assert took <= watched

        runs = install.run("runs", "list", "--project-id", project, "--limit", "100")["items"]
        work = [run for run in runs if run["kind"] == "work" and run["state"] == "finished"]
        lengths = [seconds(run["ended_at"], run["started_at"]) for run in work]
        median = statistics.median(lengths)
        waits = [seconds(run["leased_at"], run["queued_at"]) for run in work]
        budget = ALLOWED * chain_runs * median
        report = (
            f"start to ready {took:.1f} s; {len(work)} runs, median {median:.1f} s; "
            f"chain of {chain_runs} runs allows {budget:.1f} s; longest lease wait "
            f"{max(waits):.1f} s"
        )
        print(report)
        for run in sorted(work, key=lambda run: run["queued_at"]):
            print(
                f"  {run['seat']:9} queued +{seconds(run['queued_at'], at['running']):5.1f} "
                f"leased +{seconds(run['leased_at'], at['running']):5.1f} "
                f"started +{seconds(run['started_at'], at['running']):5.1f} "
                f"ended +{seconds(run['ended_at'], at['running']):5.1f}"
            )
        assert took <= budget, report
        assert max(waits) <= LEASE_SECONDS_MOST, report

        plan = install.run("plan", "show", "--project-id", project)
        assert [item["state"] for item in plan["requirements"]] == ["met"] * 4
        assert plan["speed"]["to_first_task_seconds"] is not None
        pages = sorted(path.name for path in (install.data_dir / "workspaces" / project).iterdir())
        assert pages == ["about.txt", "contact.txt", "home.txt", "pricing.txt"]
        first: dict[str, datetime] = {}
        for run in sorted(work, key=lambda run: run["started_at"]):
            first.setdefault(run["seat"], datetime.fromisoformat(run["started_at"]))
        starts = sorted(first[seat] for seat in ("home", "about", "contact"))
        assert (starts[-1] - starts[0]).total_seconds() < median, report
    finally:
        install.stop()
