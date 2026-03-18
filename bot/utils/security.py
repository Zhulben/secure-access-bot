"""
Утилиты для проверки прав доступа.
Проверяет telegram_id против списка ADMIN_IDS из конфига.
"""
from bot.config import get_config


def is_admin_by_telegram_id(telegram_id: int) -> bool:
    """
    Проверить, является ли пользователь администратором по telegram_id.
    Сверяется со списком ADMIN_IDS из .env.
    """
    return telegram_id in get_config().get_admin_ids()


def get_admin_ids() -> set[int]:
    """Вернуть множество telegram_id всех администраторов."""
    return get_config().get_admin_ids()
