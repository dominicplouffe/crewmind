"""Well-known MCP servers fill in the add form; an install edits the list (CON-15)."""

from __future__ import annotations

import json

from nightsquad.domain.connections.mcp_client import check_url
from nightsquad.domain.connections.presets import FOLDER, shipped
from tests.support import App


def test_CON_15_every_shipped_preset_is_complete_and_holds_no_value() -> None:
    """CON-15, INV-6: a remote preset has an https address its auth kind can use, a token
    preset names the secret to create, a command preset has a command; none holds a value."""
    presets = shipped()
    assert {preset.kind for preset in presets} == {"remote", "command"}
    for preset in presets:
        if preset.kind == "remote":
            assert preset.url is not None
            check_url(preset.url, private_allowed=False)
            needs_one = preset.auth_kind in ("bearer", "header")
            assert (preset.value_needed is not None) == needs_one
        else:
            assert preset.command
            assert preset.url is None
        dumped = json.dumps(preset.model_dump(exclude={"value_needed"})).lower()
        assert "value" not in dumped
        assert "password" not in dumped


async def test_CON_15_an_install_replaces_adds_and_hides_presets(app: App) -> None:
    """CON-15: files in the data directory lay over the shipped list by slug."""
    owner = await app.person("owner@example.com")
    folder = app.runtime.config.data_dir / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    hidden = {
        "slug": "github", "hidden": True, "name": "github", "title": "GitHub",
        "description": "x", "kind": "remote", "url": "https://api.githubcopilot.com/mcp/",
    }  # fmt: skip
    (folder / "github.json").write_text(json.dumps(hidden))
    wiki = {
        "slug": "wiki", "name": "wiki", "title": "Our wiki", "description": "The team wiki.",
        "kind": "remote", "url": "https://wiki.example.com/mcp", "auth_kind": "oauth",
    }  # fmt: skip
    (folder / "wiki.json").write_text(json.dumps(wiki))
    (folder / "broken.json").write_text("{not json")
    listed = (await app.ok("connections.presets", owner))["presets"]
    slugs = [preset["slug"] for preset in listed]
    assert "github" not in slugs
    assert "wiki" in slugs
    assert "linear" in slugs
