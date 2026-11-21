"""Artifact operations for people and for agents (ART-1 to ART-9, CHAT-9, IF-3.9)."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Principal, Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.accounts.people import person_or_refuse
from crewmind.domain.artifacts import service
from crewmind.domain.artifacts.service import (
    ART_3,
    ARTIFACT_LOCK,
    ARTIFACT_MARKED,
    PAGE_BYTES,
    Audience,
    Author,
    Kind,
)
from crewmind.domain.conversation import service as conversation
from crewmind.domain.execution.agent import agent_of
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.services import services_of
from crewmind.storage.models import Artifact, UploadInProgress

AGENT = frozenset({Principal.AGENT_RUN})


class ArtifactItem(BaseModel):
    name: str
    kind: str
    audience: str
    status: str = Field(description="draft or delivered (WRK-15: never shown as verified).")
    locked: bool
    mark: str | None
    versions: int
    size: int
    media_type: str
    last_author: str
    last_change: datetime
    superseded_by: str | None


class ArtifactList(BaseModel):
    items: list[ArtifactItem]
    storage_used: int


class ListInput(ProjectRef):
    kind: Kind | None = Field(default=None, description="Only this kind.")
    include_superseded: bool = Field(default=False, description="Also show superseded ones.")


class ArtifactRef(ProjectRef):
    name: str = Field(description="The artifact's name.")


class ReadInput(ArtifactRef):
    version: int | None = Field(default=None, description="A version number. Default: the latest.")
    offset: int = Field(default=0, ge=0, description="Where to start reading, in bytes.")


class Page(BaseModel):
    exists: bool
    name: str
    version: int | None = None
    size: int = 0
    offset: int = 0
    media_type: str | None = None
    text: str | None = Field(default=None, description="The page as text, when it is text.")
    content_base64: str | None = Field(default=None, description="The page's bytes.")
    more: bool = False


class VersionItem(BaseModel):
    version: int
    size: int
    content_hash: str
    author: str
    author_kind: str
    at: datetime


class Versions(BaseModel):
    name: str
    items: list[VersionItem]


class UploadInput(ArtifactRef):
    content_base64: str = Field(description="The file's bytes, base64-encoded.")
    media_type: str | None = Field(default=None, description="Its media type.")


class BeginUploadInput(ArtifactRef):
    size: int = Field(ge=0, description="The file's size in bytes.")
    media_type: str | None = Field(default=None, description="Its media type.")


class UploadRef(ProjectRef):
    upload_id: str = Field(description="The id from `uploads begin`.")


class UploadStatus(BaseModel):
    upload_id: str
    name: str
    size: int
    received: int = Field(description="Bytes received so far: resume from here.")


class MarkInput(ArtifactRef):
    mark: Literal["reference", "example"] = Field(
        description="reference: a binding source. example: illustrative only."
    )


async def _item(context: Context, artifact: Artifact) -> ArtifactItem | None:
    history = await service.versions(context.session, artifact)
    if not history:
        return None
    last = history[-1]
    delivered = artifact.kind in (Kind.DELIVERABLE, Kind.REPORT)
    return ArtifactItem(
        name=artifact.name,
        kind=artifact.kind,
        audience=artifact.audience,
        status="delivered" if delivered else "draft",
        locked=artifact.locked,
        mark=artifact.mark,
        versions=len(history),
        size=last.size,
        media_type=last.media_type,
        last_author=last.author_name,
        last_change=last.created_at,
        superseded_by=artifact.superseded_by,
    )


async def _list(context: Context, project_id: str, kind: Kind | None, all_: bool) -> ArtifactList:
    statement = select(Artifact).where(Artifact.project_id == project_id).order_by(Artifact.name)
    if kind is not None:
        statement = statement.where(Artifact.kind == kind)
    if not all_:
        statement = statement.where(Artifact.superseded_by.is_(None))
    items = [await _item(context, row) for row in await context.session.scalars(statement)]
    return ArtifactList(
        items=[item for item in items if item is not None],
        storage_used=await service.storage_used(context.session, project_id),
    )


async def _page(
    context: Context, project_id: str, name: str, version: int | None, offset: int
) -> Page:
    """ART-7: bytes in 64 KB pages. A missing file answers `exists: false`, not a refusal."""
    artifact = await service.named(context.session, project_id, name)
    history = await service.versions(context.session, artifact) if artifact else []
    chosen = next((v for v in history if v.version == version), None) if version else None
    chosen = chosen or (history[-1] if history and version is None else chosen)
    if artifact is None or chosen is None:
        return Page(exists=False, name=name)
    data = services_of(context).blobs.read(chosen.content_hash, offset, PAGE_BYTES)
    try:
        text: str | None = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return Page(
        exists=True,
        name=name,
        version=chosen.version,
        size=chosen.size,
        offset=offset,
        media_type=chosen.media_type,
        text=text,
        content_base64=None if text is not None else base64.b64encode(data).decode("ascii"),
        more=offset + len(data) < chosen.size,
    )


@operation(
    "artifacts.list",
    summary="List a project's files: deliverables, working files, uploads and reports.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
    slash_command="/deliverables",
)
async def list_artifacts(context: Context, payload: ListInput) -> ArtifactList:
    """ART-3: the latest version of each; superseded ones fold away."""
    return await _list(context, payload.project_id, payload.kind, payload.include_superseded)


@operation(
    "artifacts.read",
    summary="Read an artifact, one 64 KB page at a time.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def read_artifact(context: Context, payload: ReadInput) -> Page:
    return await _page(context, payload.project_id, payload.name, payload.version, payload.offset)


@operation(
    "artifacts.versions",
    summary="List every version of an artifact, with its author and hash.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_versions(context: Context, payload: ArtifactRef) -> Versions:
    artifact = await service.required(context.session, payload.project_id, payload.name)
    return Versions(
        name=artifact.name,
        items=[
            VersionItem(
                version=row.version,
                size=row.size,
                content_hash=row.content_hash,
                author=row.author_name,
                author_kind=row.author_kind,
                at=row.created_at,
            )
            for row in await service.versions(context.session, artifact)
        ],
    )


async def _store_upload(
    context: Context, project_id: str, name: str, content: bytes, media_type: str | None
) -> ArtifactItem:
    """CHAT-9, ART-8: an upload becomes an artifact of kind upload, shown in the chat. It is
    stored, never executed."""
    person = await person_or_refuse(context.session, context.caller.actor_id)
    services = services_of(context)
    artifact, version = await service.add_version(
        context.session,
        services.settings,
        services.blobs,
        view_of(context).project,
        name=service.plain_name(name),
        content=content,
        kind=Kind.UPLOAD,
        audience=Audience.TEAM,
        author=Author("person", person.id, person.name),
        caller=context.caller,
        now=context.now,
        media_type=media_type,
    )
    if version is not None:
        target = await conversation.channel(context.session, project_id, conversation.PROJECT_CHAT)
        await conversation.post(
            context.session,
            target,
            author=conversation.Author.PERSON,
            author_id=person.id,
            author_name=person.name,
            body=f"Uploaded {name}.",
            now=context.now,
            kind=conversation.MessageKind.STATUS,
            detail={"kind": "upload", "artifact": name, "version": version.version},
        )
    item = await _item(context, artifact)
    assert item is not None
    return item


@operation(
    "artifacts.upload",
    summary="Upload a small file in one call. For large files use `uploads begin`.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def upload(context: Context, payload: UploadInput) -> ArtifactItem:
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except ValueError:
        raise Refusal(
            "not_base64", "The content is not valid base64.", kind=RefusalKind.INVALID
        ) from None
    return await _store_upload(
        context, payload.project_id, payload.name, content, payload.media_type
    )


@operation(
    "uploads.begin",
    summary="Begin a resumable upload. Send the bytes to the address it returns.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def begin_upload(context: Context, payload: BeginUploadInput) -> UploadStatus:
    """IF-3.9: resumable transfer up to `upload.max_size`."""
    services = services_of(context)
    per_file, _ = await service._limits(  # pyright: ignore[reportPrivateUsage]
        context.session, services.settings, view_of(context).project, True
    )
    if payload.size > per_file:
        raise Refusal(
            "file_too_large",
            f"{payload.name} is {payload.size:,} bytes and `upload.max_size` is {per_file:,}.",
            rule=service.ART_6.id,
            hint="Ask an admin to raise upload.max_size.",
        )
    row = UploadInProgress(
        project_id=payload.project_id,
        person_id=context.caller.actor_id,
        name=service.plain_name(payload.name),
        media_type=payload.media_type or "application/octet-stream",
        size=payload.size,
        received=0,
        created_at=context.now,
    )
    context.session.add(row)
    await context.session.flush()
    return UploadStatus(upload_id=row.id, name=row.name, size=row.size, received=0)


async def _upload_row(context: Context, payload: UploadRef) -> UploadInProgress:
    row = await context.session.get(UploadInProgress, payload.upload_id)
    if row is None or row.project_id != payload.project_id:
        raise Refusal(
            "upload_not_found", "There is no upload with that id.", kind=RefusalKind.NOT_FOUND
        )
    return row


@operation(
    "uploads.status",
    summary="Show how many bytes of an upload have arrived, to resume it.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.READ,
)
async def upload_status(context: Context, payload: UploadRef) -> UploadStatus:
    row = await _upload_row(context, payload)
    return UploadStatus(upload_id=row.id, name=row.name, size=row.size, received=row.received)


@operation(
    "uploads.finish",
    summary="Finish a resumable upload: the file becomes an artifact.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def finish_upload(context: Context, payload: UploadRef) -> ArtifactItem:
    row = await _upload_row(context, payload)
    if row.received != row.size:
        raise Refusal(
            "upload_incomplete",
            f"{row.received:,} of {row.size:,} bytes have arrived.",
            rule=service.ART_6.id,
            hint="Send the rest, then finish.",
        )
    path = upload_path(services_of(context).data_dir, row.id)
    content = path.read_bytes() if row.size else b""
    item = await _store_upload(context, row.project_id, row.name, content, row.media_type)
    path.unlink(missing_ok=True)
    await context.session.delete(row)
    return item


def upload_path(data_dir: Path, upload_id: str) -> Path:
    """Where the bytes of an upload in progress are kept."""
    return data_dir / "uploads" / upload_id


async def _set_lock(context: Context, payload: ArtifactRef, locked: bool) -> ArtifactItem:
    artifact = await service.required(context.session, payload.project_id, payload.name)
    if artifact.locked != locked:
        artifact.locked = locked
        context.record(
            ARTIFACT_LOCK,
            subject=("artifact", artifact.name),
            project_id=payload.project_id,
            before={"locked": not locked},
            after={"locked": locked},
        )
    item = await _item(context, artifact)
    assert item is not None
    return item


@operation(
    "artifacts.lock",
    summary="Lock an artifact: agents can no longer change it.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/lock",
)
async def lock(context: Context, payload: ArtifactRef) -> ArtifactItem:
    """ART-5: only the chairman locks and unlocks."""
    return await _set_lock(context, payload, True)


@operation(
    "artifacts.unlock",
    summary="Unlock an artifact.",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def unlock(context: Context, payload: ArtifactRef) -> ArtifactItem:
    return await _set_lock(context, payload, False)


@operation(
    "artifacts.mark",
    summary="Mark an upload as a reference (binding) or an example (illustrative only).",
    authority=Authority.PROJECT_CHAIR,
    reversibility=Reversibility.REVERSIBLE,
)
async def mark(context: Context, payload: MarkInput) -> ArtifactItem:
    """CHAT-9: the chairman says whether an upload binds or only illustrates."""
    artifact = await service.required(context.session, payload.project_id, payload.name)
    before = artifact.mark
    artifact.mark = payload.mark
    context.record(
        ARTIFACT_MARKED,
        subject=("artifact", artifact.name),
        project_id=payload.project_id,
        before={"mark": before},
        after={"mark": payload.mark},
    )
    item = await _item(context, artifact)
    assert item is not None
    return item


class PublishInput(BaseModel):
    name: str = Field(description="A plain filename, with no folders.")
    content: str | None = Field(default=None, description="The text to publish.")
    workspace_path: str | None = Field(
        default=None, description="Or: a file in the workspace to publish under that name."
    )
    audience: Audience = Field(Audience.CHAIRMAN, description="team, chairman or outside.")
    purpose: str = Field(min_length=3, max_length=300, description="What this deliverable is for.")
    supersedes: str | None = Field(
        default=None,
        description="The deliverable this one replaces, if another serves the purpose.",
    )
    why_both: str | None = Field(
        default=None, description="Or: why both are needed, in a sentence."
    )


class AgentRead(BaseModel):
    name: str = Field(description="The artifact's name.")
    version: int | None = Field(default=None, description="Default: the latest.")
    offset: int = Field(default=0, ge=0, description="Where to start reading, in bytes.")


@operation(
    "agent.list_artifacts",
    summary="List the project's files.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def agent_list(context: Context, payload: Empty) -> ArtifactList:
    view = await agent_of(context)
    return await _list(context, view.project.id, None, False)


@operation(
    "agent.read_artifact",
    summary="Read any artifact in the project, one 64 KB page at a time.",
    authority=Authority.AGENT,
    reversibility=Reversibility.READ,
    principals=AGENT,
)
async def agent_read(context: Context, payload: AgentRead) -> Page:
    """ART-7: any agent in the project can read any artifact. Uploads are untrusted (P4)."""
    view = await agent_of(context)
    return await _page(context, view.project.id, payload.name, payload.version, payload.offset)


@operation(
    "agent.publish_artifact",
    summary="Publish a deliverable for the chairman or outside readers.",
    authority=Authority.AGENT,
    reversibility=Reversibility.REVERSIBLE,
    principals=AGENT,
)
async def publish(context: Context, payload: PublishInput) -> ArtifactItem:
    """ART-3, ART-5, ART-9: a deliverable has a plain name and a purpose. A new deliverable
    for a purpose that already has one names what it supersedes, or says why both are
    needed. The publication is announced in the chat."""
    view = await agent_of(context)
    services = services_of(context)
    name = service.plain_name(payload.name)
    if payload.content is not None:
        content = payload.content.encode("utf-8")
    elif payload.workspace_path is not None:
        workspace = (services.data_dir / "workspaces" / view.project.id).resolve()
        source = (workspace / payload.workspace_path).resolve()
        if workspace not in source.parents or not source.is_file():
            raise Refusal(
                "workspace_file_missing",
                f"There is no file {payload.workspace_path} in the workspace.",
                kind=RefusalKind.NOT_FOUND,
            )
        content = source.read_bytes()
    else:
        raise Refusal(
            "nothing_to_publish",
            "Give the content, or the workspace file to publish.",
            kind=RefusalKind.INVALID,
        )
    existing = await service.named(context.session, view.project.id, name)
    if existing is None or existing.kind != Kind.DELIVERABLE:
        rivals = list(
            await context.session.scalars(
                select(Artifact).where(
                    Artifact.project_id == view.project.id,
                    Artifact.kind == Kind.DELIVERABLE,
                    Artifact.purpose == payload.purpose,
                    Artifact.superseded_by.is_(None),
                    Artifact.name != name,
                )
            )
        )
        if rivals and payload.supersedes is None and not (payload.why_both or "").strip():
            names = ", ".join(rival.name for rival in rivals)
            raise Refusal(
                "deliverable_exists",
                f"The purpose {payload.purpose!r} already has a deliverable: {names}.",
                rule=ART_3.id,
                hint="Name the one this supersedes, or say why both are needed.",
            )
        for rival in rivals:
            if rival.name == payload.supersedes:
                rival.superseded_by = name
    artifact, _ = await service.add_version(
        context.session,
        services.settings,
        services.blobs,
        view.project,
        name=name,
        content=content,
        kind=Kind.DELIVERABLE,
        audience=payload.audience,
        author=Author("agent", view.seat.id, view.seat.name, view.run.id),
        caller=context.caller,
        now=context.now,
    )
    artifact.purpose = payload.purpose
    item = await _item(context, artifact)
    assert item is not None
    return item
