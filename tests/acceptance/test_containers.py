"""Container mode against a real container runtime (EXE-12, WRK-7, INV-6).

These tests need a Docker daemon and the agent image:

    docker build -f deploy/agent.Dockerfile -t nightsquad-agent .

Without either they skip and say so.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from nightsquad.runner.check_sandbox import ContainerCheckRunner
from nightsquad.runner.containers import INSTALL_LABEL, RUN_LABEL, container_user
from nightsquad.runner.sandbox import ContainerSandbox, SandboxHandle, SandboxSpec
from nightsquad.runtime import SANDBOX_IMAGE
from tests.acceptance.test_work import finish_a_verified_job

pytestmark = pytest.mark.slow

GB = 1024**3
SERVER_PORT = 8000
STAY = "sleep 60"


@pytest.fixture(scope="module")
def docker() -> Any:
    """The container runtime, or a skip that says what is missing."""
    try:
        import docker as sdk  # pyright: ignore[reportMissingTypeStubs]

        client: Any = sdk.from_env()
        client.ping()
    except Exception as error:
        pytest.skip(f"no container runtime answers: {error}")
    if not client.images.list(name=SANDBOX_IMAGE):
        pytest.skip(f"the {SANDBOX_IMAGE} image is not built (see deploy/agent.Dockerfile)")
    return client


class Probe(ContainerSandbox):
    """A sandbox that runs a shell command where the harness would run."""

    async def start(self, spec: SandboxSpec, command: str | None = None) -> SandboxHandle:
        if command is not None:
            self._command = ["/bin/sh", "-c", command]
        return await super().start(spec)


class Host:
    """Sandboxes of one test, removed at its end whatever happened."""

    def __init__(self, client: Any, root: Path) -> None:
        self.client = client
        self.root = root
        self.install = f"test-{root.name[-20:]}"
        self._sandboxes: list[Probe] = []

    def sandbox(self, command: str, install: str | None = None) -> Probe:
        built = Probe(
            image=SANDBOX_IMAGE,
            install_id=install or self.install,
            cpus=2,
            memory_bytes=2 * GB,
            command=["/bin/sh", "-c", command],
        )
        self._sandboxes.append(built)
        return built

    def spec(self, project: str, run: str = "run-1") -> SandboxSpec:
        return SandboxSpec(
            run_id=run,
            project_id=project,
            token="tok-of-this-run",
            api_url="http://host.docker.internal:1",
            workspace=self.root / "workspaces" / project,
        )

    def containers_of(self, run: str) -> list[Any]:
        return self.client.containers.list(all=True, filters={"label": f"{RUN_LABEL}={run}"})

    def container_of(self, run: str) -> Any:
        (found,) = self.containers_of(run)
        return found

    def networks(self, install: str | None = None) -> list[str]:
        mine = {"label": f"{INSTALL_LABEL}={install or self.install}"}
        return [network.name for network in self.client.networks.list(filters=mine)]

    def clean(self) -> None:
        for built in self._sandboxes:
            with contextlib.suppress(Exception):
                built.remove_leftovers()


@pytest.fixture
def host(docker: Any, tmp_path: Path) -> Iterator[Host]:
    built = Host(docker, tmp_path)
    yield built
    built.clean()


def test_EXE_12_a_real_crew_finishes_a_verified_job_in_containers(
    docker: Any, tmp_path: Path
) -> None:
    """EXE-12, WRK-7, INV-2, P3: with agents and checks as containers, the CEO's container
    plans a task, the lead's container does it in the mounted workspace, and the check
    container verifies it. Each agent reached the server only at the agent API address."""
    finish_a_verified_job(
        tmp_path,
        {
            "NIGHTSQUAD_SANDBOX_MODE": "container",
            # A container reaches a server on this host only at a published address.
            "NIGHTSQUAD_HOST": "0.0.0.0",
            "NIGHTSQUAD_PUBLIC_URL": "https://nightsquad.test",
            "NIGHTSQUAD_AGENT_API_URL": "http://host.docker.internal:{port}",
        },
    )


PROBE = (
    """
{
  echo "user=$(id -u)"
  grep -E '^(CapEff|NoNewPrivs)' /proc/self/status | tr -d '\\t ' | tr ':' '='
  echo "docker_socket=$(test -e /var/run/docker.sock && echo yes || echo no)"
  echo "data_dir=$(test -e '%s' && echo yes || echo no)"
  env | sed 's/^/env:/'
} > probe.txt
"""
    + STAY
)


async def test_EXE_12_a_sandbox_holds_no_privilege_and_nothing_of_the_host(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXE-12, EXE-13, INV-6: what an agent's shell sees. It is not root, has no capability
    and cannot gain one; it sees the workspace and nothing else of the host; its
    environment holds the run token and the server's address and no other secret; it has
    the default CPU and memory limits, the install label, and its project's own network.
    When the run ends, the container and the idle network are gone."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-be-seen")
    monkeypatch.setenv("NIGHTSQUAD_MASTER_KEY_FILE", "/secret/master.key")
    (host.root / "master.key").write_text("the-master-key")
    spec = host.spec("project-a")
    handle = await host.sandbox(PROBE % host.root).start(spec)
    probe = spec.workspace / "probe.txt"
    for _ in range(100):
        if probe.exists() and "env:" in probe.read_text():
            break
        await asyncio.sleep(0.1)
    seen = probe.read_text().splitlines()
    facts = dict(line.split("=", 1) for line in seen if not line.startswith("env:"))
    assert facts == {
        "user": str(container_user()[0]),
        "CapEff": "0000000000000000",
        "NoNewPrivs": "1",
        "docker_socket": "no",
        "data_dir": "no",
    }
    assert facts["user"] != "0"
    environment = {line[4:].split("=", 1)[0] for line in seen if line.startswith("env:")}
    assert {name for name in environment if "NIGHTSQUAD" in name} == {
        "NIGHTSQUAD_RUN_TOKEN",
        "NIGHTSQUAD_AGENT_API",
    }
    assert "sk-should-never-be-seen" not in probe.read_text()
    assert "the-master-key" not in probe.read_text()

    container = host.container_of(spec.run_id)
    settings = container.attrs["HostConfig"]
    assert (settings["NanoCpus"], settings["Memory"]) == (2_000_000_000, 2 * GB)
    assert settings["CapDrop"] == ["ALL"]
    assert not settings["Privileged"]
    assert [bind.split(":")[1] for bind in settings["Binds"]] == ["/workspace"]
    assert container.labels[INSTALL_LABEL] == host.install
    assert host.networks() == [f"nightsquad-{host.install}-project-a"]
    assert settings["NetworkMode"] == host.networks()[0]

    await handle.kill()
    assert host.containers_of(spec.run_id) == []
    assert host.networks() == []


REACH = (
    """python -c "import socket; socket.create_connection(('%s', %d), 3)" """
    "&& echo reached > reach.txt || echo refused > reach.txt"
)


async def test_EXE_12_one_project_cannot_reach_another_projects_sandbox(host: Host) -> None:
    """EXE-12: each project has a network of its own. A sandbox reaches a server in its
    own project's sandbox, and a sandbox of another project cannot."""
    # Both are built before anything starts: a new sandbox of an install clears that
    # install's leftovers.
    server, client = host.sandbox(f"python -m http.server {SERVER_PORT}"), host.sandbox("")
    serving = host.spec("project-a", "run-serving")
    await server.start(serving)
    container = host.container_of("run-serving")
    container.reload()
    (network,) = container.attrs["NetworkSettings"]["Networks"].values()
    address = network["IPAddress"]

    async def reach(project: str, run: str) -> str:
        spec = host.spec(project, run)
        handle = await client.start(spec, REACH % (address, SERVER_PORT))
        await handle.wait()
        return (spec.workspace / "reach.txt").read_text().strip()

    # The server takes a moment to listen; the neighbour in its own project gets through.
    limit = time.monotonic() + 8
    while await reach("project-a", "run-neighbour") != "reached":
        assert time.monotonic() < limit, "a sandbox could not reach its own project's network"
    assert await reach("project-b", "run-stranger") == "refused"


