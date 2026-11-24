"""Raw bytes over HTTP: resumable upload chunks and artifact downloads (IF-3.9, ART-4).

These two routes carry bytes, which a JSON operation cannot. They hold no rules of their
own: authorization is the same project lookup every operation uses, and the artifact is
created by the `uploads.finish` operation.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from nightsquad.catalog.caller import Authority, Caller, CallerKind
from nightsquad.catalog.execute import Executor, unauthenticated
from nightsquad.catalog.refusal import Refusal, RefusalKind
from nightsquad.domain.accounts.credentials import Authenticator
from nightsquad.domain.artifacts import service
from nightsquad.domain.artifacts.operations import upload_path
from nightsquad.domain.projects.access import MembershipAccess
from nightsquad.services import Services
from nightsquad.storage.models import UploadInProgress
from nightsquad.surfaces.api.app import SESSION_COOKIE

FILES_PREFIX = "/files/v1"


def add_file_routes(
    app: FastAPI, executor: Executor, authenticator: Authenticator, services: Services
) -> None:
    access = MembershipAccess()

    async def caller_of(request: Request) -> Caller:
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else None
        caller = await authenticator.authenticate(token or request.cookies.get(SESSION_COOKIE))
        if caller.kind is not CallerKind.PERSON:
            raise unauthenticated()
        return caller

    async def put_chunk(upload_id: str, request: Request, offset: int = 0) -> JSONResponse:
        """Append a chunk at `offset`. If the offset is not where the upload stands, the
        answer says where it does, so the client can resume."""
        caller = await caller_of(request)
        body = await request.body()
        async with executor.sessions() as session, session.begin():
            row = await session.get(UploadInProgress, upload_id)
            if row is None or row.person_id != caller.actor_id:
                raise Refusal(
                    "upload_not_found",
                    "There is no upload with that id.",
                    kind=RefusalKind.NOT_FOUND,
                )
            await access.resolve(session, caller, row.project_id, Authority.PROJECT_CHAIR)
            if offset != row.received or row.received + len(body) > row.size:
                return JSONResponse({"received": row.received, "size": row.size}, status_code=409)
            path = upload_path(services.data_dir, row.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab") as file:
                file.write(body)
            row.received += len(body)
            return JSONResponse({"received": row.received, "size": row.size})

    async def download(
        project_id: str, name: str, request: Request, version: int | None = None
    ) -> Response:
        """Download one version of an artifact (ART-4). HTML is served as plain text so it
        cannot run in the app's origin; the app previews it in a sandboxed frame."""
        caller = await caller_of(request)
        async with executor.sessions() as session:
            await access.resolve(session, caller, project_id, Authority.PROJECT_OBSERVER)
            artifact = await service.required(session, project_id, name)
            history = await service.versions(session, artifact)
            chosen = next((v for v in history if v.version == version), history[-1])
            content = services.blobs.read(chosen.content_hash)
            media_type = chosen.media_type
        if "html" in media_type or "svg" in media_type or "javascript" in media_type:
            media_type = "text/plain"
        return Response(
            content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{name.rsplit("/", 1)[-1]}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    app.add_api_route(
        f"{FILES_PREFIX}/uploads/{{upload_id}}", put_chunk, methods=["PUT"], include_in_schema=True
    )
    app.add_api_route(
        f"{FILES_PREFIX}/projects/{{project_id}}/artifacts/{{name:path}}",
        download,
        methods=["GET"],
        include_in_schema=True,
    )
