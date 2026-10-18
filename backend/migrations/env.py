"""Alembic runner. Revisions are hand-written SQL, so there is no model metadata to compare."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from flashpoint.settings import get_settings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# A caller (such as the test suite) can pass its own URL; otherwise use DATABASE_URL.
url = config.attributes.get("database_url") or get_settings().database_url

engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
