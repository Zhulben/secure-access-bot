"""
Точка входа приложения.
Инициализация бота, диспетчера, middleware, роутеров и запуск polling.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_config
from bot.database.session import build_engine, build_session_factory, close_engine
from bot.handlers import admin_router, common_router, user_router
from bot.middlewares.admin import AdminMiddleware
from bot.middlewares.db import DatabaseMiddleware
from bot.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


async def main() -> None:
    """Запустить бота."""
    config = get_config()

    # Настройка логирования
    setup_logging(config.log_level)
    logger.info("Запуск бота...")

    # Инициализация БД
    engine = build_engine(config.database_url)
    build_session_factory(engine)
    logger.info("Подключение к БД установлено.")

    # Создание бота
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Хранилище FSM (в памяти; для production рекомендуется Redis)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрация глобального middleware для сессии БД
    dp.update.middleware(DatabaseMiddleware())

    # Регистрация роутеров
    # Порядок важен: admin_router регистрируется с AdminMiddleware
    admin_router.message.middleware(AdminMiddleware())
    admin_router.callback_query.middleware(AdminMiddleware())

    dp.include_router(user_router)
    dp.include_router(admin_router)
    dp.include_router(common_router)

    logger.info("Роутеры зарегистрированы.")
    logger.info("Бот запущен. Ожидание сообщений...")

    # Сбросить зависшую сессию getUpdates / webhook на стороне Telegram
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Сессия Telegram сброшена.")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await close_engine()
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем (Ctrl+C).")
