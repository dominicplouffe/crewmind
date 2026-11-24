"""Attacks on who may see and call what (INV-5, IF-3.2, ACC-5, IF-4.2, section 7.11)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from nightsquad.catalog import Surface, catalog
from nightsquad.catalog.caller import Authority, Caller, CallerKind, InstanceRole
from nightsquad.catalog.operation import PROJECT_FIELD
from nightsquad.catalog.refusal import Refusal
from nightsquad.catalog.surfaces import exposed_on
from nightsquad.storage.models import Membership
from nightsquad.surfaces.api.app import route_path
from tests.attack.harness import assert_refused
from tests.conftest import FakeClock
from tests.support import App, sample_input


def project_operations() -> list[str]:
    return [o.name for o in catalog if PROJECT_FIELD in o.input.model_fields]


def guarded_operations() -> list[str]:
    return [
        o.name
        for o in catalog
        if o.authority is not Authority.ANYONE and exposed_on(o, Surface.API)
    ]


@pytest.mark.attack("INV-5")
async def test_INV_5_a_project_you_cannot_see_answers_like_one_that_does_not_exist(
    app: App,
) -> None:
    """INV-5, IF-3.3: for every operation that names a project, an outsider gets the same
    status and body for a real project as for a random id. The test walks the catalog."""
    owner = await app.person("owner@example.com")
    outsider = await app.person("outsider@example.com")
    real = await app.project(owner)
    assert len(project_operations()) >= 15
    for name in project_operations():
        operation = catalog.get(name)
        if operation.authority is Authority.ADMIN or not exposed_on(operation, Surface.API):
            continue
        answers: list[tuple[int, Any]] = []
        for project_id in (real, uuid.uuid4().hex):
            values = sample_input(operation.input, project_id=project_id)
            response = await app.call(name, outsider, **values)
            answers.append((response.status_code, response.json()))
        assert answers[0] == answers[1], name
        assert answers[0][0] == 404, name
        assert answers[0][1]["code"] == "project_not_found", name


@pytest.mark.attack("INV-5")
@pytest.mark.attack("ACC-5")
async def test_ACC_5_a_removed_member_loses_the_project_on_their_next_request(app: App) -> None:
    """ACC-5, INV-5: removal takes effect on the member's next request, with the same token."""
    owner = await app.person("owner@example.com")
    guest = await app.person("guest@example.com")
    project = await app.project(owner)
    await app.ok("members.add", owner, project_id=project, email=guest.email, role="co-chair")
    await app.ok("projects.status", guest, project_id=project)
    await app.ok("members.remove", owner, project_id=project, person_id=guest.person_id)
    response = await app.call("projects.status", guest, project_id=project)
    assert response.status_code == 404
    assert response.json()["code"] == "project_not_found"


@pytest.mark.attack("IF-3.2")
async def test_IF_3_2_every_guarded_route_refuses_callers_without_a_valid_credential(
    app: App, clock: FakeClock
) -> None:
    """IF-3.2, NFR-11: the test walks every route. No credential, a forged token, a revoked
    token, an expired token, an ended session and a deactivated person's token are all
    refused before the handler."""
    admin = await app.admin()
    victim = await app.person("victim@example.com")
    project = await app.project(victim)
    revoked = await app.ok("tokens.mint", victim, name="revoked")
    await app.ok("tokens.revoke", victim, token_id=revoked["token_id"])
    expired = await app.ok("tokens.mint", victim, name="short", expires_in_days=1)
    ended = await app.login(victim.email)
    await app.ok("auth.logout", ended)
    gone = await app.person("gone@example.com")
    gone_token = (await app.ok("tokens.mint", gone, name="mine"))["token"]
    await app.ok("people.deactivate", admin, person_id=gone.person_id)
    clock.advance(days=2)
    victim = await app.login(victim.email)
    credentials = {
        "none": None,
        "forged": "ns_pat_" + "x" * 43,
        "revoked": revoked["token"],
        "expired": expired["token"],
        "ended session": ended.token,
        "deactivated": gone_token,
        "deactivated session": gone.token,
    }
    assert len(guarded_operations()) >= 30
    for name in guarded_operations():
        values = sample_input(catalog.get(name).input, project_id=project)
        for label, credential in credentials.items():
            response = await app.call(name, credential, **values)
            assert response.status_code == 401, f"{name} with {label}: {response.text}"
            assert response.json()["code"] == "unauthenticated"


@pytest.mark.attack("IF-3.2")
async def test_IF_3_2_every_operation_declares_its_authority(app: App) -> None:
    """IF-3.2: every route states who may call it, and the admin routes refuse a member."""
    member = await app.person("member@example.com")
    schema = app.api.openapi()
    for operation in catalog:
        if not exposed_on(operation, Surface.API):
            continue
        described = next(iter(schema["paths"][route_path(operation.name)].values()))
        assert described["description"] == f"Requires: {operation.authority.value}."
        if operation.authority is Authority.ADMIN:
            response = await app.call(
                operation.name, member, **sample_input(operation.input, project_id="x" * 32)
            )
            assert_refused(response, rule="IF-3.2", code="admin_only")


