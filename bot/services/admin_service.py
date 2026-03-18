"""
Административный сервис: одобрение/отклонение заявок, бан/разбан пользователей.
Оркестрирует user_service, key_service, approval_service.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import UserStatus
from bot.database.models import ApprovalRequest, User
from bot.services.approval_service import approve_request, reject_request
from bot.services.key_service import record_key_usage
from bot.utils.logger import get_logger

logger = get_logger(__name__)


async def approve_user(
    session: AsyncSession,
    user: User,
    request: ApprovalRequest,
    admin: User,
) -> None:
    """
    Одобрить пользователя:
    1. Обновить статус пользователя → APPROVED
    2. Записать использование ключа
    3. Пометить заявку как APPROVED
    """
    now = datetime.now(timezone.utc)

    user.status = UserStatus.APPROVED
    user.approved_at = now

    # Привязать ключ к пользователю и записать использование
    if request.key_id is not None:
        user.access_key_id = request.key_id
        user.key_entered_at = now
        # Загружаем ключ и записываем использование
        from bot.services.key_service import get_key_by_id
        key = await get_key_by_id(session, request.key_id)
        if key is not None:
            await record_key_usage(session, key, user)

    await approve_request(session, request, admin)

    logger.info(
        "Пользователь tg_id=%s одобрен администратором tg_id=%s",
        user.telegram_id, admin.telegram_id,
    )


async def reject_user(
    session: AsyncSession,
    user: User,
    request: ApprovalRequest,
    admin: User,
) -> None:
    """
    Отклонить пользователя:
    1. Обновить статус пользователя → REJECTED
    2. Пометить заявку как REJECTED
    """
    user.status = UserStatus.REJECTED
    user.rejected_at = datetime.now(timezone.utc)

    await reject_request(session, request, admin)

    logger.info(
        "Пользователь tg_id=%s отклонён администратором tg_id=%s",
        user.telegram_id, admin.telegram_id,
    )


async def ban_user(session: AsyncSession, user: User, admin: User) -> None:
    """Заблокировать пользователя."""
    user.status = UserStatus.BANNED
    user.banned_at = datetime.now(timezone.utc)
    await session.flush()
    logger.info(
        "Пользователь tg_id=%s заблокирован администратором tg_id=%s",
        user.telegram_id, admin.telegram_id,
    )


async def unban_user(session: AsyncSession, user: User, admin: User) -> None:
    """
    Разбанить пользователя.
    Статус возвращается в APPROVED если пользователь уже был одобрен ранее,
    иначе в PENDING.
    """
    if user.approved_at is not None:
        user.status = UserStatus.APPROVED
    else:
        user.status = UserStatus.PENDING

    user.banned_at = None
    await session.flush()
    logger.info(
        "Пользователь tg_id=%s разбанен администратором tg_id=%s",
        user.telegram_id, admin.telegram_id,
    )
