"""The server serves the built web app with security headers (NFR-24, NFR-14)."""

from __future__ import annotations

from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from crewmind.surfaces.api.web import WebApp


def served(directory: Path | None) -> httpx.AsyncClient:
    async def behind(_: object) -> PlainTextResponse:
        return PlainTextResponse("from the server")

    following = Starlette(routes=[Route("/{path:path}", behind, methods=["GET", "POST"])])
    transport = httpx.ASGITransport(app=WebApp(following, directory))
    return httpx.AsyncClient(transport=transport, base_url="http://crewmind.test")


def build(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text("<html>the app</html>")
    (directory / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "private.txt").write_text("outside the web directory")
    return directory


async def test_NFR_24_the_web_app_is_served_and_its_routes_fall_back_to_the_start_page(
    tmp_path: Path,
) -> None:
    """NFR-24, NFR-14: files are served with security headers; an app route such as
    `/accept/<token>` gets the start page; server paths and writes pass through."""
    async with served(build(tmp_path)) as client:
        start = await client.get("/")
        assert start.text == "<html>the app</html>"
        assert "frame-ancestors 'none'" in start.headers["content-security-policy"]
        assert start.headers["x-content-type-options"] == "nosniff"
        assert start.headers["referrer-policy"] == "no-referrer"
        assert start.headers["cache-control"] == "no-cache"
        assert (await client.get("/accept/some-token")).text == "<html>the app</html>"
        script = await client.get("/assets/app.js")
        assert script.text == "console.log(1)"
        assert "immutable" in script.headers["cache-control"]
        assert (await client.get("/assets/missing.js")).status_code == 404
        for path in ("/v1/projects/list", "/mcp", "/files/v1/x", "/stream/v1/projects/p"):
            assert (await client.get(path)).text == "from the server"
        assert (await client.post("/anything")).text == "from the server"


async def test_NFR_14_a_path_cannot_leave_the_web_directory(tmp_path: Path) -> None:
    """NFR-14: a path that climbs out of the web directory never serves that file."""
    async with served(build(tmp_path)) as client:
        for path in ("/../private.txt", "/%2e%2e/private.txt", "/assets/../../private.txt"):
            response = await client.get(path)
            assert "outside the web directory" not in response.text


async def test_NFR_24_without_a_build_the_server_says_so(tmp_path: Path) -> None:
    """NFR-24: a server with no built web app answers plainly and still serves its API."""
    async with served(None) as client:
        missing = await client.get("/")
        assert missing.status_code == 404
        assert "not built" in missing.text
        assert (await client.get("/v1/projects/list")).text == "from the server"
