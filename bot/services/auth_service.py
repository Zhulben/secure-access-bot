"""
Сервис аутентификации и авторизации.
Проверка: является ли пользователь админом, забанен ли он.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import UserRole, UserStatus
from bot.database.models import User
from bot.services.user_service import get_user_by_telegram_id
from bot.utils.security import is_admin_by_telegram_id


def is_user_admin(user: User) -> bool:
    """
    Проверить права администратора.
    Пользователь считается админом если:
    - его telegram_id есть в ADMIN_IDS (из .env), ИЛИ
    - его роль в БД — ADMIN
    """
    return (
        is_admin_by_telegram_id(user.telegram_id)
        or user.role == UserRole.ADMIN
    )


def is_user_banned(user: User) -> bool:
    """Проверить, заблокирован ли пользователь."""
    return user.status == UserStatus.BANNED


def is_user_approved(user: User) -> bool:
    """Проверить, одобрен ли пользователь."""
    return user.status == UserStatus.APPROVED


def is_user_pending(user: User) -> bool:
    """Проверить, ожидает ли пользователь одобрения."""
    return user.status == UserStatus.PENDING


def is_user_rejected(user: User) -> bool:
    """Проверить, отклонён ли пользователь."""
    return user.status == UserStatus.REJECTED


async def get_admin_user(
    session: AsyncSession, telegram_id: int
) -> Optional[User]:
    """
    Получить пользователя и проверить, что он администратор.
    Returns None если пользователь не найден или не является админом.
    """
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return None
    if not is_user_admin(user):
        return None
    return user
