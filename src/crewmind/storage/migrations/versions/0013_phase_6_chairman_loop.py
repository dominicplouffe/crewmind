"""phase 6 chairman loop

Revision: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"


def upgrade() -> None:
    op.create_table(
        "brief_runs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("local_date", sa.String(length=10), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "local_date"),
    )
    op.create_table(
        "mcp_confirm_tokens",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("client", sa.String(length=160), nullable=False),
        sa.Column("tool", sa.String(length=120), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "decision_items",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("filer_kind", sa.String(length=16), nullable=False),
        sa.Column("filer_id", sa.String(length=64), nullable=False),
        sa.Column("subject_kind", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("if_declined", sa.Text(), nullable=False),
        sa.Column("basis", sa.JSON(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("default_outcome", sa.String(length=40), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.Column("outcome_detail", sa.JSON(), nullable=True),
        sa.Column("chairman_note", sa.Text(), nullable=True),
        sa.Column("extensions", sa.Integer(), nullable=False),
        sa.Column("reminded", sa.Boolean(), nullable=False),
        sa.Column("chased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("decision_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_decision_items_deadline"), ["deadline"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_items_kind"), ["kind"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_decision_items_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_decision_items_state"), ["state"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_decision_items_subject_id"), ["subject_id"], unique=False
        )

    op.create_table(
        "presences",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "project_id"),
    )
    op.create_table(
        "purchases",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "approval_item_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_purchases_project_id"), ["project_id"], unique=False)

    op.create_table(
        "snoozes",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("until", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["decision_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "item_id"),
    )
    with op.batch_alter_table("alarms", schema=None) as batch_op:
        batch_op.add_column(sa.Column("level", sa.String(length=16), nullable=False))
        batch_op.add_column(sa.Column("person_id", sa.String(length=32), nullable=True))
