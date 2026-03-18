from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.config import BOT_TOKEN, LOG_LEVEL, REDIS_URL
from app.db import close_pool, init_db, open_pool
from app.handlers.admin import admin_router
from app.handlers.common import common_router
from app.handlers.user import user_router
from app.middlewares.access import BanMiddleware


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = RedisStorage.from_url(REDIS_URL)
    dp = Dispatcher(storage=storage)

    dp.message.middleware(BanMiddleware())
    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    await open_pool()
    await init_db()

    try:
        await dp.start_polling(bot)
    finally:
        await close_pool()
        await storage.close()
        await bot.session.close()
