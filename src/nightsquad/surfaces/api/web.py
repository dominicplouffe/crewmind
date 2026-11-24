"""Serves the built web app from the same origin as the API (NFR-24, NFR-14).

Any GET outside the server's own paths answers with a file of the web app, or with its
start page so the app's own routes work on reload. Every answer carries security headers.
"""

from __future__ import annotations

from pathlib import Path

from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

SERVER_PATHS = ("/v1/", "/files/", "/stream/", "/gateway/", "/agent/", "/mcp", "/.well-known/")
"""Paths the server answers itself. The web app never claims them."""

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; "
        "connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
        "frame-src 'self' blob: data:; object-src 'self' blob:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

START_PAGE = "index.html"
NEVER_CACHED = (START_PAGE, "sw.js", "manifest.webmanifest")


def web_directory() -> Path | None:
    """Where the built web app is: inside an installed package, or in a source checkout."""
    package = Path(__file__).resolve().parents[2]
    for candidate in (package / "web_dist", package.parents[1] / "web" / "dist"):
        if (candidate / START_PAGE).is_file():
            return candidate
    return None


class WebApp:
    """ASGI layer: the web app's files first, then everything else to the next app."""

    def __init__(self, following: ASGIApp, directory: Path | None) -> None:
        self._following = following
        self._directory = directory.resolve() if directory else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope["method"] not in ("GET", "HEAD")
            or path.startswith(SERVER_PATHS)
        ):
            await self._following(scope, receive, send)
            return
        await self._answer(path)(scope, receive, send)

    def _answer(self, path: str) -> Response:
        if self._directory is None:
            return PlainTextResponse(
                "The web app is not built on this server. Build it with `npm run build` in "
                "web/, or use the CLI.",
                status_code=404,
                headers=SECURITY_HEADERS,
            )
        file = (self._directory / path.lstrip("/")).resolve()
        inside = file.is_relative_to(self._directory)
        if not (inside and file.is_file()):
            if Path(path).suffix:
                return PlainTextResponse("Not found.", status_code=404, headers=SECURITY_HEADERS)
            file = self._directory / START_PAGE
        cache = (
            "no-cache"
            if file.name in NEVER_CACHED
            else "public, max-age=31536000, immutable"
            if "assets" in file.parts
            else "no-cache"
        )
        return FileResponse(file, headers={**SECURITY_HEADERS, "Cache-Control": cache})
