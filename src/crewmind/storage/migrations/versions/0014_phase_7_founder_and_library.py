"""phase 7 founder and library

Revision: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"


def upgrade() -> None:
    op.create_table(
        "crews",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("ceo_role", sa.String(length=100), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("teams", sa.JSON(), nullable=False),
        sa.Column("estimate_runs", sa.Integer(), nullable=True),
        sa.Column("estimate_tokens", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    with op.batch_alter_table("roles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("slug", sa.String(length=100), server_default="", nullable=False)
        )
        batch_op.add_column(
            sa.Column("category", sa.String(length=40), server_default="", nullable=False)
        )
        batch_op.add_column(sa.Column("domains", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("skills", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(
            sa.Column("source", sa.String(length=16), server_default="starter", nullable=False)
        )
    op.execute("UPDATE roles SET slug = lower(name) WHERE slug = ''")
    with op.batch_alter_table("roles", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_roles_slug_version", ["slug", "version"])
