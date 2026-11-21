"""Host commands: setup, doctor, backup, restore and configuration (NFR-2, 4, 5, 7, 23)."""

from __future__ import annotations

from pathlib import Path

import pytest

from crewmind.catalog.refusal import Refusal
from crewmind.domain.install.config import ConfigError, load_config
from crewmind.domain.install.process import write_pid
from crewmind.storage.engine import Database
from tests.attack.test_install import environment
from tests.support import App


def test_NFR_7_configuration_comes_from_the_environment_with_registry_defaults(
    tmp_path: Path,
) -> None:
    """NFR-7, Appendix A: unset variables take the registry's defaults; set ones are parsed
    and checked against their range."""
    config = load_config({"CREWMIND_DATA_DIR": str(tmp_path)})
    assert (config.host, config.port, config.public_url) == ("127.0.0.1", 8420, None)
    assert config.database is Database.SQLITE
    assert config.database_url == f"sqlite:///{tmp_path / 'crewmind.sqlite'}"
    assert config.master_key_file == tmp_path / "master.key"
    assert config.base_url == "http://127.0.0.1:8420"
    custom = load_config({"CREWMIND_DATA_DIR": str(tmp_path), "CREWMIND_PORT": "9000"})
    assert custom.port == 9000
    for bad in ({"CREWMIND_PORT": "0"}, {"CREWMIND_PORT": "eighty"}, {"CREWMIND_PORT": "70000"}):
        with pytest.raises(ConfigError):
            load_config({"CREWMIND_DATA_DIR": str(tmp_path), **bad})


def test_NFR_23_slim_mode_is_sqlite(tmp_path: Path) -> None:
    """NFR-23: slim mode runs on SQLite in the data directory, and refuses a Postgres URL."""
    base = {"CREWMIND_DATA_DIR": str(tmp_path)}
    assert load_config(base, slim=True).database is Database.SQLITE
    with pytest.raises(ConfigError, match="Slim mode runs on SQLite"):
        load_config({**base, "CREWMIND_DATABASE_URL": "postgresql://u:p@db/crew"}, slim=True)


async def test_NFR_2_setup_is_idempotent_and_never_overwrites_the_master_key(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-2: the first run creates the master key and the first admin with a setup link;
    a second run changes nothing and leaves the key untouched."""
    environment(app.runtime, monkeypatch)
    first = await app.host("install.setup", admin_email="dom@example.com")
    key_file = app.runtime.config.master_key_file
    key = key_file.read_text()
    link = first.setup_link
    assert "/accept/cm_lnk_" in link
    assert any("Master key created" in step for step in first.steps)

    second = await app.host("install.setup", admin_email="other@example.com")
    assert key_file.read_text() == key
    assert second.setup_link is None
    steps = " ".join(second.steps)
    assert "already present, left untouched" in steps
    assert "An admin already exists" in steps

    admin = await app.accept(link, "dom@example.com")
    assert (await app.ok("auth.whoami", admin))["role"] == "admin"
    with pytest.raises(Refusal) as refused:
        await app.host("install.bootstrap_admin", email="third@example.com")
    assert refused.value.envelope.code == "admin_exists"


async def test_NFR_5_doctor_gives_a_fix_for_every_finding(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-5: doctor checks the whole install; each failed check comes with its fix."""
    environment(app.runtime, monkeypatch)
    report = await app.host("install.doctor")
    findings = {finding.check: finding for finding in report.findings}
    assert report.healthy is False
    assert findings["database"].ok
    assert not findings["master key"].ok
    assert not findings["server"].ok
    for finding in findings.values():
        assert finding.ok or finding.fix, finding.check

    await app.host("install.setup")
    write_pid(app.runtime.config.data_dir)
    healthy = await app.host("install.doctor")
    assert healthy.healthy is True
    app.runtime.config.master_key_file.chmod(0o644)
    loose = await app.host("install.doctor")
    key = next(f for f in loose.findings if f.check == "master key")
    assert not key.ok
    assert "chmod 600" in key.fix


async def test_NFR_4_backup_and_restore_round_trip(
    app: App, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NFR-4: one owner-readable archive holds the database and the master key. Restoring
    it brings back the earlier state and saves the state it replaced."""
    environment(app.runtime, monkeypatch)
    await app.host("install.setup")
    owner = await app.person("owner@example.com")
    kept = await app.project(owner, name="Kept")
    key = app.runtime.config.master_key_file.read_text()
    done = await app.host("install.backup", output=str(tmp_path / "backup.tar.gz"))
    archive = Path(done.archive)
    assert (archive.stat().st_mode & 0o077) == 0
    assert done.bytes > 0

    await app.project(owner, name="Made after the backup")
    app.runtime.config.master_key_file.write_text("damaged")
    assert len((await app.ok("projects.list", owner))["items"]) == 2

    write_pid(app.runtime.config.data_dir)
    with pytest.raises(Refusal) as refused:
        await app.host("install.restore", archive=str(archive), confirm="restore")
    assert refused.value.envelope.code == "server_running"
    (app.runtime.config.data_dir / "server.pid").unlink()

    await app.runtime.engine.dispose()
    restored = await app.host("install.restore", archive=str(archive), confirm="restore")
    await app.runtime.engine.dispose()
    assert Path(restored.previous_state_saved_to).exists()
    assert app.runtime.config.master_key_file.read_text() == key
    owner = await app.login(owner.email)
    projects = (await app.ok("projects.list", owner))["items"]
    assert [project["project_id"] for project in projects] == [kept]
