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
    op.create_table(
        "project_needs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "kind", "name"),
    )
    with op.batch_alter_table("project_needs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_project_needs_project_id"), ["project_id"], unique=False
        )

    with op.batch_alter_table("seats", schema=None) as batch_op:
        batch_op.add_column(sa.Column("held_for", sa.JSON(), server_default="[]", nullable=False))

    with op.batch_alter_table("secrets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("bound", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
