"""phase 5 planning

Revision: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"


def upgrade() -> None:
    op.create_table(
        "bets",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("kill_condition", sa.Text(), nullable=False),
        sa.Column("kill_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("extended", sa.Boolean(), nullable=False),
        sa.Column("extension_reason", sa.Text(), nullable=True),
        sa.Column("finding", sa.String(length=500), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_bets_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_bets_state"), ["state"], unique=False)

    op.create_table(
        "commitments",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("projected", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=True),
        sa.Column("resets", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("commitments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_commitments_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_commitments_state"), ["state"], unique=False)

    op.create_table(
        "cycles",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scorecard", sa.JSON(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("narrative_by_ceo", sa.Boolean(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "number"),
    )
    with op.batch_alter_table("cycles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cycles_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cycles_state"), ["state"], unique=False)

    op.create_table(
        "gap_reviews",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.String(length=32), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("gap_reviews", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_gap_reviews_project_id"), ["project_id"], unique=False)

    op.create_table(
        "raise_requests",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("what", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("arithmetic", sa.Text(), nullable=False),
        sa.Column("if_declined", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("granted", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("raise_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_raise_requests_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "requirements",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_kind", sa.String(length=16), nullable=False),
        sa.Column("author_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("test_kind", sa.String(length=16), nullable=False),
        sa.Column("success_test", sa.Text(), nullable=False),
        sa.Column("test_files", sa.JSON(), nullable=False),
        sa.Column("estimate_runs", sa.Integer(), nullable=True),
        sa.Column("actual_runs", sa.Integer(), nullable=True),
        sa.Column("actual_tokens", sa.Integer(), nullable=True),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("recurring", sa.Boolean(), nullable=False),
        sa.Column("metric", sa.JSON(), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False),
        sa.Column("ruling", sa.String(length=16), nullable=True),
        sa.Column("ruling_note", sa.Text(), nullable=True),
        sa.Column("ruled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("gap_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("met_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("requirements", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_requirements_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_requirements_state"), ["state"], unique=False)

    op.create_table(
        "reserve_draws",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("arithmetic", sa.Text(), nullable=False),
        sa.Column("drawn_by", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reserve_draws", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_reserve_draws_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "target_dates",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "time_spans",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("went_to", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("time_spans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_time_spans_project_id"), ["project_id"], unique=False)

    op.create_table(
        "gaps",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "review_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("must_fix", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("waived_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["review_id"], ["gap_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("gaps", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_gaps_project_id"), ["project_id"], unique=False)

    op.create_table(
        "metric_readings",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "requirement_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("metric_readings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_metric_readings_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_metric_readings_requirement_id"), ["requirement_id"], unique=False
        )

    op.create_table(
        "requirement_dependencies",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column(
            "requirement_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "depends_on", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.ForeignKeyConstraint(["depends_on"], ["requirements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requirement_id", "depends_on"),
    )
    with op.batch_alter_table("requirement_dependencies", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_requirement_dependencies_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_requirement_dependencies_requirement_id"),
            ["requirement_id"],
            unique=False,
        )

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "requirement_id",
                sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("bet_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True)
        )
        batch_op.create_index(batch_op.f("ix_tasks_bet_id"), ["bet_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_tasks_requirement_id"), ["requirement_id"], unique=False
        )

    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stand_down_when", sa.String(length=40), nullable=True))
