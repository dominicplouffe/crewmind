"""Attacks on tasks, checks and reviews (WRK-1 to WRK-9, WRK-13 to WRK-15, INV-2, INV-3,
INV-16, section 7.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update

from nightsquad.domain.work import checks
from nightsquad.storage.models import Seat, Task
from tests.attack.harness import assert_refused
from tests.attack.work_support import OBSERVABLE, Crew
from tests.conftest import FakeClock
from tests.support import App

COMMAND = {
    "title": "Produce the report file",
    "goal": "Write report.txt with the quarterly numbers.",
    "success_test": "test -f check.sh && sh check.sh",
    "test_kind": "command",
    "test_files": ["check.sh"],
}


@pytest.mark.attack("WRK-2")
async def test_WRK_2_only_the_ceo_creates_tasks_and_only_a_lead_splits_them(app: App) -> None:
    """WRK-2, P15: a worker, a lead and a person cannot create a top-level task. A lead
    creates subtasks only under a task it has claimed, for a member of its own team, one
    level deep. A suggestion creates no work and reaches the CEO."""
    crew = await Crew.start(app)
    for seat in ("build-1", "build-2", "Reviewer"):
        refused = await crew.call(seat, "agent.create_task", **OBSERVABLE, team="build")
        assert refused.status_code == 403, seat
    person = await app.call("agent.create_task", crew.owner, **OBSERVABLE, team="build")
    assert person.status_code in (401, 403, 404)
    assert_refused(
        await crew.call("CEO", "agent.create_task", **OBSERVABLE), rule="WRK-2",
        code="task_needs_a_team",
    )  # fmt: skip

    task = await crew.task()
    sub = {**OBSERVABLE, "parent_id": task["id"], "assignee": "build-2"}
    early = await crew.call("build-1", "agent.create_subtask", **sub)
    assert_refused(early, rule="WRK-2", code="not_your_task_to_split")
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    by_member = await crew.call("build-2", "agent.create_subtask", **sub)
    assert_refused(by_member, rule="WRK-2", code="not_your_task_to_split")
    outsider = await crew.call("build-1", "agent.create_subtask", **{**sub, "assignee": "CEO"})
    assert_refused(outsider, rule="WRK-2", code="assignee_not_in_your_team")
    child = await crew.ok("build-1", "agent.create_subtask", **sub)
    assert (child["parent_id"], child["state"]) == (task["id"], "ready")
    await crew.ok("build-2", "agent.claim_task", task_id=child["id"])
    deeper = await crew.call("build-2", "agent.create_subtask", **{**sub, "parent_id": child["id"]})
    assert_refused(deeper, rule="WRK-2", code="not_your_task_to_split")

    board = await crew.ok("build-2", "agent.suggest", text="We should also test on mobile.")
    assert len(board["open"]) == 2
    ceo = await crew.ok("CEO", "agent.board")
    assert ceo["suggestions"] == ["build-2: We should also test on mobile."]
    assert len((await app.ok("tasks.list", crew.owner, project_id=crew.project))["items"]) == 2


@pytest.mark.attack("WRK-3")
async def test_WRK_3_creation_stays_within_its_ceilings_and_floors(
    app: App, clock: FakeClock
) -> None:
    """WRK-3: the open-task ceiling, the 15-character test, the 6-hour not-before, and the
    Explore share of evidence-producing tasks."""
    crew = await Crew.start(app, settings={"tasks.max_open": 2})
    short = await crew.call(
        "CEO", "agent.create_task", **{**OBSERVABLE, "success_test": "It works."}, team="build"
    )
    assert_refused(short, rule="WRK-3", code="success_test_too_short")
    far = await crew.call(
        "CEO", "agent.create_task", **OBSERVABLE, team="build",
        not_before=(clock.now.replace(hour=16, minute=1)).isoformat(),
    )  # fmt: skip
    assert_refused(far, rule="WRK-3", code="not_before_too_far")
    await crew.task()
    await crew.task(title="A second task")
    full = await crew.call("CEO", "agent.create_task", **OBSERVABLE, team="build")
    refused = assert_refused(full, rule="WRK-3", code="too_many_open_tasks")
    assert "`tasks.max_open` is 2" in refused.message


async def test_WRK_3_explore_keeps_its_share_of_outside_evidence(app: App) -> None:
    """WRK-3: in Explore, once 3 tasks would be open, half must produce outside evidence."""
    crew = await Crew.start(app, type="explore")
    await crew.task()
    await crew.task(title="A second task")
    third = await crew.call("CEO", "agent.create_task", **OBSERVABLE, team="build")
    assert_refused(third, rule="WRK-3", code="too_little_outside_evidence")
    await crew.task(title="Interview five customers", outside_evidence=True)
    fourth = await crew.call("CEO", "agent.create_task", **OBSERVABLE, team="build")
    assert_refused(fourth, rule="WRK-3", code="too_little_outside_evidence")
    await crew.task(title="Run the landing page test", outside_evidence=True)


@pytest.mark.attack("WRK-4")
@pytest.mark.attack("INV-3")
async def test_WRK_4_a_task_is_claimed_only_by_whoever_it_is_for(
    app: App, clock: FakeClock
) -> None:
    """WRK-4, INV-3: only the team's lead claims a top-level task and only the assignee a
    subtask; one item at a time; not before its time; and never by the agent that wrote its
    success test while another agent could do the work."""
    crew = await Crew.start(app)
    later = clock.now.replace(hour=11)
    task = await crew.task(not_before=later.isoformat())
    early = await crew.call("build-1", "agent.claim_task", task_id=task["id"])
    assert_refused(early, rule="WRK-4", code="task_not_yet")
    clock.advance(hours=3)
    own = await crew.call("CEO", "agent.claim_task", task_id=task["id"])
    assert_refused(own, rule="WRK-4", code="not_yours_to_claim")
    for seat in ("build-2", "Reviewer"):
        assert_refused(
            await crew.call(seat, "agent.claim_task", task_id=task["id"]), rule="WRK-4",
            code="not_yours_to_claim",
        )  # fmt: skip
    claimed = await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    assert (claimed["state"], claimed["claimant"]) == ("claimed", "build-1")
    second = await crew.task(title="A second task")
    held = await crew.call("build-1", "agent.claim_task", task_id=second["id"])
    assert_refused(held, rule="WRK-4", code="one_item_at_a_time")
    again = await crew.call("build-1", "agent.claim_task", task_id=task["id"])
    assert_refused(again, rule="WRK-4", code="task_not_ready")

    sub = await crew.ok(
        "build-1", "agent.create_subtask", **OBSERVABLE, parent_id=task["id"], assignee="build-1"
    )
    self_test = await crew.call("build-1", "agent.claim_task", task_id=sub["id"])
    assert_refused(self_test, rule="INV-3", code="own_test")


async def test_INV_3_a_solo_ceo_may_do_its_own_work_and_it_is_labelled(app: App) -> None:
    """INV-3, WRK-6, WRK-9, WRK-15, P5: in a solo project the CEO claims the task it wrote.
    With independent read on, a reviewer still judges it. With it off, the close is
    labelled self-reported, never verified or reviewed. Independent read cannot be turned
    off once a team exists."""
    crew = await Crew.start(app, team=False)
    task = await crew.ok("CEO", "agent.create_task", **OBSERVABLE)
    await crew.ok("CEO", "agent.claim_task", task_id=task["id"])
    done = await crew.ok(
        "CEO", "agent.complete_task", task_id=task["id"], evidence="The summary is in s.md."
    )
    assert done["state"] == "review"
    assert (
        await crew.ok("Reviewer", "agent.review_task", task_id=task["id"], ok=True,
                      notes="Read it; all three interviewees are named.")
    )["label"] == "reviewed"  # fmt: skip

    off = {"changes": {"review.independent": False}, "reason": "Running solo, accepting the cost."}
    await app.ok("settings.change_project", crew.owner, project_id=crew.project, **off)
    second = await crew.ok("CEO", "agent.create_task", **OBSERVABLE)
    await crew.ok("CEO", "agent.claim_task", task_id=second["id"])
    closed = await crew.ok(
        "CEO", "agent.complete_task", task_id=second["id"], evidence="The summary is in s2.md."
    )
    assert (closed["state"], closed["label"]) == ("done", "self-reported")

    await app.ok(
        "settings.change_project", crew.owner, project_id=crew.project,
        changes={"review.independent": True}, reason="Hiring a team next.",
    )  # fmt: skip
    await crew.ok("CEO", "agent.hire_team", team="build", role="Generalist")
    refused = await app.call("settings.change_project", crew.owner, project_id=crew.project, **off)
    assert_refused(refused, rule="GOV-1", code="constraint_broken")


@pytest.mark.attack("WRK-5")
@pytest.mark.attack("INV-2")
@pytest.mark.attack("7.3")
async def test_WRK_5_a_test_must_fail_first_and_cannot_be_weakened(app: App) -> None:
    """WRK-5, WRK-7, INV-2, section 7.3: a test that passes before the work, a command that
    cannot fail, and a missing test file are refused. The check runs the pinned test file,
    so rewriting it does not help. Completing only sends the task to checking; no agent
    call makes it done. It is done, labelled verified, only when the platform's own run of
    the pinned command exits 0."""
    crew = await Crew.start(app)
    missing = await crew.call("CEO", "agent.create_task", **COMMAND, team="build")
    assert_refused(missing, rule="WRK-5", code="test_files_missing")
    crew.write("check.sh", "test -f report.txt\n")
    for command in ("true", ":", "exit 0", "echo done", "printf ok"):
        cannot = await crew.call(
            "CEO", "agent.create_task", **{**COMMAND, "success_test": command}, team="build"
        )
        assert_refused(cannot, rule="WRK-5", code="test_cannot_fail")
    crew.write("report.txt", "already here")
    passing = await crew.call("CEO", "agent.create_task", **COMMAND, team="build")
    assert_refused(passing, rule="WRK-5", code="test_passes_before_work")
    (crew.workspace / "report.txt").unlink()

    task = await crew.ok("CEO", "agent.create_task", **COMMAND, team="build")
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    crew.write("check.sh", "exit 0\n")
    sent = await crew.ok(
        "build-1", "agent.complete_task", task_id=task["id"], evidence="The check passes now."
    )
    assert (sent["state"], sent["label"]) == ("checking", "not yet checked")
    for name, extra in (
        ("agent.complete_task", {"evidence": "Really, it is done now."}),
        ("agent.review_task", {"ok": True, "notes": "Looks fine to me as it is."}),
        ("agent.claim_task", {}),
    ):
        for seat in ("build-1", "Reviewer", "CEO"):
            forced = await crew.call(seat, name, task_id=task["id"], **extra)
            assert forced.status_code == 403, (name, seat)
    assert (await crew.show(task["id"]))["state"] == "checking"

    assert await app.work_jobs.run_checks() == 1
    back = await crew.show(task["id"])
    assert (back["state"], back["failures"], back["label"]) == ("ready", 1, "not yet checked")
    assert back["attempts"][0]["result"] == "failed"
    stranger = await crew.call("build-2", "agent.claim_task", task_id=task["id"])
    assert stranger.status_code == 403

    crew.write("report.txt", "Q3: 41 orders")
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    await crew.ok(
        "build-1", "agent.complete_task", task_id=task["id"], evidence="report.txt holds Q3: 41."
    )
    await app.work_jobs.run_checks()
    done = await crew.show(task["id"])
    assert (done["state"], done["label"], done["failures"]) == ("done", "verified", 0)
    assert [a["result"] for a in done["attempts"]] == ["failed", "passed"]
    assert (crew.workspace / "check.sh").read_text() == "exit 0\n"
    late = await crew.call(
        "build-1", "agent.kill_task", task_id=task["id"], reason="Not needed now."
    )
    assert late.status_code == 403


@pytest.mark.attack("WRK-7")
async def test_WRK_7_a_check_has_no_token_no_key_and_no_way_to_reach_the_server(
    app: App, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """WRK-7, INV-6: the check's environment carries no token, key or server address, and
    the check cannot change the real workspace. On an unisolated host holding a
    container-runtime socket, an agent-written check is refused unless the operator
    allows it."""
    crew = await Crew.start(app)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-be-seen")
    crew.write(
        "check.sh",
        "env > seen.txt\n"
        "! env | grep -qiE 'nightsquad|token|api_key|sk-should' && test -f go.txt\n",
    )
    task = await crew.ok("CEO", "agent.create_task", **COMMAND, team="build")
    crew.write("go.txt", "go")
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    await crew.ok(
        "build-1", "agent.complete_task", task_id=task["id"], evidence="go.txt is in place now."
    )
    await app.work_jobs.run_checks()
    assert (await crew.show(task["id"]))["label"] == "verified"
    assert not (crew.workspace / "seen.txt").exists()

    socket = tmp_path / "docker.sock"
    socket.write_text("")
    monkeypatch.setattr(checks, "CONTAINER_SOCKETS", (socket,))
    crew.write("c2.sh", "test -f later.txt\n")
    unsafe = await crew.call(
        "CEO", "agent.create_task",
        **{**COMMAND, "success_test": "test -f c2.sh && sh c2.sh", "test_files": ["c2.sh"]},
        team="build",
    )  # fmt: skip
    assert_refused(unsafe, rule="WRK-7", code="checks_not_allowed_here")
    scope = await crew.call(
        "CEO", "agent.propose_requirement", text="The later file is in the workspace.",
        test_kind="command", success_test="test -f later.txt", estimate_runs=1,
    )  # fmt: skip
    assert_refused(scope, rule="WRK-7", code="checks_not_allowed_here")


@pytest.mark.attack("WRK-6")
@pytest.mark.attack("WRK-9")
async def test_WRK_9_nobody_reviews_their_own_work(app: App) -> None:
    """WRK-6, WRK-9, INV-3, WRK-15: only the claimant completes, with real evidence and no
    open subtask. An observable test goes to exactly one reviewer seat; the author, the
    CEO and a non-reviewer cannot give the verdict; notes are required. Ok closes it as
    reviewed."""
    crew = await Crew.start(app)
    task = await crew.task()
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    thin = await crew.call("build-1", "agent.complete_task", task_id=task["id"], evidence="Done.")
    assert_refused(thin, rule="WRK-6", code="evidence_too_thin")
    other = await crew.call(
        "build-2", "agent.complete_task", task_id=task["id"], evidence="I say it is finished."
    )
    assert_refused(other, rule="WRK-6", code="not_your_task")
    sub = await crew.ok(
        "build-1", "agent.create_subtask", **OBSERVABLE, parent_id=task["id"], assignee="build-2"
    )
    blocked = await crew.call(
        "build-1", "agent.complete_task", task_id=task["id"], evidence="The summary is written."
    )
    assert_refused(blocked, rule="WRK-6", code="subtasks_open")
    await crew.ok("build-1", "agent.kill_task", task_id=sub["id"], reason="Doing it myself.")

    sent = await crew.ok(
        "build-1", "agent.complete_task", task_id=task["id"], evidence="The summary is in s.md."
    )
    assert sent["state"] == "review"
    verdict = {"task_id": task["id"], "ok": True, "notes": "Read it, all three are named."}
    for seat, rule in (("build-1", "INV-3"), ("CEO", "INV-3"), ("build-2", "WRK-9")):
        assert_refused(await crew.call(seat, "agent.review_task", **verdict), rule=rule)
    short = await crew.call("Reviewer", "agent.review_task", **{**verdict, "notes": "ok"})
    assert_refused(short, rule="WRK-9", code="notes_too_short")
    assert (await crew.ok("Reviewer", "agent.board"))["yours"][0]["id"] == task["id"]
    done = await crew.ok("Reviewer", "agent.review_task", **verdict)
    assert (done["state"], done["label"]) == ("done", "reviewed")
    twice = await crew.call("Reviewer", "agent.review_task", **verdict)
    assert twice.status_code == 403


@pytest.mark.attack("WRK-8")
async def test_WRK_8_three_failures_block_a_task_and_a_repeat_alarms(app: App) -> None:
    """WRK-8, WRK-3: a rejected review returns the task, reserved, with its history. The
    third failure blocks it and tells the CEO. A second task dying on the same command
    alarms the chairman, and a third task with that test is refused: the check is the
    suspect. When the reviewer seat is gone, the platform staffs it again so the work is
    still read."""
    crew = await Crew.start(app)
    task = await crew.task()
    back: dict[str, Any] = {}
    for attempt in range(1, 4):
        await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
        await crew.ok(
            "build-1", "agent.complete_task", task_id=task["id"], evidence="The summary is in s.md."
        )
        back = await crew.ok(
            "Reviewer", "agent.review_task", task_id=task["id"], ok=False,
            notes="Only two of the three interviewees are named.",
        )  # fmt: skip
        assert back["failures"] == attempt
    assert back["state"] == "blocked"
    assert (await crew.ok("CEO", "agent.board"))["open"][0]["reason"] == "the review failed 3 times"

    crew.write("check.sh", "test -f never.txt\n")
    dead: list[int] = []
    for _ in range(2):
        command = await crew.ok("CEO", "agent.create_task", **COMMAND, team="build")
        for _ in range(3):
            await crew.ok("build-1", "agent.claim_task", task_id=command["id"])
            await crew.ok(
                "build-1", "agent.complete_task", task_id=command["id"], evidence="It should pass."
            )
            await app.work_jobs.run_checks()
        dead.append(command["id"])
        assert (await crew.show(command["id"]))["state"] == "blocked"
    history = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
    alarms = [m for m in history if m["detail"] == {"kind": "check suspect", "alarm": True}]
    assert len(alarms) == 1
    assert f"Task {dead[1]}" in alarms[0]["body"]
    suspect = await crew.call("CEO", "agent.create_task", **COMMAND, team="build")
    assert_refused(suspect, rule="WRK-3", code="check_is_the_suspect")

    for task_id in (task["id"], *dead):
        await crew.ok("CEO", "agent.kill_task", task_id=task_id, reason="Re-planning the work.")
    unread = await crew.task(title="One more summary")
    await crew.ok("build-1", "agent.claim_task", task_id=unread["id"])
    async with app.runtime.sessions() as session, session.begin():
        await session.execute(
            update(Seat).where(Seat.kind == "reviewer").values(state="stood down")
        )
    read = await crew.ok(
        "build-1", "agent.complete_task", task_id=unread["id"], evidence="The summary is in s3.md."
    )
    assert read["state"] == "review"
    names = (await app.ok("roster.show", crew.owner, project_id=crew.project))["seats"]
    assert [seat["state"] for seat in names if seat["kind"] == "reviewer"] == ["active"]


async def test_WRK_9_with_no_reader_but_the_author_a_task_closes_unread(app: App) -> None:
    """WRK-9, INV-3, WRK-15: when the only reviewer seat is the one that did the work, there
    is nobody to read it. The task closes unread, and says so; it is never called reviewed."""
    from nightsquad.domain.work import reviews, tasks
    from nightsquad.domain.work.model import TaskState

    crew = await Crew.start(app)
    task = await crew.task()
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    async with app.runtime.sessions() as session, session.begin():
        reviewer = await session.scalar(select(Seat).where(Seat.kind == "reviewer"))
        row = await session.get(Task, task["id"])
        assert reviewer is not None
        assert row is not None
        row.claimant_id = reviewer.id
        tasks.move(session, row, TaskState.REVIEW, tasks.WORK_JOB, app.runtime.clock())
        await reviews.assign(session, row, app.runtime.clock())
    closed = await crew.show(task["id"])
    assert (closed["state"], closed["label"]) == ("closed unread", "closed unread")


@pytest.mark.attack("WRK-14")
async def test_WRK_14_only_the_claimant_blocks_and_only_the_owner_kills(app: App) -> None:
    """WRK-14: only the claimant blocks, with a reason, and the CEO is told. The CEO kills
    top-level tasks and a lead its own subtasks; killing a task kills its open subtasks.
    There is no unblock."""
    crew = await Crew.start(app)
    task = await crew.task()
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    sub = await crew.ok(
        "build-1", "agent.create_subtask", **OBSERVABLE, parent_id=task["id"], assignee="build-2"
    )
    for seat in ("build-2", "CEO"):
        refused = await crew.call(
            seat, "agent.block_task", task_id=task["id"], reason="I think it is stuck."
        )
        assert_refused(refused, rule="WRK-14", code="not_your_task")
    vague = await crew.call("build-1", "agent.block_task", task_id=task["id"], reason="stuck")
    assert_refused(vague, rule="WRK-14", code="reason_too_short")
    for seat, target in (("build-1", task["id"]), ("build-2", sub["id"]), ("CEO", sub["id"])):
        refused = await crew.call(
            seat, "agent.kill_task", task_id=target, reason="No longer needed at all."
        )
        assert_refused(refused, rule="WRK-14", code="not_yours_to_kill")

    blocked = await crew.ok(
        "build-1", "agent.block_task", task_id=task["id"], reason="The source data is missing."
    )
    assert (blocked["state"], blocked["claimant"]) == ("blocked", None)
    for name in ("agent.claim_task", "agent.complete_task"):
        stuck = await crew.call("build-1", name, task_id=task["id"], evidence="Trying again now.")
        assert stuck.status_code == 403
    killed = await crew.ok(
        "CEO", "agent.kill_task", task_id=task["id"], reason="Re-issuing with the data."
    )
    assert killed["state"] == "killed"
    assert (await crew.show(sub["id"]))["state"] == "killed"


@pytest.mark.attack("INV-16")
async def test_INV_16_a_claim_with_no_live_run_returns_to_ready(app: App, clock: FakeClock) -> None:
    """INV-16, WRK-4: a claimed task whose claimant has had no live run for 2 x
    `run.timeout` goes back to ready, and its lead is woken. A claim with a live run stays."""
    crew = await Crew.start(app)
    task = await crew.task()
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    clock.advance(hours=4)
    await app.work_jobs.keep_work_moving()
    assert (await crew.show(task["id"]))["state"] == "claimed"

    await crew.ok("build-2", "agent.board")
    async with app.runtime.sessions() as session, session.begin():
        lead = await session.scalar(select(Seat.id).where(Seat.name == "build-1"))
        from nightsquad.storage.models import Run

        await session.execute(
            update(Run).where(Run.seat_id == lead).values(state="finished", ended_at=clock.now)
        )
    clock.advance(hours=2)
    await app.work_jobs.keep_work_moving()
    assert (await crew.show(task["id"]))["state"] == "claimed"
    clock.advance(hours=2)
    await app.work_jobs.keep_work_moving()
    back = await crew.show(task["id"])
    assert (back["state"], back["claimant"]) == ("ready", None)
    again = await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    assert again["state"] == "claimed"


@pytest.mark.attack("WRK-13")
async def test_WRK_13_sampled_closes_are_audited_by_the_chairman_only(
    app: App, clock: FakeClock
) -> None:
    """WRK-13, WRK-15: every observable close is considered once. A drawn one waits for the
    chairman, who passes or fails it once; nobody else can. A failure reopens nothing and
    tells the CEO. An unjudged sample expires as not reviewed."""
    crew = await Crew.start(app, settings={"audit.sample_rate": 100})
    observer = await app.person("observer@example.com")
    await app.ok(
        "members.add", crew.owner, project_id=crew.project, email=observer.email, role="observer"
    )
    ids: list[int] = []
    for number in range(2):
        task = await crew.task(title=f"Summary number {number}")
        await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
        await crew.ok(
            "build-1", "agent.complete_task", task_id=task["id"], evidence="It is in the folder."
        )
        await crew.ok(
            "Reviewer", "agent.review_task", task_id=task["id"], ok=True,
            notes="Read it and it meets the test.",
        )  # fmt: skip
        ids.append(task["id"])
    audits: dict[str, Any] = await app.ok("audits.list", observer, project_id=crew.project)
    assert (audits["considered"], audits["drawn"]) == (2, 2)
    first, second = audits["items"]
    verdict = {"project_id": crew.project, "audit_id": first["id"], "verdict": "failed"}
    assert (await app.call("audits.settle", observer, **verdict)).status_code == 403
    by_agent = await crew.call("CEO", "audits.settle", **verdict)
    assert by_agent.status_code in (401, 403, 404)
    failed = await app.ok("audits.settle", crew.owner, **verdict, note="It names two, not three.")
    assert failed["verdict"] == "failed"
    settled = [
        e for e in await app.events(crew.owner, crew.project) if e["type"] == "audit.settled"
    ]
    assert settled[0]["after"] == {"verdict": "failed", "task": ids[0]}
    shown = await crew.show(ids[0])
    assert (shown["state"], shown["label"], shown["audit"]) == ("done", "reviewed", "failed")
    assert (await crew.show(ids[1]))["audit"] == "waiting"
    assert_refused(
        await app.call("audits.settle", crew.owner, **verdict), rule="WRK-13",
        code="audit_already_settled",
    )  # fmt: skip

    clock.advance(hours=49)
    await app.work_jobs.keep_work_moving()
    owner = await app.login(crew.owner.email)
    items = (await app.ok("audits.list", owner, project_id=crew.project))["items"]
    assert [i["verdict"] for i in items] == ["failed", "not reviewed"]
    async with app.runtime.sessions() as session:
        assert (
            await session.scalar(select(Task.state).where(Task.id == second["task_id"])) == "done"
        )


async def test_EXE_15_the_board_is_in_each_agents_context(app: App) -> None:
    """EXE-15, WRK-2, WRK-8: a run's context pack shows what the agent holds with its
    attempt history, what it may claim and what waits for its review; the CEO sees every
    open task and the team's suggestions, which are handed to its work run once."""
    from tests.support import agent_call, live_run

    crew = await Crew.start(app)
    task = await crew.task()
    await crew.ok("build-2", "agent.suggest", text="We should also interview two churned users.")

    async def pack(seat: str) -> str:
        run = await live_run(app, crew.project, seat=seat)
        return (await agent_call(app, run.token, "agent.context")).json()["context_pack"]

    lead = await pack("build-1")
    assert f"Ready for you to claim (agent_claim_task):\n- [task {task['id']}, ready]" in lead
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    await crew.ok(
        "build-1", "agent.complete_task", task_id=task["id"], evidence="The summary is in s.md."
    )
    reviewer = await pack("Reviewer")
    assert f"Waiting for your review:\n- [task {task['id']}] Write the summary" in reviewer
    assert "The author's evidence: The summary is in s.md." in reviewer
    await crew.ok(
        "Reviewer", "agent.review_task", task_id=task["id"], ok=False,
        notes="It names only two interviewees.",
    )  # fmt: skip
    await crew.ok("build-1", "agent.claim_task", task_id=task["id"])
    again = await pack("build-1")
    assert f"You hold task {task['id']}: Write the summary" in again
    assert "It has failed 1 of 3 times:\n  attempt 1: failed - It names only two" in again

    ceo = await pack("CEO")
    assert f"Open tasks:\n- [task {task['id']}, claimed] Write the summary" in ceo
    assert "- build-2: We should also interview two churned users." in ceo
    assert "churned users" not in await pack("CEO")


