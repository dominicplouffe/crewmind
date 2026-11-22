"""Phase 3b speaking

Revision: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"


def upgrade() -> None:
    op.create_table(
        "held_posts",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("marker", sa.String(length=16), nullable=True),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("held_posts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_held_posts_due_at"), ["due_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_held_posts_project_id"), ["project_id"], unique=False)

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rewrite_asked", sa.Boolean(), nullable=False))
