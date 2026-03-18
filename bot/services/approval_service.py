"""
Сервис для работы с заявками на доступ (ApprovalRequest).
Создание заявок, проверка дублей, получение pending-заявок.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import RequestStatus
from bot.database.models import AccessKey, ApprovalRequest, User
from bot.utils.logger import get_logger

logger = get_logger(__name__)


async def get_pending_request_for_user(
    session: AsyncSession, user_id: int
) -> Optional[ApprovalRequest]:
    """Найти активную (pending) заявку пользователя."""
    result = await session.execute(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.user_id == user_id,
            ApprovalRequest.status == RequestStatus.PENDING,
        )
    )
    return result.scalar_one_or_none()


async def get_all_pending_requests(session: AsyncSession) -> list[ApprovalRequest]:
    """Получить все ожидающие заявки (для отображения в админке)."""
    result = await session.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status == RequestStatus.PENDING)
        .order_by(ApprovalRequest.created_at.asc())
    )
    return list(result.scalars().all())


async def create_approval_request(
    session: AsyncSession,
    user: User,
    key: Optional[AccessKey],
) -> tuple[ApprovalRequest, bool]:
    """
    Создать заявку на доступ. Предотвращает дублирование.

    Returns:
        (request, created) — created=False если заявка уже существует.
    """
    # Проверяем дублирование
    existing = await get_pending_request_for_user(session, user.id)
    if existing is not None:
        logger.debug("Дубль заявки для user_id=%s, возвращаем существующую", user.id)
        return existing, False

    request = ApprovalRequest(
        user_id=user.id,
        key_id=key.id if key else None,
        status=RequestStatus.PENDING,
    )
    session.add(request)
    await session.flush()
    logger.info(
        "Создана заявка id=%s для user_id=%s key=%s",
        request.id, user.id, key.key_value if key else None,
    )
    return request, True


async def approve_request(
    session: AsyncSession,
    request: ApprovalRequest,
    admin: User,
) -> None:
    """Одобрить заявку."""
    request.status = RequestStatus.APPROVED
    request.processed_by = admin.id
    request.processed_at = datetime.now(timezone.utc)
    await session.flush()
    logger.info(
        "Заявка id=%s одобрена администратором tg_id=%s",
        request.id, admin.telegram_id,
    )


async def reject_request(
    session: AsyncSession,
    request: ApprovalRequest,
    admin: User,
) -> None:
    """Отклонить заявку."""
    request.status = RequestStatus.REJECTED
    request.processed_by = admin.id
    request.processed_at = datetime.now(timezone.utc)
    await session.flush()
    logger.info(
        "Заявка id=%s отклонена администратором tg_id=%s",
        request.id, admin.telegram_id,
    )


async def get_request_by_id(
    session: AsyncSession, request_id: int
) -> Optional[ApprovalRequest]:
    """Получить заявку по id."""
    result = await session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    return result.scalar_one_or_none()


async def get_request_for_user_with_user(
    session: AsyncSession, user_id: int
) -> Optional[ApprovalRequest]:
    """Получить pending-заявку пользователя вместе с данными пользователя."""
    from sqlalchemy.orm import selectinload
    result = await session.execute(
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.user))
        .where(
            ApprovalRequest.user_id == user_id,
            ApprovalRequest.status == RequestStatus.PENDING,
        )
    )
    return result.scalar_one_or_none()
