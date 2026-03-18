"""
Middleware для защиты административных роутов.
Проверяет, что пользователь является администратором до вызова handler'а.
"""
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.auth_service import get_admin_user
from bot.utils.logger import get_logger
from bot.utils.security import is_admin_by_telegram_id

logger = get_logger(__name__)


class AdminMiddleware(BaseMiddleware):
    """
    Пропускает только администраторов.
    Устанавливает data["admin_user"] для использования в handler'е.

    Первичная проверка — по ADMIN_IDS из .env (быстро, без запроса в БД).
    Вторичная — по роли в БД.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Получить telegram_id из события
        telegram_id = self._get_telegram_id(event)
        if telegram_id is None:
            return  # Неизвестный тип события, пропускаем

        # Быстрая проверка по конфигу
        if not is_admin_by_telegram_id(telegram_id):
            # Медленная проверка по БД (на случай если роль задана в БД, а не в .env)
            session: AsyncSession | None = data.get("session")
            if session is None:
                await self._deny(event)
                return
            admin = await get_admin_user(session, telegram_id)
            if admin is None:
                await self._deny(event)
                return
            data["admin_user"] = admin
        else:
            # Получить объект пользователя из БД для использования в хендлерах
            session: AsyncSession | None = data.get("session")
            if session is not None:
                admin = await get_admin_user(session, telegram_id)
                data["admin_user"] = admin
            else:
                data["admin_user"] = None

        return await handler(event, data)

    @staticmethod
    def _get_telegram_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None

    @staticmethod
    async def _deny(event: TelegramObject) -> None:
        """Уведомить пользователя об отказе в доступе."""
        text = "У вас нет прав для выполнения этого действия."
        try:
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
        except Exception:
            pass
        logger.warning("Попытка несанкционированного доступа к админ-функции.")
