"""Phase 4 work and verification

Revision: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_evidence_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_evidence_state"), ["state"], unique=False)

    op.create_table(
        "project_guards",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("project_guards", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_project_guards_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "side_effects",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("is_launch", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("fired", sa.Boolean(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "idempotency_key"),
    )
    with op.batch_alter_table("side_effects", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_side_effects_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "suggestions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("handed_to_run", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("suggestions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_suggestions_handed_to_run"), ["handed_to_run"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_suggestions_project_id"), ["project_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("parent_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("team_id", sa.String(length=32), nullable=True),
        sa.Column("assignee_id", sa.String(length=32), nullable=True),
        sa.Column("author_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("test_kind", sa.String(length=16), nullable=False),
        sa.Column("success_test", sa.Text(), nullable=False),
        sa.Column("test_files", sa.JSON(), nullable=False),
        sa.Column("test_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("outside_evidence", sa.Boolean(), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("serves", sa.Text(), nullable=True),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("claimant_id", sa.String(length=32), nullable=True),
        sa.Column("reserved_for", sa.String(length=32), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_evidence", sa.Text(), nullable=True),
        sa.Column("check_output", sa.Text(), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=24), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_claimant_id"), ["claimant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_parent_id"), ["parent_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_state"), ["state"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_tasks_test_fingerprint"), ["test_fingerprint"], unique=False
        )

    op.create_table(
        "audit_samples",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("task_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("drawn", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("considered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    with op.batch_alter_table("audit_samples", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_samples_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "reviews",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("task_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.String(length=32), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reviews", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reviews_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_reviews_reviewer_id"), ["reviewer_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_reviews_task_id"), ["task_id"], unique=False)

    op.create_table(
        "task_attempts",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("task_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("seat_id", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("task_attempts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_task_attempts_task_id"), ["task_id"], unique=False)

    op.create_table(
        "watches",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "side_effect_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("check", sa.Text(), nullable=False),
        sa.Column("expect", sa.Text(), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=True),
        sa.Column("last_result", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["side_effect_id"], ["side_effects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("side_effect_id"),
    )
    with op.batch_alter_table("watches", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_watches_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_watches_state"), ["state"], unique=False)
