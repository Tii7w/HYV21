from logging.config import fileConfig

from alembic import context

from app.db import engine
from app.models import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            # SQLite ALTER TABLE kısıtları için tablo kopyalama yöntemi kullanılır.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
