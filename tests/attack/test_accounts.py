"""Attacks on sign-in, sessions, tokens and links (ACC-1 to ACC-4, IF-3.7, 7.8 to 7.10)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from crewmind.domain.accounts import passwords
from crewmind.storage.models import BrowserSession, Link, Person, Token
from crewmind.surfaces.api.app import SESSION_COOKIE
from tests.attack.harness import assert_refused
from tests.conftest import FakeClock
from tests.support import PASSWORD, App

WRONG = "not the right password"


@pytest.mark.attack("ACC-1")
async def test_ACC_1_unknown_deactivated_and_wrong_password_logins_look_the_same(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ACC-1: the same answer, and the same work done: exactly one hash check each, so the
    time taken does not reveal which accounts exist."""
    admin = await app.admin()
    await app.person("real@example.com")
    gone = await app.person("gone@example.com")
    await app.ok("people.deactivate", admin, person_id=gone.person_id)
    await app.ok("people.invite", admin, email="invited@example.com", name="Invited")

    checks = 0
    real = passwords._hasher  # pyright: ignore[reportPrivateUsage]

    class Counting:
        def verify(self, stored: str, password: str) -> bool:
            nonlocal checks
            checks += 1
            return real.verify(stored, password)

    monkeypatch.setattr(passwords, "_hasher", Counting())
    answers: list[tuple[int, Any]] = []
    attempts = {
        "real@example.com": WRONG,
        "nobody@example.com": PASSWORD,
        "gone@example.com": PASSWORD,
        "invited@example.com": PASSWORD,
    }
    for email, password in attempts.items():
        checks = 0
        response = await app.call("auth.login", email=email, password=password)
        answers.append((response.status_code, response.json()))
        assert checks == 1, email
    assert all(answer == answers[0] for answer in answers)
    assert answers[0][0] == 401
    assert answers[0][1]["code"] == "login_failed"


@pytest.mark.attack("ACC-1")
async def test_ACC_1_ten_failures_lock_the_address_for_15_minutes(
    app: App, clock: FakeClock
) -> None:
    """ACC-1: after ten failures even the right password is refused, for known and unknown
    addresses alike, until 15 minutes have passed."""
    await app.person("real@example.com")
    for email in ("real@example.com", "nobody@example.com"):
        for _ in range(10):
            failed = await app.call("auth.login", email=email, password=WRONG)
            assert failed.json()["code"] == "login_failed"
        locked = await app.call("auth.login", email=email, password=PASSWORD)
        envelope = assert_refused(locked, rule="ACC-1", code="locked_out")
        assert "10 failed sign-ins" in envelope.message
    clock.advance(minutes=14)
    assert (
        await app.call("auth.login", email="real@example.com", password=PASSWORD)
    ).status_code == 403
    clock.advance(minutes=2)
    await app.login("real@example.com")


@pytest.mark.attack("ACC-1")
async def test_ACC_1_short_passwords_are_refused_and_passwords_are_hashed(app: App) -> None:
    """ACC-1, NFR-12: 11 characters is refused; the stored value is an Argon2id hash."""
    admin = await app.admin()
    invite = await app.ok("people.invite", admin, email="new@example.com", name="New")
    short = await app.call("auth.use_link", link=invite["link"], password="elevenchars")
    assert short.status_code == 422
    assert short.json()["rule"] == "ACC-1"
    await app.accept(invite["link"], "new@example.com")
    async with app.runtime.sessions() as session:
        stored = await session.scalar(
            select(Person.password_hash).where(Person.email == "new@example.com")
        )
    assert stored is not None
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


@pytest.mark.attack("ACC-2")
@pytest.mark.attack("7.10-session")
async def test_ACC_2_sessions_end_at_sign_out_password_change_idleness_and_age(
    app: App, clock: FakeClock
) -> None:
    """ACC-2, IF-3.7: an ended session's credential stops working on the server."""
    alice = await app.person("alice@example.com")

    signed_out = await app.login(alice.email)
    await app.ok("auth.logout", signed_out)
    assert (await app.call("auth.whoami", signed_out)).status_code == 401

    before_change = await app.login(alice.email)
    other = await app.login(alice.email)
    await app.ok(
        "auth.change_password", other, current_password=PASSWORD, new_password=PASSWORD + "!"
    )
    assert (await app.call("auth.whoami", before_change)).status_code == 401
    assert (await app.call("auth.whoami", other)).status_code == 401

    session = (await app.ok("auth.login", email=alice.email, password=PASSWORD + "!"))["session"]
    clock.advance(days=2, hours=23)
    await app.ok("auth.whoami", session)
    clock.advance(days=3, minutes=1)
    assert (await app.call("auth.whoami", session)).status_code == 401

    session = (await app.ok("auth.login", email=alice.email, password=PASSWORD + "!"))["session"]
    for _ in range(7):
        clock.advance(days=2)
        if (await app.call("auth.whoami", session)).status_code == 401:
            break
    else:
        pytest.fail("a session outlived 14 days")
    assert (await app.call("auth.whoami", session)).status_code == 401