async def test_EXE_12_a_second_install_never_adopts_these_containers(host: Host) -> None:
    """EXE-12: starting another install on the same host leaves this install's containers
    alone. Starting this install again removes what its last process left behind."""
    spec = host.spec("project-a")
    await host.sandbox(STAY).start(spec)
    host.sandbox(STAY, install=f"{host.install}-other")
    assert host.container_of(spec.run_id).status in ("created", "running")
    host.sandbox(STAY)
    assert host.containers_of(spec.run_id) == []
    assert host.networks() == []


NO_NETWORK = "curl -s -m 3 http://host.docker.internal:1; ip route 2>&1 | grep -q default"
NO_SECRET = "! env | grep -qiE 'nightsquad|token|api_key|sk-should'"
CHECKS: list[tuple[str, str, bool, str]] = [
    ("passes", "test -f go.txt", True, "exit 0"),
    ("fails", "test -f missing.txt", False, "exit 1"),
    ("is not root", 'test "$(id -u)" != 0', True, "exit 0"),
    ("has no network", NO_NETWORK, False, "exit"),
    ("holds no token, key or address", NO_SECRET, True, "exit 0"),
    ("runs the pinned test file", "sh check.sh", True, "pinned"),
    ("cannot change the workspace", "echo changed > go.txt", True, "exit 0"),
    ("stops at its time limit", "sleep 30", False, "did not finish in 1 seconds"),
]


