"""A local web site for tests that fetch a page: the fetch guard is told to treat
127.0.0.1 as public, and nothing else inside."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from crewmind.domain.work import fetch

PAGE = b"<html><body>Order 4411 was <b>delivered</b> on 3 May.</body></html>"


class Site:
    """A small web server on this machine, standing in for a public site."""

    def __init__(self) -> None:
        site = self
        self.status = 200
        self.page = PAGE

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/inside":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.2:{site.port}/page")
                    self.end_headers()
                    return
                if self.path == "/slow":
                    time.sleep(3)
                body = b"x" * (3 * 1024 * 1024) if self.path == "/big" else site.page
                self.send_response(site.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def url(self, path: str = "/page") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def close(self) -> None:
        self._server.shutdown()


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[Site]:
    """A local site the guard is told to treat as public. Only 127.0.0.1 is let through;
    every other inside address is still refused."""
    real = fetch.is_public

    def local_site_is_public(address: str) -> bool:
        return address == "127.0.0.1" or real(address)

    monkeypatch.setattr(fetch, "is_public", local_site_is_public)
    built = Site()
    yield built
    built.close()
