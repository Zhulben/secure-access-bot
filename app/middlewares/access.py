from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from app.db import get_user


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user = await get_user(event.from_user.id)
        if user and user["status"] == "banned":
            await event.answer("⛔ Вам запрещён доступ к боту.")
            return None
        return await handler(event, data)
