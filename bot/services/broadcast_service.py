"""
Сервис рассылки сообщений.
Создание рассылки, отправка пользователям, логирование результатов.
"""
import asyncio
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import BroadcastType, DeliveryMode, DeliveryStatus
from bot.database.models import Broadcast, DeliveryLog, User
from bot.services.user_service import get_approved_users, get_pending_users
from bot.utils.logger import get_logger

logger = get_logger(__name__)

# Задержка между сообщениями (мс) для предотвращения flood
SEND_DELAY_MS = 50


async def create_broadcast(
    session: AsyncSession,
    admin_id: int,
    broadcast_type: BroadcastType,
    text: Optional[str],
    photo_file_id: Optional[str],
    send_to_pending_masked: bool,
) -> Broadcast:
    """Создать запись рассылки в БД."""
    broadcast = Broadcast(
        admin_id=admin_id,
        broadcast_type=broadcast_type,
        text=text,
        photo_file_id=photo_file_id,
        send_to_pending_masked=send_to_pending_masked,
    )
    session.add(broadcast)
    await session.flush()
    logger.info(
        "Создана рассылка id=%s type=%s admin_id=%s",
        broadcast.id, broadcast_type, admin_id,
    )
    return broadcast


async def send_broadcast(
    bot: Bot,
    session: AsyncSession,
    broadcast: Broadcast,
) -> dict[str, int]:
    """
    Разослать сообщение всем целевым пользователям.

    Returns:
        {"success": N, "failed": N, "skipped": N}
    """
    stats = {"success": 0, "failed": 0, "skipped": 0}

    # Одобренные пользователи — получают полный контент
    approved_users = await get_approved_users(session)

    for user in approved_users:
        status, error = await _send_real_message(bot, broadcast, user)
        await _log_delivery(session, broadcast, user, DeliveryMode.REAL, status, error)
        if status == DeliveryStatus.SUCCESS:
            stats["success"] += 1
        else:
            stats["failed"] += 1
        await asyncio.sleep(SEND_DELAY_MS / 1000)

    # Pending-пользователи — получают маскированное уведомление (если включено)
    if broadcast.send_to_pending_masked:
        pending_users = await get_pending_users(session)
        for user in pending_users:
            status, error = await _send_masked_message(bot, user)
            await _log_delivery(session, broadcast, user, DeliveryMode.MASKED, status, error)
            if status == DeliveryStatus.SUCCESS:
                stats["success"] += 1
            else:
                stats["failed"] += 1
            await asyncio.sleep(SEND_DELAY_MS / 1000)

    logger.info(
        "Рассылка id=%s завершена: %s",
        broadcast.id, stats,
    )
    return stats


async def _send_real_message(
    bot: Bot,
    broadcast: Broadcast,
    user: User,
) -> tuple[DeliveryStatus, Optional[str]]:
    """Отправить реальный контент одному пользователю."""
    try:
        if broadcast.broadcast_type == BroadcastType.TEXT:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=broadcast.text or "",
            )
        elif broadcast.broadcast_type == BroadcastType.PHOTO:
            await bot.send_photo(
                chat_id=user.telegram_id,
                photo=broadcast.photo_file_id or "",
            )
        elif broadcast.broadcast_type == BroadcastType.PHOTO_CAPTION:
            await bot.send_photo(
                chat_id=user.telegram_id,
                photo=broadcast.photo_file_id or "",
                caption=broadcast.text or "",
            )
        return DeliveryStatus.SUCCESS, None

    except TelegramForbiddenError:
        # Пользователь заблокировал бота
        return DeliveryStatus.FAILED, "Пользователь заблокировал бота"

    except TelegramRetryAfter as e:
        # Flood control — ждём и повторяем один раз
        logger.warning("Flood control, жду %s секунд", e.retry_after)
        await asyncio.sleep(e.retry_after)
        try:
            if broadcast.broadcast_type == BroadcastType.TEXT:
                await bot.send_message(chat_id=user.telegram_id, text=broadcast.text or "")
            elif broadcast.broadcast_type == BroadcastType.PHOTO:
                await bot.send_photo(chat_id=user.telegram_id, photo=broadcast.photo_file_id or "")
            elif broadcast.broadcast_type == BroadcastType.PHOTO_CAPTION:
                await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=broadcast.photo_file_id or "",
                    caption=broadcast.text or "",
                )
            return DeliveryStatus.SUCCESS, None
        except TelegramAPIError as retry_err:
            return DeliveryStatus.FAILED, str(retry_err)

    except TelegramAPIError as e:
        return DeliveryStatus.FAILED, str(e)