@pytest.mark.attack("IF-3.7")
async def test_IF_3_7_a_browser_session_cannot_write_from_another_origin(app: App) -> None:
    """IF-3.7: a write carried by the session cookie from another site is refused. The same
    write from the app's own origin, or with a bearer token, is allowed."""
    alice = await app.person("alice@example.com")
    base = app.runtime.config.base_url
    async with app.client() as browser:
        login = await browser.post(
            "/v1/auth/login", json={"email": alice.email, "password": PASSWORD}
        )
        cookie = login.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert browser.cookies.get(SESSION_COOKIE)
        project = {"name": "Atlas", "type": "deliver", "goal": "Ship it."}
        foreign = await browser.post(
            "/v1/projects/create", json=project, headers={"Origin": "https://evil.example"}
        )
        assert_refused(foreign, rule="IF-3.7", code="cross_origin_write")
        own = await browser.post("/v1/projects/create", json=project, headers={"Origin": base})
        assert own.status_code == 200
        read = await browser.get("/v1/projects/list", headers={"Origin": "https://evil.example"})
        assert read.status_code == 200
        await browser.post("/v1/auth/logout", json={}, headers={"Origin": base})
        assert (await browser.get("/v1/auth/whoami")).status_code == 401


@pytest.mark.attack("ACC-3")
@pytest.mark.attack("7.10-token")
async def test_ACC_3_tokens_expire_are_named_and_are_stored_only_as_hashes(
    app: App, clock: FakeClock
) -> None:
    """ACC-3, NFR-12, section 7.10: no token lasts for ever or past its date, a revoked token
    is dead and cannot be revoked twice, and the value is never stored or shown again."""
    alice = await app.person("alice@example.com")
    for days in (0, 366, -1):
        refused = await app.call("tokens.mint", alice, name="bad", expires_in_days=days)
        assert_refused(refused, rule="ACC-3", code="token_expiry_out_of_range")
    assert (await app.call("tokens.mint", alice, name="")).status_code == 422

    minted = await app.ok("tokens.mint", alice, name="laptop")
    token = minted["token"]
    await app.ok("auth.whoami", token)
    listed = await app.ok("tokens.list", alice)
    assert token not in str(listed)
    assert listed["items"][0]["name"] == "laptop"
    async with app.runtime.sessions() as session:
        rows = (await session.execute(select(Token))).scalars().all()
        assert all(token not in str(vars(row)) for row in rows)

    clock.advance(days=29, hours=23)
    await app.ok("auth.whoami", token)
    clock.advance(hours=2)
    assert (await app.call("auth.whoami", token)).status_code == 401
    alice = await app.login(alice.email)
    assert (await app.ok("tokens.list", alice))["items"][0]["state"] == "expired"

    second = await app.ok("tokens.mint", alice, name="phone", expires_in_days=365)
    await app.ok("tokens.revoke", alice, token_id=second["token_id"])
    assert (await app.call("auth.whoami", second["token"])).status_code == 401
    twice = await app.call("tokens.revoke", alice, token_id=second["token_id"])
    assert_refused(twice, rule="7.10-token", code="transition_refused")

    mallory = await app.person("mallory@example.com")
    stolen = await app.call("tokens.revoke", mallory, token_id=minted["token_id"])
    assert stolen.status_code == 404


@pytest.mark.attack("ACC-4")
@pytest.mark.attack("7.9")
async def test_ACC_4_a_link_works_once_and_for_72_hours(app: App, clock: FakeClock) -> None:
    """ACC-4, section 7.9: a used, expired or invented link gets one and the same refusal."""
    used = await app.ok("people.invite", await app.admin(), email="one@example.com", name="One")
    await app.ok("auth.use_link", link=used["link"], password=PASSWORD)
    late = await app.ok("people.invite", await app.admin(), email="two@example.com", name="Two")
    clock.advance(hours=72, minutes=1)
    answers: list[Any] = []
    for link in (used["link"], late["link"], "http://127.0.0.1:8420/accept/cm_lnk_invented"):
        response = await app.call("auth.use_link", link=link, password=PASSWORD)
        assert_refused(response, rule="ACC-4", code="link_invalid")
        answers.append(response.json())
    assert answers[0] == answers[1] == answers[2]
    async with app.runtime.sessions() as session:
        assert all(
            used["link"].rsplit("/", 1)[-1] != row.token_hash
            for row in (await session.execute(select(Link))).scalars()
        )

    fresh = await app.ok("people.reset_link", await app.admin(), person_id=late["person_id"])
    clock.advance(hours=71)
    await app.accept(fresh["link"], "two@example.com")


@pytest.mark.attack("7.8")
async def test_7_8_account_states_change_only_as_listed(app: App) -> None:
    """Section 7.8: an invited person cannot be deactivated, an active one cannot be
    reactivated, and a deactivated one cannot be deactivated again."""
    admin = await app.admin()
    invited = await app.ok("people.invite", admin, email="new@example.com", name="New")
    refused = await app.call("people.deactivate", admin, person_id=invited["person_id"])
    assert_refused(refused, rule="7.8", code="transition_refused")
    active = await app.person("active@example.com")
    assert_refused(
        await app.call("people.reactivate", admin, person_id=active.person_id), rule="7.8"
    )
    await app.ok("people.deactivate", admin, person_id=active.person_id)
    assert_refused(
        await app.call("people.deactivate", admin, person_id=active.person_id), rule="7.8"
    )
    async with app.runtime.sessions() as session:
        live = await session.scalars(
            select(BrowserSession).where(
                BrowserSession.person_id == active.person_id, BrowserSession.state == "active"
            )
        )
        assert list(live) == []
    await app.ok("people.reactivate", admin, person_id=active.person_id)
    await app.login(active.email)
