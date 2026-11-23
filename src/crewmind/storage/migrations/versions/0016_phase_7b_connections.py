"""phase 7b connections

Revision: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"


def upgrade() -> None:
    with op.batch_alter_table("secrets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("bound", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