async def _send_masked_message(
    bot: Bot,
    user: User,
) -> tuple[DeliveryStatus, Optional[str]]:
    """Отправить маскированное уведомление pending-пользователю."""
    masked_text = (
        "У вас есть новое сообщение от администратора.\n\n"
        "Завершите регистрацию, чтобы получить полный доступ к материалам."
    )
    try:
        await bot.send_message(chat_id=user.telegram_id, text=masked_text)
        return DeliveryStatus.SUCCESS, None
    except TelegramForbiddenError:
        return DeliveryStatus.FAILED, "Пользователь заблокировал бота"
    except TelegramAPIError as e:
        return DeliveryStatus.FAILED, str(e)


async def _log_delivery(
    session: AsyncSession,
    broadcast: Broadcast,
    user: User,
    mode: DeliveryMode,
    status: DeliveryStatus,
    error: Optional[str],
) -> None:
    """Записать результат доставки в БД."""
    log = DeliveryLog(
        broadcast_id=broadcast.id,
        user_id=user.id,
        delivery_mode=mode,
        delivery_status=status,
        error_text=error,
    )
    session.add(log)
    # Не делаем flush здесь — накапливаем и flush в конце рассылки


async def get_last_broadcasts(session: AsyncSession, limit: int = 5) -> list:
    """Получить последние N рассылок администратора."""
    from sqlalchemy import select
    from bot.database.models import Broadcast
    result = await session.execute(
        select(Broadcast).order_by(Broadcast.created_at.desc()).limit(limit)
    )
    broadcasts = list(result.scalars().all())
    broadcasts.reverse()  # от старых к новым
    return broadcasts


async def deliver_missed_broadcasts(
    bot: Bot,
    session: AsyncSession,
    user: User,
) -> int:
    """
    Отправить пользователю все рассылки, которые он пропустил (не получил как REAL).
    Вызывается при одобрении пользователя.
    Возвращает количество отправленных рассылок.
    """
    from sqlalchemy import select, exists
    from bot.database.models import Broadcast, DeliveryLog

    # Найти рассылки без REAL-доставки для этого пользователя
    already_delivered = (
        select(DeliveryLog.broadcast_id)
        .where(
            DeliveryLog.user_id == user.id,
            DeliveryLog.delivery_mode == DeliveryMode.REAL,
        )
    )
    result = await session.execute(
        select(Broadcast)
        .where(Broadcast.id.not_in(already_delivered))
        .order_by(Broadcast.created_at.asc())
    )
    missed = list(result.scalars().all())

    sent = 0
    for broadcast in missed:
        status, error = await _send_real_message(bot, broadcast, user)
        await _log_delivery(session, broadcast, user, DeliveryMode.REAL, status, error)
        if status == DeliveryStatus.SUCCESS:
            sent += 1
        await asyncio.sleep(SEND_DELAY_MS / 1000)

    await session.flush()
    if sent:
        logger.info(
            "Пользователю tg_id=%s доставлено пропущенных рассылок: %d",
            user.telegram_id, sent,
        )
    return sent


async def get_broadcast_stats(session: AsyncSession, broadcast_id: int) -> dict[str, int]:
    """Получить статистику доставки конкретной рассылки."""
    from sqlalchemy import select, func
    from bot.database.models import DeliveryLog

    result = await session.execute(
        select(DeliveryLog.delivery_status, func.count(DeliveryLog.id))
        .where(DeliveryLog.broadcast_id == broadcast_id)
        .group_by(DeliveryLog.delivery_status)
    )
    return {str(row[0]): row[1] for row in result.all()}
