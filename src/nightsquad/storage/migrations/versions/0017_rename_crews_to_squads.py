"""rename crews to squads

Revision: 0017
Revises: 0016

LIB-2, INV-21: the library's ready-made job is a squad (ADR-0011). The table, its
constraints, the stored event type and subject kind, and the one starter squad whose
slug held the old word are renamed. Nothing is dropped, so every past event stays.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"

OLD_SLUG, NEW_SLUG = "an-overnight-crew", "an-overnight-squad"


def upgrade() -> None:
    op.rename_table("crews", "squads")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE squads RENAME CONSTRAINT crews_pkey TO squads_pkey")
        op.execute("ALTER TABLE squads RENAME CONSTRAINT crews_slug_key TO squads_slug_key")
    events = sa.table(
        "events", sa.column("type"), sa.column("subject_kind"), sa.column("subject_id")
    )
    op.execute(events.update().where(events.c.type == "crew.saved").values(type="squad.saved"))
    op.execute(events.update().where(events.c.subject_kind == "crew").values(subject_kind="squad"))
    op.execute(
        events.update()
        .where(events.c.subject_kind == "squad", events.c.subject_id == OLD_SLUG)
        .values(subject_id=NEW_SLUG)
    )
    squads = sa.table("squads", sa.column("slug"), sa.column("name"), sa.column("source"))
    op.execute(
        squads.update()
        .where(squads.c.slug == OLD_SLUG, squads.c.source == "starter")
        .values(slug=NEW_SLUG, name="An overnight squad")
    )


def downgrade() -> None:
    squads = sa.table("squads", sa.column("slug"), sa.column("name"), sa.column("source"))
    op.execute(
        squads.update()
        .where(squads.c.slug == NEW_SLUG, squads.c.source == "starter")
        .values(slug=OLD_SLUG, name="An overnight crew")
    )
    events = sa.table(
        "events", sa.column("type"), sa.column("subject_kind"), sa.column("subject_id")
    )
    op.execute(
        events.update()
        .where(events.c.subject_kind == "squad", events.c.subject_id == NEW_SLUG)
        .values(subject_id=OLD_SLUG)
    )
    op.execute(events.update().where(events.c.subject_kind == "squad").values(subject_kind="crew"))
    op.execute(events.update().where(events.c.type == "squad.saved").values(type="crew.saved"))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE squads RENAME CONSTRAINT squads_slug_key TO crews_slug_key")
        op.execute("ALTER TABLE squads RENAME CONSTRAINT squads_pkey TO crews_pkey")
    op.rename_table("squads", "crews")
