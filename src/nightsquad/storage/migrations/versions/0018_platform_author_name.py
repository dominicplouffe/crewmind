"""platform author name

Revision: 0018
Revises: 0017

CHAT-3, ART-1: lines and artifact versions the platform wrote before the product was
renamed (ADR-0011) carry the old product name as their author. They carry the new one,
so every surface shows the platform's own lines alike.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"

OLD_NAME, NEW_NAME = "crew" + "mind", "nightsquad"
TABLES = ("messages", "artifact_versions")


def _rename(old: str, new: str) -> None:
    for name in TABLES:
        table = sa.table(name, sa.column("author_kind"), sa.column("author_name"))
        op.execute(
            table.update()
            .where(table.c.author_kind == "platform", table.c.author_name == old)
            .values(author_name=new)
        )


def upgrade() -> None:
    _rename(OLD_NAME, NEW_NAME)


def downgrade() -> None:
    _rename(NEW_NAME, OLD_NAME)
