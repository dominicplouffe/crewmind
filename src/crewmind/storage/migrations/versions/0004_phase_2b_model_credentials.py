"""Phase 2b model credentials

Revision: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"


def upgrade() -> None:
    op.create_table(
        "provider_ceilings",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("max_concurrent", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("provider"),
    )
    op.create_table(
        "model_credentials",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("owner_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("breaker_state", sa.String(length=16), nullable=False),
        sa.Column("breaker_failures", sa.Integer(), nullable=False),
        sa.Column("breaker_cooloff_seconds", sa.Integer(), nullable=False),
        sa.Column("breaker_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_failures", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["persons.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "lineups",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("credential_id", sa.String(length=32), nullable=False),
        sa.Column("model_class", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["credential_id"], ["model_credentials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id", "model_class"),
    )
    with op.batch_alter_table("lineups", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_lineups_credential_id"), ["credential_id"], unique=False
        )

    op.create_table(
        "project_credentials",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("credential_id", sa.String(length=32), nullable=False),
        sa.Column("use", sa.String(length=16), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["model_credentials.id"],
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "use", "seat_id"),
    )
    with op.batch_alter_table("project_credentials", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_project_credentials_project_id"), ["project_id"], unique=False
        )

    with op.batch_alter_table("seats", schema=None) as batch_op:
        batch_op.add_column(sa.Column("override_class", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("override_model", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("override_effort", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("substitution", sa.Text(), nullable=True))
