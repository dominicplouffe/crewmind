"""The container sandbox's start, driven by a stand-in for Docker (EXE-12, CON-7).

The tests in tests/acceptance/test_containers.py prove the same against a real Docker
host, and skip where there is none. These run everywhere, so a broken start cannot hide
behind a missing daemon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nightsquad.runner import sandbox
from nightsquad.runner.containers import PRIVATE_DIR, container_user
from nightsquad.runner.sandbox import ContainerSandbox, SandboxSpec


class _Network:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attrs: dict[str, Any] = {"Containers": {}}

    def reload(self) -> None:
        return None


class _Containers:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []

    def list(self, **_: Any) -> list[Any]:
        return []

    def get(self, name: str) -> Any:
        raise LookupError(name)

    def run(self, image: str, command: Any, **options: Any) -> object:
        self.started.append({"image": image, "command": command, **options})
        return object()


class _Networks:
    def list(self, **_: Any) -> list[Any]:
        return []

    def create(self, name: str, **_: Any) -> _Network:
        return _Network(name)


class _Docker:
    """Answers the calls a container sandbox makes, and keeps what it was asked to run."""

    def __init__(self) -> None:
        self.containers = _Containers()
        self.networks = _Networks()

    def info(self) -> dict[str, Any]:
        return {"NCPU": 4}


async def test_EXE_12_a_container_run_starts_as_an_unprivileged_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXE-12, EXE-13, CON-7: starting a run makes one container, as the unprivileged user
    the platform chooses, never root, with no capabilities and no way to gain privileges.
    Its private in-memory filesystem is that user's alone and runs nothing."""
    docker = _Docker()
    monkeypatch.setattr(sandbox, "docker_client", lambda: docker)
    box = ContainerSandbox(image="agent", install_id="i1", cpus=2, memory_bytes=1 << 30)
    spec = SandboxSpec(
        run_id="r1",
        project_id="p1",
        token="ns_run_test",
        api_url="http://server:8420",
        workspace=tmp_path / "workspace",
    )

    await box.start(spec)

    [started] = docker.containers.started
    user, group = container_user()
    assert started["user"] == f"{user}:{group}"
    assert user != 0
    assert started["cap_drop"] == ["ALL"]
    assert started["security_opt"] == ["no-new-privileges"]
    private = started["tmpfs"][PRIVATE_DIR].split(",")
    assert {f"uid={user}", f"gid={group}", "mode=0700", "noexec", "nosuid", "nodev"} <= set(private)
