"""Phase 2c artifacts, directives and cards

Revision: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"


def upgrade() -> None:
    op.create_table(
        "action_cards",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column(
            "message_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("estimated_tokens", sa.BigInteger(), nullable=False),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("action_cards", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_action_cards_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("mark", sa.String(length=16), nullable=True),
        sa.Column("superseded_by", sa.String(length=500), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
    )
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_artifacts_project_id"), ["project_id"], unique=False)

    op.create_table(
        "directives",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("author_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("card_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("directives", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_directives_project_id"), ["project_id"], unique=False)

    op.create_table(
        "frozen_threads",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("channel_id", sa.String(length=32), nullable=False),
        sa.Column(
            "thread_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "thread_id"),
    )
    op.create_table(
        "uploads_in_progress",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("received", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "artifact_versions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("artifact_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("author_kind", sa.String(length=16), nullable=False),
        sa.Column("author_id", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=200), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "version"),
    )
    with op.batch_alter_table("artifact_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_artifact_versions_artifact_id"), ["artifact_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_artifact_versions_project_id"), ["project_id"], unique=False
        )
