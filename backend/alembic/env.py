"""Alembic environment. The database URL comes from app settings (.env), never from alembic.ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    # Keep the application's loggers working when migrations run in-process (e.g. tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Models register themselves on Base.metadata once they exist (data-model step).
target_metadata = Base.metadata

database_url = get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
