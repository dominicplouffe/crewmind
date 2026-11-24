"""phase 8 agent names

Revision: 0015
Revises: 0014

EXE-18: every seat gets a display name. Existing team seats show their seat name; the CEO
and reviewer seats draw a first name from the pool, as a new seat would. The column is
added empty, filled, then made required, so it runs on SQLite and Postgres alike.
"""

from __future__ import annotations

from itertools import groupby

import sqlalchemy as sa
from alembic import op

from nightsquad.domain.execution import names

revision: str = "0015"
down_revision: str | None = "0014"

_SEATS = sa.table(
    "seats",
    sa.column("id", sa.String),
    sa.column("project_id", sa.String),
    sa.column("team_id", sa.String),
    sa.column("name", sa.String),
    sa.column("display_name", sa.String),
    sa.column("created_at", sa.DateTime),
)


def _fill(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.select(_SEATS.c.id, _SEATS.c.project_id, _SEATS.c.team_id, _SEATS.c.name).order_by(
            _SEATS.c.project_id, _SEATS.c.created_at, _SEATS.c.name
        )
    ).all()
    for project_id, group in groupby(rows, key=lambda row: row.project_id):
        seats = list(group)
        taken = {seat.name for seat in seats}
        chosen: dict[str, str] = {}
        for seat in seats:
            if seat.team_id is not None:
                chosen[seat.id] = seat.name
        for seat in seats:
            if seat.team_id is None:
                chosen[seat.id] = names.draw(project_id, taken)
                taken.add(chosen[seat.id])
        for seat_id, display_name in chosen.items():
            connection.execute(
                _SEATS.update().where(_SEATS.c.id == seat_id).values(display_name=display_name)
            )


def upgrade() -> None:
    with op.batch_alter_table("seats", schema=None) as batch_op:
        batch_op.add_column(sa.Column("display_name", sa.String(length=100), nullable=True))
    _fill(op.get_bind())
    with op.batch_alter_table("seats", schema=None) as batch_op:
        batch_op.alter_column("display_name", existing_type=sa.String(length=100), nullable=False)
