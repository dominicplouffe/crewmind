"""Print the OpenAPI schema of the human API (IF-3.1). The web app's API client is
generated from it:

    uv run python -m crewmind.surfaces.api.schema > web/openapi.json
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from crewmind.catalog.registry import catalog
from crewmind.domain.install.config import Config
from crewmind.runtime import build_runtime
from crewmind.surfaces.api.app import build_api
from crewmind.surfaces.api.files import add_file_routes
from crewmind.surfaces.api.stream import add_stream_route
from crewmind.surfaces.mcp.oauth_routes import add_oauth_routes


def schema() -> dict[str, object]:
    scratch = Path(tempfile.mkdtemp())
    runtime = build_runtime(
        Config(
            database_url=f"sqlite:///{scratch / 'schema.sqlite'}",
            data_dir=scratch,
            master_key_file=scratch / "master.key",
            host="127.0.0.1",
            port=8420,
            public_url=None,
        )
    )
    app = build_api(catalog, runtime.executor, runtime.authenticator, base_url="http://127.0.0.1")
    add_file_routes(app, runtime.executor, runtime.authenticator, runtime.services)
    add_oauth_routes(app, runtime.executor, runtime.config.base_url)
    add_stream_route(app, runtime.executor, runtime.authenticator, runtime.hub)
    return app.openapi()


if __name__ == "__main__":
    json.dump(schema(), sys.stdout, indent=1, sort_keys=True)
