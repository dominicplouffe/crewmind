"""Well-known MCP servers that fill in the add form (CON-15). Library content: shipped in the
package from `content/mcp-servers/`, and edited per install by an admin, who puts files of
the same shape in the data directory's `mcp-servers/` folder. A file there with a shipped
slug replaces it; `"hidden": true` removes it. A preset holds no value, only names (INV-6)."""

from __future__ import annotations

import json
import logging
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, Empty, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.domain.connections.mcp import AuthKind
from crewmind.services import services_of

logger = logging.getLogger(__name__)

FOLDER = "mcp-servers"


class PresetValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="The name to give the secret, such as github-token.")
    description: str = Field(description="What to create at the provider, and with what access.")


class PresetVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    env: str = Field(description="The environment variable the command server reads.")
    description: str


class Preset(BaseModel):
    """CON-15: the address or command, the auth kind and the secrets a server needs."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str = Field(description="The connection name the form suggests.")
    title: str
    description: str
    kind: Literal["remote", "command"]
    url: str | None = None
    auth_kind: AuthKind = AuthKind.NONE
    header_name: str | None = None
    value_needed: PresetValue | None = Field(
        default=None,
        description="The token or header value a remote server needs: what to call it and "
        "what to create at the provider. Never the value itself.",
    )
    command: str | None = None
    environment: list[PresetVariable] = Field(
        default_factory=list[PresetVariable],
        description="The variables a command server needs, each filled by a secret you add.",
    )
    docs: str | None = Field(default=None, description="The server's own instructions.")
    hidden: bool = False


class PresetList(BaseModel):
    presets: list[Preset]


def _read(text: str, where: str) -> Preset | None:
    try:
        return Preset.model_validate(json.loads(text))
    except (ValueError, ValidationError) as error:
        logger.warning("MCP server preset %s is not valid and is skipped: %s", where, error)
        return None


def shipped() -> list[Preset]:
    root = resources.files("crewmind.content").joinpath("library", FOLDER)
    found = [
        _read(entry.read_text(encoding="utf-8"), entry.name)
        for entry in sorted(root.iterdir(), key=lambda entry: entry.name)
        if entry.name.endswith(".json")
    ]
    return [preset for preset in found if preset is not None]


def for_install(data_dir: Path) -> list[Preset]:
    """The shipped presets with the install's own laid over them, by slug."""
    by_slug = {preset.slug: preset for preset in shipped()}
    folder = data_dir / FOLDER
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            preset = _read(path.read_text(encoding="utf-8"), path.name)
            if preset is not None:
                by_slug[preset.slug] = preset
    return sorted(
        (preset for preset in by_slug.values() if not preset.hidden),
        key=lambda preset: preset.title.lower(),
    )


@operation(
    "connections.presets",
    summary="List well-known MCP servers, to fill in the add form.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def presets(context: Context, payload: Empty) -> PresetList:
    """CON-15: library content, shipped and edited per install."""
    return PresetList(presets=for_install(services_of(context).data_dir))
