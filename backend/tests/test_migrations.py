from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import engine
from app.models import Base


def test_migrations_match_models(migrated):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []
