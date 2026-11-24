"""Phase 3c recall memory

Revision: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("memory_extracted", sa.Boolean(), nullable=False))
