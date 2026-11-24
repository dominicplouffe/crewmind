"""Attacks on the outside world: the fetch guard, outside evidence, side effects, launches
and watches (WRK-12, WRK-16, WRK-17, INV-14, EXE-14, sections 7.15 and 7.16)."""

from __future__ import annotations

import pytest

from nightsquad.domain.work import fetch
from tests.attack.harness import assert_refused
from tests.attack.work_support import OBSERVABLE, Squad
from tests.conftest import FakeClock
from tests.site_support import PAGE, Site
from tests.support import App, agent_call, live_run


@pytest.mark.attack("WRK-12")
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8420/v1/projects/list",
        "http://localhost/",
        "http://10.0.0.5/",
        "http://192.168.1.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "file:///etc/passwd",
        "ftp://example.org/file",
        "http://user:secret@example.org/",
    ],
)
async def test_WRK_12_the_fetch_guard_reaches_no_inside_address(url: str) -> None:
    """WRK-12, EXE-14, P4: loopback, private, link-local and unspecified addresses, other
    schemes and addresses carrying credentials are refused before anything is sent."""
    with pytest.raises(fetch.FetchRefused):
        await fetch.fetch_public(url)


async def test_WRK_12_the_guard_rechecks_redirects_and_caps_size_and_time(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WRK-12: a public page is fetched; a redirect to an inside address, a body over 2 MB,
    an error status and a slow server are refused."""
    assert await fetch.fetch_public(site.url()) == PAGE
    with pytest.raises(fetch.FetchRefused, match="not a public address"):
        await fetch.fetch_public(site.url("/inside"))
    with pytest.raises(fetch.FetchRefused, match="larger than 2 MB"):
        await fetch.fetch_public(site.url("/big"))
    site.status = 503
    with pytest.raises(fetch.FetchRefused, match="status 503"):
        await fetch.fetch_public(site.url())
    site.status = 200
    monkeypatch.setattr(fetch, "FETCH_SECONDS", 1)
    with pytest.raises(fetch.FetchRefused, match="did not answer"):
        await fetch.fetch_public(site.url("/slow"))


@pytest.mark.attack("7.15")
async def test_WRK_12_evidence_counts_only_once_the_platform_verifies_it(
    app: App, site: Site
) -> None:
    """WRK-12, section 7.15: filed evidence is pending and counts for nothing. The platform
    fetches the page and verifies the quoted words are on it, then snapshots it. Words that
    are not there, an inside address and a missing task fail it; an agent cannot mark its
    own evidence verified. A failing fetch is retried 5 times, then fails closed."""
    squad = await Squad.start(app)
    task = await squad.task()
    orphan = await squad.call(
        "build-1", "agent.file_evidence", url=site.url(), quote="Order 4411 was delivered"
    )
    assert_refused(orphan, rule="WRK-12", code="evidence_needs_a_task")
    filed = await squad.ok(
        "build-1", "agent.file_evidence", url=site.url(), task_id=task["id"],
        quote="order 4411 was   DELIVERED",
    )  # fmt: skip
    assert filed["state"] == "pending"
    wrong = await squad.ok(
        "build-1", "agent.file_evidence", url=site.url(), task_id=task["id"],
        quote="Order 9999 was refunded",
    )  # fmt: skip
    inside = await squad.ok(
        "build-1", "agent.file_evidence", url="http://10.0.0.5/secret", task_id=task["id"],
        quote="anything at all",
    )  # fmt: skip
    for name in ("evidence.verify", "agent.verify_evidence"):
        forged = await squad.call("build-1", name, evidence_id=filed["id"])
        assert forged.status_code in (403, 404), name

    assert await app.work_jobs.verify_evidence() == 3
    listed = (await app.ok("evidence.list", squad.owner, project_id=squad.project))["items"]
    by_id = {item["id"]: item for item in listed}
    assert by_id[filed["id"]]["state"] == "verified"
    assert (by_id[wrong["id"]]["state"], by_id[wrong["id"]]["failure"]) == (
        "failed",
        "The quoted words are not on the page.",
    )
    assert by_id[inside["id"]]["state"] == "failed"
    assert "not a public address" in by_id[inside["id"]]["failure"]

    site.status = 503
    flaky = await squad.ok(
        "build-1", "agent.file_evidence", url=site.url(), task_id=task["id"],
        quote="Order 4411 was delivered",
    )  # fmt: skip
    for _ in range(4):
        assert await app.work_jobs.verify_evidence() == 0
    assert await app.work_jobs.verify_evidence() == 1
    final = (await app.ok("evidence.list", squad.owner, project_id=squad.project))["items"][-1]
    assert (final["id"], final["state"]) == (flaky["id"], "failed")


@pytest.mark.attack("INV-14")
@pytest.mark.attack("WRK-16")
@pytest.mark.attack("7.16-effect")
async def test_INV_14_a_side_effect_fires_once_across_retries(app: App, clock: FakeClock) -> None:
    """INV-14, WRK-16, section 7.16: a side effect is declared before it fires. When the run
    fails and is retried, the retry is shown what was declared, and declaring the same key
    again says do not fire. Only the declaring run or its retry finishes it, once."""
    squad = await Squad.start(app)
    declare = {"key": "email-supplier-quote", "what": "Email the supplier for a quote."}
    first = await squad.ok("build-1", "agent.declare_effect", **declare)
    assert (first["fire"], first["state"]) == (True, "declared")
    other = await squad.call(
        "build-2", "agent.finish_effect", key=declare["key"], fired=True, outcome="I sent it."
    )
    assert_refused(other, rule="WRK-16", code="not_your_side_effect")

    retry = await live_run(app, squad.project, seat="build-2")
    for _ in range(2):
        await squad.fail("build-1")
        clock.advance(seconds=100)
        retry = await live_run(app, squad.project, seat="build-1")
        pack = (await agent_call(app, retry.token, "agent.context")).json()["context_pack"]
        assert "[key email-supplier-quote] Email the supplier for a quote.: it was never" in pack
        again = await agent_call(app, retry.token, "agent.declare_effect", **declare)
        assert (again.json()["fire"], again.json()["id"]) == (False, first["id"])

    done = await agent_call(
        app, retry.token, "agent.finish_effect", key=declare["key"], fired=True,
        outcome="Sent; the supplier confirmed receipt.",
    )  # fmt: skip
    assert (done.json()["state"], done.json()["fired"]) == ("finished", True)
    twice = await agent_call(
        app, retry.token, "agent.finish_effect", key=declare["key"], fired=True, outcome="Again."
    )
    assert_refused(twice, rule="7.16-effect")
    effects = (await app.ok("launches.list", squad.owner, project_id=squad.project))["items"]
    assert len(effects) == 1


@pytest.mark.attack("WRK-17")
@pytest.mark.attack("7.16-watch")
async def test_WRK_17_a_launch_must_be_watched(app: App, clock: FakeClock) -> None:
    """WRK-17, section 7.16: a launch with no watch, a watch that runs too often, and a URL
    watch with nothing to expect are refused. A fired launch is watched at 0 tokens. When
    the watch fails the chat says so, the chairman is alarmed and the launching seat is
    woken; when it recovers it passes again. Only the launching seat, the CEO or the
    chairman retires it, which ends the watch."""
    squad = await Squad.start(app)
    launch = {"key": "landing-page-v1", "what": "Publish the landing page.", "launch": True}
    bare = await squad.call("build-1", "agent.declare_effect", **launch)
    assert_refused(bare, rule="WRK-17", code="launch_needs_a_watch")
    often = await squad.call(
        "build-1", "agent.declare_effect", **launch,
        watch={"kind": "command", "check": "test -f site-up.txt", "interval_minutes": 5},
    )  # fmt: skip
    assert_refused(often, rule="WRK-17", code="watch_too_often")
    blind = await squad.call(
        "build-1", "agent.declare_effect", **launch,
        watch={"kind": "url", "check": "https://example.org/", "interval_minutes": 30},
    )  # fmt: skip
    assert_refused(blind, rule="WRK-17", code="watch_needs_a_condition")

    watch = {"kind": "command", "check": "test -f site-up.txt", "interval_minutes": 15}
    run = await live_run(app, squad.project, seat="build-1")
    declared = (
        await agent_call(app, run.token, "agent.declare_effect", **launch, watch=watch)
    ).json()
    assert (declared["fire"], declared["watch"]) == (True, None)
    squad.write("site-up.txt", "up")
    live = await agent_call(
        app, run.token, "agent.finish_effect", key=launch["key"], fired=True,
        outcome="It is live.",
    )  # fmt: skip
    assert live.json()["watch"] == "passing"
    spent = (await app.ok("budget.show", squad.owner, project_id=squad.project))["spent"]

    assert await app.work_jobs.run_watches() == 1
    assert await app.work_jobs.run_watches() == 0
    (squad.workspace / "site-up.txt").unlink()
    clock.advance(minutes=16)
    await app.work_jobs.run_watches()
    listed = (await app.ok("launches.list", squad.owner, project_id=squad.project))["items"][0]
    assert listed["watch"] == "failing"
    history = (await app.ok("chat.history", squad.owner, project_id=squad.project))["items"]
    flags = [m for m in history if m["detail"] == {"kind": "watch failing", "alarm": True}]
    assert len(flags) == 1
    clock.advance(minutes=16)
    await app.work_jobs.run_watches()
    assert len([m for m in history if m["detail"] == {"kind": "watch failing", "alarm": True}]) == 1

    squad.write("site-up.txt", "up again")
    clock.advance(minutes=16)
    await app.work_jobs.run_watches()
    listed = (await app.ok("launches.list", squad.owner, project_id=squad.project))["items"][0]
    assert listed["watch"] == "passing"
    assert (await app.ok("budget.show", squad.owner, project_id=squad.project))["spent"] == spent

    stranger = await squad.call("build-2", "agent.retire_launch", effect_id=declared["id"])
    assert_refused(stranger, rule="WRK-17", code="not_your_launch")
    retired = await app.ok(
        "launches.retire", squad.owner, project_id=squad.project, effect_id=declared["id"]
    )
    assert (retired["state"], retired["watch"]) == ("retired", "ended")
    owner = await app.login(squad.owner.email)
    changes = [
        e["after"]["state"]
        for e in await app.events(owner, squad.project)
        if e["type"] == "side_effect.state_changed"
    ]
    assert changes == ["declared", "finished", "retired"]
    clock.advance(minutes=16)
    assert await app.work_jobs.run_watches() == 0
    again = await app.call(
        "launches.retire", squad.owner, project_id=squad.project, effect_id=declared["id"]
    )
    assert_refused(again, rule="7.16-effect")


async def test_WRK_3_an_explore_project_in_an_evidence_drought_makes_only_evidence_tasks(
    app: App, clock: FakeClock, site: Site
) -> None:
    """WRK-3, WRK-12: a young Explore project is never in drought. After
    `evidence.drought_after` with nothing verified, only evidence-producing tasks may be
    created, until evidence is verified."""
    squad = await Squad.start(app, type="explore")
    await squad.task()
    clock.advance(hours=25)
    dry = await squad.call("CEO", "agent.create_task", **OBSERVABLE, team="build")
    assert_refused(dry, rule="WRK-3", code="evidence_drought")
    probe = await squad.task(title="Ask five customers", outside_evidence=True)
    await squad.ok(
        "build-1", "agent.file_evidence", url=site.url(), task_id=probe["id"],
        quote="Order 4411 was delivered",
    )  # fmt: skip
    await app.work_jobs.verify_evidence()
    await squad.task(title="Write up what we learned", outside_evidence=True)
    await squad.task(title="Plan the next step")


async def test_WRK_16_a_side_effect_is_never_stranded(app: App) -> None:
    """WRK-16, WRK-17, section 7.16: the agent that declared a side effect finishes it in a
    later run when the declaring run is gone. If the agent never does, the chairman closes
    it as outcome unknown; a launch is then watched and can be retired. Another agent
    still cannot finish it, and an agent cannot close one as unknown."""
    squad = await Squad.start(app)
    await squad.ok("build-1", "agent.declare_effect", key="send-quote", what="Email the quote.")
    later = await squad.ok(
        "build-1", "agent.finish_effect", key="send-quote", fired=True, outcome="Sent it."
    )
    assert (later["state"], later["fired"]) == ("finished", True)

    watch = {"kind": "command", "check": "test -f up.txt", "interval_minutes": 15}
    launch = await squad.ok(
        "build-1", "agent.declare_effect", key="site-live", what="Publish the landing page.",
        launch=True, watch=watch,
    )  # fmt: skip
    ref = {"project_id": squad.project, "effect_id": launch["id"]}
    stuck = await app.call("launches.retire", squad.owner, **ref)
    assert_refused(stuck, rule="7.16-effect")
    other = await squad.call(
        "build-2", "agent.finish_effect", key="site-live", fired=True, outcome="I say it is up."
    )
    assert_refused(other, rule="WRK-16", code="not_your_side_effect")
    by_agent = await squad.call("build-1", "launches.close_unknown", **ref)
    assert by_agent.status_code in (401, 403, 404)

    closed = await app.ok("launches.close_unknown", squad.owner, **ref)
    assert (closed["state"], closed["fired"], closed["watch"]) == ("finished", None, "passing")
    assert "unknown" in closed["outcome"]
    assert_refused(await app.call("launches.close_unknown", squad.owner, **ref), rule="7.16-effect")
    retired = await app.ok("launches.retire", squad.owner, **ref)
    assert (retired["state"], retired["watch"]) == ("retired", "ended")
    changes = [
        e["after"]["state"]
        for e in await app.events(squad.owner, squad.project)
        if e["type"] == "side_effect.state_changed" and e["subject_id"] == str(launch["id"])
    ]
    assert changes == ["declared", "finished", "retired"]