@pytest.mark.parametrize(
    ("command", "passed", "output"), [c[1:] for c in CHECKS], ids=[c[0] for c in CHECKS]
)
async def test_WRK_7_a_check_container(
    docker: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    passed: bool,
    output: str,
) -> None:
    """WRK-7, INV-2, INV-6, EXE-12: a platform check runs in a container with no network,
    no token, no key and no privilege, on a copy of the workspace with the pinned test
    files put back, and within its time limit. The real workspace is never changed and
    nothing is left behind."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-be-seen")
    install = f"test-{tmp_path.name[-20:]}"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "go.txt").write_text("go")
    (workspace / "check.sh").write_text("echo weakened by the claimant\n")
    runner = ContainerCheckRunner(SANDBOX_IMAGE, tmp_path / "checks", install)
    seconds = 1 if "sleep" in command else 30
    result = await runner.run(workspace, command, {"check.sh": b"echo pinned\n"}, seconds)
    assert (result.passed, output in result.output) == (passed, True), result.output
    assert (workspace / "go.txt").read_text() == "go"
    assert list((tmp_path / "checks").iterdir()) == []
    mine = {"label": f"{INSTALL_LABEL}={install}"}
    assert docker.containers.list(all=True, filters=mine) == []


async def test_EXE_12_a_sandbox_starts_when_it_asks_for_more_cpus_than_the_host_has(
    host: Host,
) -> None:
    """EXE-12: a host with fewer CPUs than a sandbox asks for still runs it, on all it has."""
    greedy = Probe(
        image=SANDBOX_IMAGE,
        install_id=host.install,
        cpus=4096,
        memory_bytes=2 * GB,
        command=["/bin/sh", "-c", STAY],
    )
    spec = host.spec("project-a", "run-greedy")
    handle = await greedy.start(spec)
    granted = host.container_of("run-greedy").attrs["HostConfig"]["NanoCpus"]
    assert granted == int(host.client.info()["NCPU"]) * 1_000_000_000
    await handle.kill()