@pytest.mark.attack("EXE-16")
async def test_EXE_16_stalled_work_wakes_the_ceo_and_alarms_once(
    app: App, clock: FakeClock
) -> None:
    """EXE-16: with tasks open and no work run started for `stall.after`, the CEO is woken
    and the chairman gets one alarm naming the cause. A held project is explained by its
    hold and does not alarm. The guard clears when work starts again."""
    crew = await Crew.start(app)
    await crew.task()
    clock.advance(minutes=30)
    await app.work_jobs.keep_work_moving()
    await app.ok("projects.hold", crew.owner, project_id=crew.project)
    clock.advance(minutes=45)
    await app.work_jobs.keep_work_moving()

    def stalls(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [m for m in history if m["detail"] == {"kind": "stalled", "alarm": True}]

    async def history() -> list[dict[str, Any]]:
        return (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]

    assert stalls(await history()) == []
    await app.ok("projects.resume", crew.owner, project_id=crew.project)
    await app.work_jobs.keep_work_moving()
    await app.work_jobs.keep_work_moving()
    (alarm,) = stalls(await history())
    assert "No work run has started for 60 minutes while tasks are open (1 ready)." in alarm["body"]

    await crew.ok("build-1", "agent.board")
    await app.work_jobs.keep_work_moving()
    clock.advance(minutes=10)
    await app.work_jobs.keep_work_moving()
    assert len(stalls(await history())) == 1


@pytest.mark.attack("GOV-7")
async def test_GOV_7_spinning_drops_concurrency_to_one_until_something_changes(app: App) -> None:
    """GOV-7: after `spin.window` work runs that change no task and publish no file, the
    project is spinning: the chat says so once and it may run one work run at a time. It
    clears when a run changes work state."""
    from nightsquad.domain.work import board

    crew = await Crew.start(app, settings={"spin.window": 3})

    async def spinning_lines() -> int:
        history = (await app.ok("chat.history", crew.owner, project_id=crew.project))["items"]
        return len([m for m in history if m["detail"] == {"kind": "spinning"}])

    async def limit() -> int:
        async with app.runtime.sessions() as session:
            return await board.concurrency_limit(session, crew.project, 4)

    await crew.ok("CEO", "agent.board")
    await crew.ok("CEO", "agent.board")
    await app.work_jobs.keep_work_moving()
    assert (await spinning_lines(), await limit()) == (0, 4)
    await crew.ok("CEO", "agent.board")
    await app.work_jobs.keep_work_moving()
    await app.work_jobs.keep_work_moving()
    assert (await spinning_lines(), await limit()) == (1, 1)

    await crew.task()
    await crew.finish("CEO")
    await app.work_jobs.keep_work_moving()
    assert (await spinning_lines(), await limit()) == (1, 4)


@pytest.mark.attack("WRK-5")
async def test_WRK_5_work_done_in_a_pinned_test_file_is_named_as_the_reason_it_cannot_pass(
    app: App,
) -> None:
    """WRK-5, WRK-8: a task whose author pinned the very file the work must change can
    never pass, because every check puts the pinned file back. The failed check says so in
    plain words to the worker, and the CEO is told at once, so nobody tries it again blind."""
    from sqlalchemy import select

    from nightsquad.storage.models import Notice

    crew = await Crew.start(app)
    crew.write("tool.sh", "exit 1\n")
    pinned = {**COMMAND, "success_test": "test -f tool.sh && sh tool.sh", "test_files": ["tool.sh"]}
    made = await crew.ok("CEO", "agent.create_task", **pinned, team="build")
    await crew.ok("build-1", "agent.claim_task", task_id=made["id"])
    crew.write("tool.sh", "exit 0\n")
    await crew.ok(
        "build-1", "agent.complete_task", task_id=made["id"], evidence="tool.sh now exits 0."
    )
    await app.work_jobs.run_checks()

    task = await crew.show(made["id"])
    assert (task["state"], task["failures"]) == ("ready", 1)
    assert task["check_output"].startswith("The check puts the pinned test files back")
    assert "tool.sh" in task["check_output"]
    async with app.runtime.sessions() as session:
        told = list(await session.scalars(select(Notice).where(Notice.kind == "task cannot pass")))
    assert len(told) == 1
    assert told[0].urgent is True
