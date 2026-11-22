"""Forward-only schema migrations, applied at start (NFR-10)."""

from __future__ import annotations

from importlib import resources

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from crewmind.storage.engine import sync_url


def alembic_config(url: str | URL) -> Config:
    config = Config()
    location = resources.files("crewmind.storage") / "migrations"
    config.set_main_option("script_location", str(location))
    config.set_main_option(
        "sqlalchemy.url", sync_url(url).render_as_string(hide_password=False).replace("%", "%%")
    )
    return config


def migrate(url: str | URL) -> None:
    """Bring the database at `url` to the newest schema."""
    command.upgrade(alembic_config(url), "head")
