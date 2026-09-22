"""Alembic environment (T-30).

Reads DATABASE_URL from database.db (same source as the app) and converts
async drivers to their sync counterparts for migration runs:
  sqlite+aiosqlite → sqlite | postgresql+asyncpg → postgresql (needs psycopg2)
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from database.db import Base, DATABASE_URL
from database import models  # noqa: F401  (register all tables)

config = context.config

SYNC_URL = DATABASE_URL.replace("+aiosqlite", "").replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", SYNC_URL)

try:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
except Exception:
    pass

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=SYNC_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
