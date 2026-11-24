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
        "squads",
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
    op.create_table(
        "draftings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("quick", sa.Boolean(), nullable=False),
        sa.Column("document", sa.Text(), nullable=True),
        sa.Column("draft", sa.JSON(), nullable=True),
        sa.Column("grade", sa.JSON(), nullable=True),
        sa.Column("rehearsal", sa.JSON(), nullable=True),
        sa.Column("rehearsed_draft", sa.String(length=64), nullable=True),
        sa.Column("rest_accepted", sa.Boolean(), nullable=False),
        sa.Column("doctrine", sa.String(length=64), nullable=False),
        sa.Column("turn", sa.String(length=16), nullable=False),
        sa.Column("turn_attempts", sa.Integer(), nullable=False),
        sa.Column("model_calls", sa.Integer(), nullable=False),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.Column("rules_hit", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["persons.id"],
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("draftings", schema=None) as batch_op:
        batch_op.create_index("ix_draftings_person", ["person_id", "state"], unique=False)
        batch_op.create_index(batch_op.f("ix_draftings_project_id"), ["project_id"], unique=False)

    op.create_table(
        "drafting_ledger",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("drafting_id", sa.String(length=32), nullable=False),
        sa.Column("settles", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("passage", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["drafting_id"], ["draftings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("drafting_id", "settles"),
    )
    with op.batch_alter_table("drafting_ledger", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_drafting_ledger_drafting_id"), ["drafting_id"], unique=False
        )

    op.create_table(
        "drafting_messages",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("drafting_id", sa.String(length=32), nullable=False),
        sa.Column("author", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["drafting_id"], ["draftings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("drafting_messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_drafting_messages_drafting_id"), ["drafting_id"], unique=False
        )

    op.create_table(
        "drafting_questions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("drafting_id", sa.String(length=32), nullable=False),
        sa.Column("settles", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("recommended", sa.Integer(), nullable=True),
        sa.Column("changes", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["drafting_id"], ["draftings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("drafting_questions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_drafting_questions_drafting_id"), ["drafting_id"], unique=False
        )

    op.create_table(
        "grill_items",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("drafting_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("passage", sa.Text(), nullable=False),
        sa.Column("problem", sa.String(length=24), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("is_example", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["drafting_id"], ["draftings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("grill_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_grill_items_drafting_id"), ["drafting_id"], unique=False
        )

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extras", sa.JSON(), server_default="{}", nullable=False))
        batch_op.add_column(sa.Column("doctrine_fingerprint", sa.String(length=64), nullable=True))

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
