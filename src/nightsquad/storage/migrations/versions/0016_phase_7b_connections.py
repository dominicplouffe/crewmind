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
        "connections",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("env_name", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("warned", sa.JSON(), server_default="[]", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("connections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_connections_name_key"), ["name_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_connections_owner_id"), ["owner_id"], unique=False)

    op.create_table(
        "connection_secrets",
        sa.Column("connection_id", sa.String(length=32), nullable=False),
        sa.Column("delivery", sa.String(length=16), nullable=False),
        sa.Column("sites", sa.JSON(), nullable=False),
        sa.Column("header_kind", sa.String(length=16), nullable=True),
        sa.Column("header_name", sa.String(length=100), nullable=True),
        sa.Column("basic_user", sa.String(length=200), nullable=True),
        sa.Column("shape", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("connection_id"),
    )
    op.create_table(
        "connection_variables",
        sa.Column("connection_id", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("connection_id"),
    )
    op.create_table(
        "mcp_servers",
        sa.Column("connection_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("transport", sa.String(length=24), nullable=True),
        sa.Column("auth_kind", sa.String(length=16), nullable=False),
        sa.Column("header_name", sa.String(length=100), nullable=True),
        sa.Column("private_allowed", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("server_name", sa.String(length=200), nullable=True),
        sa.Column("server_version", sa.String(length=100), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("breaker_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cool_off_seconds", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("tools_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oauth", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("command", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("image", sa.String(length=300), nullable=True),
        sa.Column("environment", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("connection_id"),
    )
    op.create_table(
        "mcp_sign_ins",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=32), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("return_to", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("mcp_sign_ins", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mcp_sign_ins_connection_id"), ["connection_id"], unique=False
        )

    op.create_table(
        "mcp_tools",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("server_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("classification", sa.String(length=16), nullable=False),
        sa.Column("permission", sa.String(length=16), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gone", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.connection_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "name"),
    )
    with op.batch_alter_table("mcp_tools", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_tools_server_id"), ["server_id"], unique=False)

    op.create_table(
        "project_connections",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("connection_id", sa.String(length=32), nullable=False),
        sa.Column("env_name", sa.String(length=100), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("attached_by", sa.String(length=32), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "connection_id"),
    )
    with op.batch_alter_table("project_connections", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_project_connections_connection_id"), ["connection_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_project_connections_project_id"), ["project_id"], unique=False
        )

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
