"""
Alembic environment: конфигурация для async-миграций с asyncpg.
"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Загрузить модели и Base ДО вызова run_migrations
from bot.database.base import Base
from bot.database.models import (  # noqa: F401 — нужны для регистрации таблиц в metadata
    AccessKey,
    ApprovalRequest,
    Broadcast,
    DeliveryLog,
    KeyUsage,
    User,
)

# Alembic Config object
config = context.config

# Настройка логирования из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные для autogenerate
target_metadata = Base.metadata


def get_database_url() -> str:
    """Читать DATABASE_URL из переменной окружения (приоритет перед alembic.ini)."""
    url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))
    # asyncpg требует postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    """Offline mode: генерация SQL-скриптов без подключения к БД."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Online mode: async подключение к БД и применение миграций."""
    url = get_database_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
