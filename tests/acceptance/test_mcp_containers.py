"""A command MCP server in its own container (CON-11, EXE-12): reached over its attached
standard input and output, given only its own variables, removed when stopped."""

from __future__ import annotations

import shutil

import pytest

from nightsquad.domain.connections import mcp_client
from nightsquad.domain.connections.mcp_client import CommandSpec, Target, probe_target
from nightsquad.runner.mcp_commands import SERVER_LABEL, CommandPool

IMAGE = "nightsquad-server:latest"
SERVER = """
import os
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
server = MCPServer("boxed", version="1")
@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def who() -> str:
    \"\"\"Who it runs as, and which variables it sees.\"\"\"
    return f"{os.getuid()} {','.join(sorted(os.environ))}"
server.run("stdio")
"""


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        import docker  # pyright: ignore[reportMissingTypeStubs]

        client = docker.from_env()
        try:
            client.images.get(IMAGE)
        finally:
            client.close()
    except Exception:
        return False
    return True


@pytest.mark.slow
@pytest.mark.skipif(not _docker_ready(), reason=f"needs Docker and the {IMAGE} image")
async def test_CON_11_a_command_server_runs_in_its_own_confined_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CON-11, EXE-12: the server answers over its container's standard input and output,
    not as root, seeing its own variable and nothing of the host's; stopping removes it."""
    import docker  # pyright: ignore[reportMissingTypeStubs]

    monkeypatch.setenv("NIGHTSQUAD_HOST_ONLY", "a value only the host has")

    async def idle() -> float:
        return 60.0

    pool = CommandPool(
        containers=True, idle_seconds=idle, default_image=IMAGE, install_id="test-install",
        cpus=1.0, memory_bytes=512 * 1024 * 1024,
    )  # fmt: skip
    previous = mcp_client.command_runner[0]
    mcp_client.command_runner[0] = pool
    spec = CommandSpec("acceptance-box", IMAGE, ("python", "-c", SERVER), {"ONLY_MINE": "x"})
    try:
        found = await probe_target(
            Target("", {}, False, None, spec), seconds=60, description_max=500
        )
        assert [tool.name for tool in found.tools] == ["who"]
        result = await mcp_client.call_target(
            Target("", {}, False, None, spec), "who", {}, seconds=60, most_bytes=4096
        )
        uid, names = result.text.split(" ", 1)
        assert uid != "0"
        assert "ONLY_MINE" in names.split(",")
        assert "NIGHTSQUAD_HOST_ONLY" not in names
        client = docker.from_env()
        try:
            assert client.containers.list(filters={"label": f"{SERVER_LABEL}=acceptance-box"})
        finally:
            client.close()
    finally:
        await pool.close()
        mcp_client.command_runner[0] = previous
    client = docker.from_env()
    try:
        assert not client.containers.list(
            all=True, filters={"label": f"{SERVER_LABEL}=acceptance-box"}
        )
    finally:
        client.close()
