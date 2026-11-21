"""Attacks on secrets (ACC-6, INV-6, NFR-12)."""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy import select, text

from crewmind.catalog import Principal, catalog
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.secret import one_time_secret_fields
from crewmind.domain.secrets.store import MasterKey, SecretStore, ensure_master_key
from crewmind.storage.models import Base, StoredSecret
from tests.support import PASSWORD, App

SHOWN_ONCE = {
    ("auth.login", "session"),
    ("people.invite", "link"),
    ("people.reset_link", "link"),
    ("tokens.mint", "token"),
    ("mcp_clients.mint", "token"),
    ("projects.delete", "confirmation"),
    ("install.bootstrap_admin", "link"),
    ("install.reset_link", "link"),
    ("install.setup", "setup_link"),
}
SECRET_WORDS = ("password", "secret", "token", "hash", "key", "credential", "session", "link")
NOT_SECRET = {"token_id", "token_expires_at", "secrets_reencrypted", "tokens_counted", "tokens"}


def _fields(model: type[BaseModel], prefix: str = "") -> list[str]:
    names: list[str] = []
    for name, field in model.model_fields.items():
        names.append(prefix + name)
        for inner in getattr(field.annotation, "__args__", ()) or ():
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                names.extend(_fields(inner, f"{prefix}{name}."))
    return names


@pytest.mark.attack("INV-6")
async def test_INV_6_no_operation_output_carries_a_secret_except_those_shown_once(app: App) -> None:
    """INV-6, IF-6.2: the test walks every output schema. A secret appears only in the named
    fields that show a new credential once, and never in anything an MCP client can call."""
    shown = {
        (operation.name, name)
        for operation in catalog
        for name in one_time_secret_fields(operation.output)
    }
    assert shown == SHOWN_ONCE
    for operation in catalog:
        once = set(one_time_secret_fields(operation.output))
        if Principal.MCP_CLIENT in operation.principals:
            assert not once, operation.name
        for path in _fields(operation.output):
            leaf = path.rsplit(".", 1)[-1]
            if leaf in once or leaf in NOT_SECRET:
                continue
            assert not any(word in leaf for word in SECRET_WORDS), f"{operation.name}: {path}"
        for name, field in operation.input.model_fields.items():
            if "password" in name:
                assert field.annotation is SecretStr, f"{operation.name}: {name}"


@pytest.mark.attack("INV-6")
async def test_INV_6_no_secret_reaches_the_database_the_event_log_or_the_logs(
    app: App, caplog: pytest.LogCaptureFixture
) -> None:
    """INV-6, NFR-12: after a full account flow, no password, session, token or link value
    is in any table, any event or any log line."""
    caplog.set_level(logging.DEBUG)
    admin = await app.admin()
    invite = await app.ok("people.invite", admin, email="new@example.com", name="New")
    person = await app.accept(invite["link"], "new@example.com")
    token = (await app.ok("tokens.mint", person, name="laptop"))["token"]
    mcp = (await app.ok("mcp_clients.mint", person, client_name="Desk"))["token"]
    await app.call("auth.login", email="new@example.com", password="a wrong password!")
    project = await app.project(person)
    code = (await app.ok("projects.delete", person, project_id=project))["confirmation"]
    secrets = [PASSWORD, person.token, token, mcp, invite["link"].rsplit("/", 1)[-1], code]

    stored: list[str] = []
    async with app.runtime.sessions() as session:
        for table in Base.metadata.sorted_tables:
            for row in (await session.execute(select(table))).all():
                stored.append(json.dumps([str(value) for value in row]))
    everything = "\n".join(stored) + "\n" + caplog.text
    for secret in secrets:
        assert secret not in everything


@pytest.mark.attack("ACC-6")
async def test_ACC_6_secrets_need_the_master_key_and_are_encrypted_at_rest(app: App) -> None:
    """ACC-6, NFR-12: with no key nothing is stored or read; with it, the stored bytes are
    not the value."""
    key_file = app.runtime.config.master_key_file
    store = SecretStore(key_file)
    now = app.runtime.clock()
    owner = ("project", "p1")
    async with app.runtime.sessions() as session:
        with pytest.raises(Refusal) as refused:
            await store.put(session, owner, "api key", "sk-very-secret", now)
        assert refused.value.envelope.rule == "ACC-6"
    assert ensure_master_key(key_file) is True
    assert ensure_master_key(key_file) is False
    assert (key_file.stat().st_mode & 0o077) == 0
    async with app.runtime.sessions() as session, session.begin():
        await store.put(session, owner, "api key", "sk-very-secret", now)
    async with app.runtime.sessions() as session:
        raw = (await session.execute(text("SELECT ciphertext, nonce FROM secrets"))).one()
        assert b"sk-very-secret" not in bytes(raw[0]) + bytes(raw[1])
        assert await store.reveal(session, owner, "api key") == "sk-very-secret"
        key_file.unlink()
        with pytest.raises(Refusal):
            await store.reveal(session, owner, "api key")


@pytest.mark.attack("ACC-6")
async def test_ACC_6_key_rotation_is_all_or_nothing(app: App) -> None:
    """ACC-6: rotating re-encrypts every value. If one cannot be re-encrypted, nothing
    changes: the old key still opens every other value."""
    key_file = app.runtime.config.master_key_file
    ensure_master_key(key_file)
    store = SecretStore(key_file)
    now = app.runtime.clock()
    async with app.runtime.sessions() as session, session.begin():
        for index in range(3):
            await store.put(session, ("project", "p1"), f"key {index}", f"value {index}", now)
    old_key = MasterKey.read(key_file).id

    rotated = await app.host("install.rotate_key")
    assert rotated.secrets_reencrypted == 3
    new_key = MasterKey.read(key_file).id
    assert new_key != old_key
    assert not store.pending_key_file.exists()
    async with app.runtime.sessions() as session:
        assert await store.reveal(session, ("project", "p1"), "key 2") == "value 2"
        assert set(await session.scalars(select(StoredSecret.key_id))) == {new_key}

    async with app.runtime.sessions() as session, session.begin():
        broken = await session.scalar(select(StoredSecret).where(StoredSecret.name == "key 1"))
        assert broken is not None
        broken.ciphertext = b"corrupted" + broken.ciphertext
    with pytest.raises(Refusal) as refused:
        await app.host("install.rotate_key")
    assert refused.value.envelope.code == "secret_unreadable"
    assert MasterKey.read(key_file).id == new_key
    assert not store.pending_key_file.exists()
    async with app.runtime.sessions() as session:
        assert await store.reveal(session, ("project", "p1"), "key 0") == "value 0"
        assert set(await session.scalars(select(StoredSecret.key_id))) == {new_key}
