"""Artifacts: every file in a project, versioned and content-addressed (ART-1 to ART-9).

Bytes are stored once per content hash under the data directory. Every file an agent
writes in the workspace becomes a working artifact when its run ends (ART-2).
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crewmind.catalog.caller import Caller, platform_job
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.conversation import service as conversation
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, SettingsService, Subject
from crewmind.storage.events import append_event, event_type
from crewmind.storage.models import Artifact, ArtifactVersion, Project

ARTIFACT_VERSION = event_type("artifact.version_added", "An artifact got a new version (ART-1).")
ARTIFACT_LOCK = event_type("artifact.lock_changed", "An artifact was locked or unlocked (ART-5).")
ARTIFACT_MARKED = event_type("artifact.marked", "An upload was marked reference or example.")

ART_3 = rules.register(
    Rule("ART-3", "One deliverable per purpose: a new one names what it replaces.")
)
ART_5 = rules.register(Rule("ART-5", "Agents cannot write a locked artifact."))
ART_6 = rules.register(Rule("ART-6", "Files and project storage stay within their limits."))
ART_9 = rules.register(Rule("ART-9", "Agents publish plain filenames, with no paths."))

PAGE_BYTES = 64 * 1024  # ART-7
QUOTA_FLAG_SHARE = 80  # ART-6: a flag at 80% of the quota
OPENING_LINES = 3  # ART-3: a publication is announced with its opening lines
SNAPSHOT_JOB = platform_job("runner: workspace snapshot")
_PLAIN_NAME = re.compile(r"^[^/\\\x00]{1,200}$")
_SKIPPED_DIRECTORIES = {".git", "node_modules", "__pycache__", ".venv"}


class Kind(StrEnum):
    DELIVERABLE = "deliverable"
    WORKING = "working"
    UPLOAD = "upload"
    REPORT = "report"


class Audience(StrEnum):
    TEAM = "team"
    CHAIRMAN = "chairman"
    OUTSIDE = "outside"


@dataclass(frozen=True)
class Author:
    kind: str
    id: str
    name: str
    run_id: str | None = None
    shown_as: str | None = None
    """The name people read, when it differs from `name` (an agent's display name, EXE-18)."""


class BlobStore:
    """Content-addressed files: identical bytes are stored once (ART-2)."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, content_hash: str) -> Path:
        return self._root / content_hash[:2] / content_hash

    def put(self, content: bytes) -> str:
        content_hash = hashlib.sha256(content).hexdigest()
        target = self.path(content_hash)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return content_hash

    def read(self, content_hash: str, offset: int = 0, length: int | None = None) -> bytes:
        with self.path(content_hash).open("rb") as file:
            file.seek(offset)
            return file.read() if length is None else file.read(length)


def plain_name(name: str) -> str:
    """ART-9: a plain filename, with no path."""
    if not _PLAIN_NAME.match(name) or name in (".", ".."):
        raise Refusal(
            "name_has_path",
            f"{name!r} is not a plain filename. Publish a name with no folders in it.",
            rule=ART_9.id,
            hint="Use just the file's name, such as report.md.",
        )
    return name


async def named(session: AsyncSession, project_id: str, name: str) -> Artifact | None:
    return await session.scalar(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.name == name)
    )


async def required(session: AsyncSession, project_id: str, name: str) -> Artifact:
    artifact = await named(session, project_id, name)
    if artifact is None:
        raise Refusal(
            "artifact_not_found",
            f"There is no artifact named {name}.",
            kind=RefusalKind.NOT_FOUND,
            hint="List them with `crewmind artifacts list`.",
        )
    return artifact


async def versions(session: AsyncSession, artifact: Artifact) -> list[ArtifactVersion]:
    rows = await session.scalars(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact.id)
        .order_by(ArtifactVersion.version)
    )
    return list(rows)


async def storage_used(session: AsyncSession, project_id: str) -> int:
    """Bytes the project stores: each distinct content once (ART-2, ART-6)."""
    distinct = (
        select(ArtifactVersion.content_hash, func.max(ArtifactVersion.size).label("size"))
        .where(ArtifactVersion.project_id == project_id)
        .group_by(ArtifactVersion.content_hash)
        .subquery()
    )
    return int(await session.scalar(select(func.coalesce(func.sum(distinct.c.size), 0))) or 0)


async def _limits(
    session: AsyncSession, settings: SettingsService, project: Project, upload: bool
) -> tuple[int, int]:
    install = Subject(Scope.INSTALL, INSTALL_SUBJECT)
    per_file = await settings.get(
        session, install, "upload.max_size" if upload else "artifact.max_size"
    )
    quota = await settings.get(
        session, Subject(Scope.PROJECT, project.id, project.type), "storage.quota"
    )
    return int(per_file), int(quota)


async def add_version(
    session: AsyncSession,
    settings: SettingsService,
    blobs: BlobStore,
    project: Project,
    *,
    name: str,
    content: bytes,
    kind: Kind,
    audience: Audience,
    author: Author,
    caller: Caller,
    now: datetime,
    media_type: str | None = None,
    announce: bool = True,
) -> tuple[Artifact, ArtifactVersion | None]:
    """Store a new version of an artifact, creating it if needed. Identical content is not
    a new version. Size and quota are checked first (ART-6); agent writes to a locked
    artifact are refused (ART-5)."""
    per_file, quota = await _limits(session, settings, project, kind is Kind.UPLOAD)
    if len(content) > per_file:
        raise Refusal(
            "file_too_large",
            f"{name} is {len(content):,} bytes and the limit per file is {per_file:,}.",
            rule=ART_6.id,
            hint="Split the file, or ask an admin to raise the limit.",
        )
    artifact = await named(session, project.id, name)
    if artifact is not None and artifact.locked and author.kind == "agent":
        raise Refusal(
            "artifact_locked",
            f"The chairman has locked {name}. Agents cannot change it.",
            rule=ART_5.id,
            hint="Ask the chairman to unlock it, or publish under another name.",
        )
    content_hash = hashlib.sha256(content).hexdigest()
    history = await versions(session, artifact) if artifact is not None else []
    if history and history[-1].content_hash == content_hash:
        return artifact, None  # type: ignore[return-value]
    used = await storage_used(session, project.id)
    if used + len(content) > quota:
        raise Refusal(
            "storage_quota",
            f"The project stores {used:,} bytes and `storage.quota` is {quota:,}; {name} "
            f"needs {len(content):,} more.",
            rule=ART_6.id,
            hint="Ask the chairman to raise storage.quota.",
        )
    if artifact is None:
        artifact = Artifact(
            project_id=project.id,
            name=name,
            kind=kind,
            audience=audience,
            locked=False,
            mark=None,
            created_at=now,
        )
        session.add(artifact)
        await session.flush()
    elif kind is Kind.DELIVERABLE and artifact.kind == Kind.WORKING:
        artifact.kind, artifact.audience = kind, audience
    blobs.put(content)
    version = ArtifactVersion(
        artifact_id=artifact.id,
        project_id=project.id,
        version=len(history) + 1,
        content_hash=content_hash,
        size=len(content),
        media_type=media_type or mimetypes.guess_type(name)[0] or "application/octet-stream",
        author_kind=author.kind,
        author_id=author.id,
        author_name=author.name,
        run_id=author.run_id,
        created_at=now,
    )
    session.add(version)
    await session.flush()
    append_event(
        session,
        type=ARTIFACT_VERSION,
        caller=caller,
        at=now,
        subject=("artifact", name),
        project_id=project.id,
        after={"version": version.version, "kind": artifact.kind, "hash": content_hash},
        detail={"size": len(content), "author": author.name},
    )
    after = used + len(content)
    if used * 100 < quota * QUOTA_FLAG_SHARE <= after * 100:
        await conversation.platform_line(
            session,
            project.id,
            f"Storage is at {after * 100 // quota}% of its quota ({after:,} of {quota:,} bytes).",
            now,
            detail={"kind": "storage quota"},
        )
    wide = artifact.audience in (Audience.CHAIRMAN, Audience.OUTSIDE)
    if announce and artifact.kind in (Kind.DELIVERABLE, Kind.REPORT) and wide:
        await conversation.platform_line(
            session,
            project.id,
            f"{author.shown_as or author.name} published {name} (version {version.version}).\n"
            + opening(content),
            now,
            detail={"kind": "deliverable", "artifact": name, "version": version.version},
        )
    return artifact, version


def opening(content: bytes) -> str:
    """The opening lines of a text file, for the chat announcement (ART-3)."""
    try:
        text = content[:PAGE_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        return "(not a text file)"
    lines = [line for line in text.splitlines() if line.strip()][:OPENING_LINES]
    return "\n".join(f"> {line[:200]}" for line in lines)


def _workspace_files(workspace: Path) -> list[tuple[str, Path]]:
    """Every regular file in the workspace, by its path inside it."""
    if not workspace.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace)
        skipped = _SKIPPED_DIRECTORIES & set(relative.parts)
        if path.is_file() and not path.is_symlink() and not skipped:
            found.append((relative.as_posix(), path))
    return found


Mask = Callable[[bytes], tuple[bytes, list[str]]]
"""Masks a file's content: the content with given secrets replaced, and their names."""


def lock_in_workspace(workspace: Path, locked: list[str]) -> None:
    """Make locked files read-only where the sandbox will see them (ART-5)."""
    for name in locked:
        path = workspace / name
        if path.is_file():
            path.chmod(0o444)


async def snapshot_workspace(
    session: AsyncSession,
    settings: SettingsService,
    blobs: BlobStore,
    project: Project,
    workspace: Path,
    author: Author,
    now: datetime,
    mask: Mask | None = None,
) -> list[str]:
    """ART-2: at the end of a run, every file in the workspace that changed becomes a new
    version of a working artifact. A locked file an agent changed is put back (ART-5).
    At the storage quota the snapshot is skipped, with a line in the chat (ART-6).
    With `mask`, a file that held a given secret is stored masked, in the workspace too,
    and the chairman is told, naming the file and the secret (CON-8)."""
    changed: list[str] = []
    for name, path in await asyncio.to_thread(_workspace_files, workspace):
        content = await asyncio.to_thread(path.read_bytes)
        if mask is not None:
            masked, found = mask(content)
            if found:
                content = masked
                await asyncio.to_thread(path.write_bytes, masked)
                await conversation.platform_line(
                    session,
                    project.id,
                    f"{author.shown_as or author.name} wrote the value of "
                    f"{', '.join(found)} into {name}. It was replaced with [secret: NAME] "
                    "there and in the saved file.",
                    now,
                    detail={"kind": "secret masked in a file", "artifact": name, "secrets": found},
                )
        artifact = await named(session, project.id, name)
        if artifact is not None and artifact.locked:
            history = await versions(session, artifact)
            if history and history[-1].content_hash != hashlib.sha256(content).hexdigest():
                path.chmod(0o644)
                path.write_bytes(blobs.read(history[-1].content_hash))
                path.chmod(0o444)
                await conversation.platform_line(
                    session,
                    project.id,
                    f"{author.shown_as or author.name} changed the locked file {name}; "
                    "it was put back.",
                    now,
                    detail={"kind": "locked file restored", "artifact": name},
                )
            continue
        try:
            _, version = await add_version(
                session,
                settings,
                blobs,
                project,
                name=name,
                content=content,
                kind=Kind.WORKING,
                audience=Audience.TEAM,
                author=author,
                caller=SNAPSHOT_JOB,
                now=now,
                announce=False,
            )
        except Refusal as refusal:
            await conversation.platform_line(
                session,
                project.id,
                f"Workspace snapshot skipped: {refusal.envelope.message}",
                now,
                detail={"kind": "snapshot skipped"},
            )
            break
        if version is not None:
            changed.append(name)
    return changed
