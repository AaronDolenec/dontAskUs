"""Alembic environment configuration."""
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context  # pylint: disable=no-name-in-module
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path so we can import database and models
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get database URL from environment
database_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://qauser:securepassword123@db:5432/qadb")
config.set_main_option("sqlalchemy.url", database_url)

# Import models for autogenerate support
from database import Base
from models import *  # noqa: F401, F403  # pylint: disable=wildcard-import,unused-wildcard-import

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
