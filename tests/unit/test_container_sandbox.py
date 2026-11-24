"""The container sandbox's start, against a stand-in Docker client: the path every
container run takes, checked without Docker (EXE-12, CON-7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from crewmind.runner import sandbox
from crewmind.runner.containers import PRIVATE_DIR, container_user
from crewmind.runner.sandbox import ContainerSandbox, SandboxSpec


async def test_EXE_12_a_container_run_starts_confined_with_a_private_dir_only_it_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXE-12, CON-7: starting a run gives Docker one set of arguments it accepts: no root,
    no capabilities, no new privileges, and the private directory for secret files on an
    in-memory filesystem owned by the run's own user and closed to anyone else."""
    docker = MagicMock()
    docker.info.return_value = {"NCPU": 2}
    docker.networks.list.return_value = []
    monkeypatch.setattr(sandbox, "docker_client", lambda: docker)

    def no_server(_client: Any) -> None:
        return None

    monkeypatch.setattr(sandbox, "own_container", no_server)
    started = ContainerSandbox(image="agent", install_id="i1", cpus=1, memory_bytes=1 << 30)
    spec = SandboxSpec(
        run_id="r1",
        project_id="p1",
        token="t",
        api_url="http://host.docker.internal:8000",
        workspace=tmp_path / "workspace",
    )

    await started.start(spec)

    docker.containers.run.assert_called_once()
    given: dict[str, Any] = docker.containers.run.call_args.kwargs
    user, group = container_user()
    assert given["user"] == f"{user}:{group}"
    assert (given["cap_drop"], given["security_opt"]) == (["ALL"], ["no-new-privileges"])
    options = set(given["tmpfs"][PRIVATE_DIR].split(","))
    assert {"mode=0700", f"uid={user}", f"gid={group}", "noexec", "nosuid", "nodev"} <= options
    assert given["environment"]["CREWMIND_PRIVATE_DIR"] == PRIVATE_DIR
