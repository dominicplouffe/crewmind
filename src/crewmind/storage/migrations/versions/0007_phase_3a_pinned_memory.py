"""Phase 3a pinned memory

Revision: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"


def upgrade() -> None:
    op.create_table(
        "closed_decisions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("ruling", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("closed_decisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_closed_decisions_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "corrections",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column(
            "message_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column("words", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("corrections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_corrections_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_corrections_seat_id"), ["seat_id"], unique=False)

    op.create_table(
        "example_marks",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column(
            "message_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    with op.batch_alter_table("example_marks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_example_marks_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "pinned_notes",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pinned_notes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_pinned_notes_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_pinned_notes_seat_id"), ["seat_id"], unique=False)

    op.create_table(
        "standing_orders",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.String(length=400), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "message_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("proposed_by", sa.String(length=200), nullable=False),
        sa.Column("shorten", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("standing_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_standing_orders_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "reopen_requests",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "decision_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["closed_decisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reopen_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_reopen_requests_decision_id"), ["decision_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_reopen_requests_project_id"), ["project_id"], unique=False
        )
