"""Attacks on the host commands (NFR-3, NFR-4, NFR-6, NFR-23)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsquad.catalog.refusal import Refusal
from nightsquad.domain.install import maintenance
from nightsquad.domain.install.config import ConfigError, load_config
from nightsquad.runtime import Runtime
from tests.support import App


def environment(runtime: Runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the host commands at the test install, as the environment would."""
    config = runtime.config
    monkeypatch.setenv("NIGHTSQUAD_DATA_DIR", str(config.data_dir))
    monkeypatch.setenv("NIGHTSQUAD_DATABASE_URL", config.database_url)
    monkeypatch.setenv("NIGHTSQUAD_SANDBOX_MODE", config.sandbox_mode)
    config.data_dir.mkdir(parents=True, exist_ok=True)


@pytest.mark.attack("NFR-6")
def test_NFR_6_binding_beyond_localhost_needs_tls_and_a_public_url(tmp_path: Path) -> None:
    """NFR-6: the default bind is 127.0.0.1. Any other host is refused without an https
    public URL."""
    base = {"NIGHTSQUAD_DATA_DIR": str(tmp_path)}
    assert load_config(base).host == "127.0.0.1"
    for extra in ({}, {"NIGHTSQUAD_PUBLIC_URL": "http://squad.example"}):
        with pytest.raises(ConfigError, match="TLS"):
            load_config({**base, "NIGHTSQUAD_HOST": "0.0.0.0", **extra})
    published = load_config(
        {**base, "NIGHTSQUAD_HOST": "0.0.0.0", "NIGHTSQUAD_PUBLIC_URL": "https://squad.example"}
    )
    assert published.base_url == "https://squad.example"


@pytest.mark.attack("NFR-4")
async def test_NFR_4_restore_needs_the_confirmation_word(
    app: App, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NFR-4: a restore without the typed word, or from a file that is not a backup, is
    refused and changes nothing."""
    environment(app.runtime, monkeypatch)
    owner = await app.person("owner@example.com")
    await app.project(owner)
    archive = (await app.host("install.backup", output=str(tmp_path / "b.tar.gz"))).archive
    for word in ("", "yes", "RESTORE"):
        with pytest.raises(Refusal) as refused:
            await app.host("install.restore", archive=archive, confirm=word)
        assert refused.value.envelope.rule == "NFR-4"
        assert refused.value.envelope.code == "not_confirmed"
    fake = tmp_path / "fake.tar.gz"
    fake.write_text("not an archive")
    with pytest.raises(Refusal) as refused:
        await app.host("install.restore", archive=str(fake), confirm="restore")
    assert refused.value.envelope.code == "archive_unreadable"
    assert len((await app.ok("projects.list", owner))["items"]) == 1


@pytest.mark.attack("NFR-3")
async def test_NFR_3_update_refuses_a_dirty_checkout_and_a_package_install(
    app: App, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NFR-3: with uncommitted changes nothing is updated; a dry run changes nothing."""
    environment(app.runtime, monkeypatch)
    monkeypatch.setattr(maintenance, "checkout_root", lambda: None)
    with pytest.raises(Refusal) as refused:
        await app.host("install.update")
    assert refused.value.envelope.code == "not_a_checkout"

    import subprocess

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    monkeypatch.setattr(maintenance, "checkout_root", lambda: checkout)
    plan = await app.host("install.update", dry_run=True)
    assert plan.dry_run is True
    assert len(plan.steps) == 5
    assert not (app.runtime.config.data_dir / "backups").exists()

    (checkout / "local-change.txt").write_text("uncommitted")
    with pytest.raises(Refusal) as refused:
        await app.host("install.update")
    assert refused.value.envelope.rule == "NFR-3"
    assert refused.value.envelope.code == "dirty_checkout"
    assert "1 uncommitted change" in refused.value.envelope.message


@pytest.mark.attack("NFR-23")
async def test_NFR_23_migrate_moves_only_a_slim_install_into_postgres(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-23: the source must be SQLite and the target Postgres; anything else is refused."""
    environment(app.runtime, monkeypatch)
    target = "sqlite:///elsewhere.sqlite"
    with pytest.raises(Refusal) as refused:
        await app.host("install.migrate", to="postgres", url=target)
    assert refused.value.envelope.rule == "NFR-23"
    assert refused.value.envelope.code == "wrong_databases"