@pytest.mark.attack("ACC-5")
async def test_ACC_5_roles_limit_what_a_member_may_do(app: App) -> None:
    """ACC-5, section 3: an observer writes nothing; a co-chair acts as the chairman except
    deleting the project and handing on the chair."""
    owner = await app.person("owner@example.com")
    cochair = await app.person("cochair@example.com")
    observer = await app.person("observer@example.com")
    project = await app.project(owner)
    await app.ok("members.add", owner, project_id=project, email=cochair.email, role="co-chair")
    await app.ok("members.add", owner, project_id=project, email=observer.email, role="observer")

    await app.ok("record.list", observer, project_id=project)
    for name in ("projects.start", "projects.hold", "projects.stop", "settings.change_project"):
        values = sample_input(catalog.get(name).input, project_id=project)
        assert_refused(await app.call(name, observer, **values), rule="ACC-5", code="role_required")
    assert_refused(
        await app.call("members.remove", observer, project_id=project, person_id=owner.person_id),
        rule="ACC-5",
    )

    await app.ok("projects.start", cochair, project_id=project)
    await app.ok("projects.stop", cochair, project_id=project)
    for name in ("projects.delete", "projects.cancel_delete"):
        assert_refused(await app.call(name, cochair, project_id=project), rule="ACC-5")
    assert_refused(
        await app.call(
            "members.hand_on_chair", cochair, project_id=project, person_id=cochair.person_id
        ),
        rule="ACC-5",
    )


@pytest.mark.attack("7.11")
@pytest.mark.attack("ACC-5")
async def test_7_11_a_project_always_has_exactly_one_chairman(app: App) -> None:
    """Section 7.11, ACC-5: the chairman cannot be removed or demoted, nobody can be made a
    second chairman, and the database itself refuses two."""
    owner = await app.person("owner@example.com")
    other = await app.person("other@example.com")
    project = await app.project(owner)
    await app.ok("members.add", owner, project_id=project, email=other.email, role="co-chair")

    removed = await app.call("members.remove", owner, project_id=project, person_id=owner.person_id)
    assert_refused(removed, rule="7.11", code="transition_refused")
    demoted = await app.call(
        "members.set_role", owner, project_id=project, person_id=owner.person_id, role="observer"
    )
    assert_refused(demoted, rule="7.11")
    promoted = await app.call(
        "members.set_role", owner, project_id=project, person_id=other.person_id, role="chairman"
    )
    assert promoted.status_code == 422
    twice = await app.call(
        "members.add", owner, project_id=project, email=other.email, role="observer"
    )
    assert_refused(twice, rule="ACC-5", code="already_member")

    async with app.runtime.sessions() as session:
        membership = await session.get(
            Membership, await _membership_id(app, project, other.person_id)
        )
        assert membership is not None
        membership.role = "chairman"
        with pytest.raises(IntegrityError):
            await session.commit()

    handed = await app.ok(
        "members.hand_on_chair", owner, project_id=project, person_id=other.person_id
    )
    roles = {item["email"]: item["role"] for item in handed["items"]}
    assert roles == {owner.email: "co-chair", other.email: "chairman"}


async def _membership_id(app: App, project: str, person_id: str) -> str:
    from sqlalchemy import select

    async with app.runtime.sessions() as session:
        found = await session.scalar(
            select(Membership.id).where(
                Membership.project_id == project, Membership.person_id == person_id
            )
        )
    assert found is not None
    return found


@pytest.mark.attack("ACC-5")
async def test_ACC_5_a_person_who_chairs_a_project_cannot_be_deactivated(app: App) -> None:
    """ACC-5, section 7.8: deactivation is refused, naming the projects, until an admin has
    handed each chair on as break-glass."""
    admin = await app.admin()
    owner = await app.person("owner@example.com")
    heir = await app.person("heir@example.com")
    project = await app.project(owner, name="Atlas")
    refused = await app.call("people.deactivate", admin, person_id=owner.person_id)
    envelope = assert_refused(refused, rule="ACC-5", code="chairs_projects")
    assert "Atlas" in envelope.message

    short = await app.call(
        "members.break_glass_hand_on",
        admin,
        project_id=project,
        person_id=heir.person_id,
        reason="x",
    )
    assert short.status_code == 422
    await app.ok(
        "members.break_glass_hand_on",
        admin,
        project_id=project,
        person_id=heir.person_id,
        reason="Owner has left the company.",
    )
    handed = [e for e in await app.events(heir, project) if e["type"] == "member.chair_handed_on"]
    assert "break-glass by an admin" in handed[0]["detail"]["cause"]
    assert handed[0]["actor"] == admin.person_id
    await app.ok("people.deactivate", admin, person_id=owner.person_id)


@pytest.mark.attack("IF-4.2")
async def test_IF_4_2_host_local_operations_are_unreachable_from_the_network(app: App) -> None:
    """IF-4.2: no host-local operation has a route, and the executor refuses any caller who
    is not the host operator, admins included."""
    admin = await app.admin()
    host_local = [operation for operation in catalog if operation.host_local]
    assert len(host_local) >= 9
    async with app.client() as client:
        for operation in host_local:
            response = await client.post(route_path(operation.name), json={})
            assert response.status_code == 404, operation.name
    caller = Caller(CallerKind.PERSON, admin.person_id, role=InstanceRole.ADMIN)
    backup = catalog.get("install.backup")
    with pytest.raises(Refusal) as refused:
        await app.runtime.executor.execute(backup, caller, backup.input())
    assert refused.value.envelope.rule == "IF-4.2"
