"""
Middleware для инъекции сессии БД в каждый handler.
Сессия создаётся на время обработки одного update и автоматически коммитится или откатывается.
"""
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.session import get_session_factory
from bot.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """
    Открывает сессию БД перед каждым обработчиком и закрывает после.
    Сессия доступна в handler'е через: session: AsyncSession = data["session"]
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        factory = get_session_factory()
        async with factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                logger.error("Ошибка БД, откат транзакции: %s", exc, exc_info=True)
                raise
