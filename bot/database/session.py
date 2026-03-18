"""
Управление подключением к БД и сессиями SQLAlchemy.
Использует asyncpg через create_async_engine.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.database.base import Base

# Движок и фабрика сессий инициализируются при старте приложения
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def build_engine(database_url: str) -> AsyncEngine:
    """Создать и вернуть движок. Вызывается один раз при старте."""
    global _engine
    _engine = create_async_engine(
        database_url,
        echo=False,          # Поставьте True для отладки SQL-запросов
        pool_pre_ping=True,  # Проверять соединение перед использованием
        pool_size=10,
        max_overflow=20,
    )
    return _engine


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Создать фабрику сессий. Вызывается один раз при старте."""
    global _session_factory
    _session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Объекты доступны после commit без re-fetch
        autoflush=False,
    )
    return _session_factory


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Получить фабрику сессий (после инициализации)."""
    if _session_factory is None:
        raise RuntimeError("Session factory не инициализирована. Вызовите build_session_factory().")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Генератор сессии для использования в зависимостях или напрямую.
    Пример:
        async with get_session() as session:
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables(engine: AsyncEngine) -> None:
    """Создать все таблицы (только для разработки, в prod используйте Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Корректно закрыть движок при завершении приложения."""
    if _engine is not None:
        await _engine.dispose()
