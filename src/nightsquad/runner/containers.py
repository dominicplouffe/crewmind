"""What every nightsquad container shares: who it runs as, how it is confined, and how it
reaches the server (EXE-12, WRK-7).

Agent sandboxes and check sandboxes are both containers from the agent image. Neither is
given a privilege, a capability or a way to gain one.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

AGENT_IMAGE_USER = 10001
"""EXE-12: the unprivileged user a container runs as when the server itself runs as root."""

CONTAINER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
"""The agent image's own search path. The host's default path does not hold its Python."""

WORKSPACE = "/workspace"
INSTALL_LABEL = "nightsquad.install"
RUN_LABEL = "nightsquad.run"


def install_id(data_dir: Path) -> str:
    """EXE-12: the label that tells this install's containers from another install's on
    the same host."""
    return hashlib.sha256(str(data_dir).encode()).hexdigest()[:12]


def container_user() -> tuple[int, int]:
    """EXE-12: a container never runs as root. It runs as the server's own user, so both
    can use the workspace, or as the image's unprivileged user when the server is root."""
    user = os.getuid()
    return (user, os.getgid()) if user else (AGENT_IMAGE_USER, AGENT_IMAGE_USER)


def hand_over(directory: Path) -> None:
    """Give a directory tree to the user its container runs as. Only a root server needs
    this. A file made read-only (a locked artifact, ART-5) stays root's and read-only."""
    if os.getuid():
        return
    user, group = container_user()
    for root, _, files in os.walk(directory):
        os.chown(root, user, group)
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path) or not os.stat(path).st_mode & 0o200:
                continue
            os.chown(path, user, group)


PRIVATE_DIR = "/run/nightsquad"
"""The in-memory filesystem a container gives a run for its file secrets (CON-7)."""


def confinement() -> dict[str, Any]:
    """EXE-12: no root, no capabilities, and no way to gain privileges. Secrets given to
    the agent as files live on an in-memory filesystem that ends with the container
    (CON-7, EXE-13)."""
    user, group = container_user()
    return {
        "user": f"{user}:{group}",
        "security_opt": ["no-new-privileges"],
        "cap_drop": ["ALL"],
        "tmpfs": {PRIVATE_DIR: "rw,noexec,nosuid,nodev,mode=1777"},
    }


NANO = 1_000_000_000


def cpus_granted(client: Any, wanted: float) -> int:
    """The CPU limit to give a container, in Docker's units: what was asked for, or every
    CPU the host has when it has fewer (EXE-12). Docker refuses a limit above the host's
    count, and a small host must still be able to run agents."""
    try:
        host = int(client.info().get("NCPU") or 0)
    except Exception:
        host = 0
    return int(min(wanted, host) * NANO) if host > 0 else int(wanted * NANO)


def docker_client() -> Any:
    import docker  # pyright: ignore[reportMissingTypeStubs]

    return docker.from_env()


def own_container(client: Any) -> Any | None:
    """The container this server runs in, or None when it runs on the host. Docker names a
    container's host after the container unless told otherwise."""
    with contextlib.suppress(Exception):
        return client.containers.get(socket.gethostname())
    return None


def host_of(url: str) -> str:
    return urlsplit(url).hostname or ""


def is_loopback_url(url: str) -> bool:
    return host_of(url) in ("127.0.0.1", "localhost", "::1")
