"""Print the upgrade body that brings a migrated database up to the models."""

import tempfile

import sqlalchemy
from alembic.autogenerate import produce_migrations, render_python_code
from alembic.migration import MigrationContext

from nightsquad.storage.migrate import migrate
from nightsquad.storage.models import Base

with tempfile.TemporaryDirectory() as d:
    url = f"sqlite:///{d}/x.sqlite"
    migrate(url)
    engine = sqlalchemy.create_engine(url)
    with engine.connect() as c:
        ctx = MigrationContext.configure(c, opts={"render_as_batch": True, "compare_type": False})
        script = produce_migrations(ctx, Base.metadata)
        print(render_python_code(script.upgrade_ops, render_as_batch=True))
