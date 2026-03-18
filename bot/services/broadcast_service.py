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
        status, error, message_id = await _send_real_message(bot, broadcast, user)
        await _log_delivery(session, broadcast, user, DeliveryMode.REAL, status, error, message_id)
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
) -> tuple[DeliveryStatus, Optional[str], Optional[int]]:
    """Отправить реальный контент одному пользователю. Возвращает (status, error, message_id)."""
    try:
        if broadcast.broadcast_type == BroadcastType.TEXT:
            msg = await bot.send_message(chat_id=user.telegram_id, text=broadcast.text or "")
        elif broadcast.broadcast_type == BroadcastType.PHOTO:
            msg = await bot.send_photo(chat_id=user.telegram_id, photo=broadcast.photo_file_id or "")
        elif broadcast.broadcast_type == BroadcastType.PHOTO_CAPTION:
            msg = await bot.send_photo(
                chat_id=user.telegram_id,
                photo=broadcast.photo_file_id or "",
                caption=broadcast.text or "",
            )
        else:
            return DeliveryStatus.FAILED, "Неизвестный тип рассылки", None
        return DeliveryStatus.SUCCESS, None, msg.message_id

    except TelegramForbiddenError:
        return DeliveryStatus.FAILED, "Пользователь заблокировал бота", None

    except TelegramRetryAfter as e:
        logger.warning("Flood control, жду %s секунд", e.retry_after)
        await asyncio.sleep(e.retry_after)
        try:
            if broadcast.broadcast_type == BroadcastType.TEXT:
                msg = await bot.send_message(chat_id=user.telegram_id, text=broadcast.text or "")
            elif broadcast.broadcast_type == BroadcastType.PHOTO:
                msg = await bot.send_photo(chat_id=user.telegram_id, photo=broadcast.photo_file_id or "")
            elif broadcast.broadcast_type == BroadcastType.PHOTO_CAPTION:
                msg = await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=broadcast.photo_file_id or "",
                    caption=broadcast.text or "",
                )
            else:
                return DeliveryStatus.FAILED, "Неизвестный тип рассылки", None
            return DeliveryStatus.SUCCESS, None, msg.message_id
        except TelegramAPIError as retry_err:
            return DeliveryStatus.FAILED, str(retry_err), None

    except TelegramAPIError as e:
        return DeliveryStatus.FAILED, str(e), None


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
    message_id: Optional[int] = None,
) -> None:
    """Записать результат доставки в БД."""
    log = DeliveryLog(
        broadcast_id=broadcast.id,
        user_id=user.id,
        delivery_mode=mode,
        delivery_status=status,
        message_id=message_id,
        error_text=error,
    )
    session.add(log)
    # Не делаем flush здесь — накапливаем и flush в конце рассылки


async def get_highlighted_broadcasts(session: AsyncSession) -> list:
    """Получить все выделенные рассылки (от старых к новым)."""
    from sqlalchemy import select
    from bot.database.models import Broadcast
    result = await session.execute(
        select(Broadcast)
        .where(Broadcast.is_highlighted == True)
        .order_by(Broadcast.created_at.asc())
    )
    return list(result.scalars().all())


async def toggle_highlight_broadcast(session: AsyncSession, broadcast_id: int) -> bool:
    """Переключить выделение рассылки. Возвращает новое значение."""
    from sqlalchemy import select
    from bot.database.models import Broadcast
    result = await session.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()
    if broadcast is None:
        return False
    broadcast.is_highlighted = not broadcast.is_highlighted
    await session.flush()
    return broadcast.is_highlighted


async def get_last_broadcasts(session: AsyncSession, limit: int = 5) -> list:
    """Получить последние N рассылок (от старых к новым)."""
    from sqlalchemy import select
    from bot.database.models import Broadcast
    result = await session.execute(
        select(Broadcast).order_by(Broadcast.created_at.desc()).limit(limit)
    )
    broadcasts = list(result.scalars().all())
    broadcasts.reverse()
    return broadcasts


async def delete_broadcast_messages(
    bot: Bot,
    session: AsyncSession,
    count: int,
) -> dict[str, int]:
    """
    Удалить сообщения последних N рассылок из чатов всех получателей.
    Возвращает {"deleted": N, "failed": N}.
    """
    from sqlalchemy import select
    from bot.database.models import Broadcast, DeliveryLog
    from bot.database.enums import DeliveryMode, DeliveryStatus

    # Найти последние count рассылок
    result = await session.execute(
        select(Broadcast).order_by(Broadcast.created_at.desc()).limit(count)
    )
    broadcasts = list(result.scalars().all())
    if not broadcasts:
        return {"deleted": 0, "failed": 0}

    broadcast_ids = [b.id for b in broadcasts]

    # Найти все delivery_logs с message_id для этих рассылок
    logs_result = await session.execute(
        select(DeliveryLog).where(
            DeliveryLog.broadcast_id.in_(broadcast_ids),
            DeliveryLog.delivery_mode == DeliveryMode.REAL,
            DeliveryLog.delivery_status == DeliveryStatus.SUCCESS,
            DeliveryLog.message_id.is_not(None),
        )
    )
    logs = list(logs_result.scalars().all())

    stats = {"deleted": 0, "failed": 0}
    for log in logs:
        # Получаем telegram_id пользователя
        from bot.services.user_service import get_user_by_id
        user = await get_user_by_id(session, log.user_id)
        if user is None:
            continue
        try:
            await bot.delete_message(chat_id=user.telegram_id, message_id=log.message_id)
            stats["deleted"] += 1
        except Exception:
            stats["failed"] += 1
        await asyncio.sleep(SEND_DELAY_MS / 1000)

    logger.info("Удалено сообщений рассылок: %s", stats)
    return stats


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
        status, error, message_id = await _send_real_message(bot, broadcast, user)
        await _log_delivery(session, broadcast, user, DeliveryMode.REAL, status, error, message_id)
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


async def clear_user_chats(
    bot: Bot,
    session: AsyncSession,
) -> dict[str, int]:
    """
    Полная очистка всей истории чата бота с каждым одобренным пользователем.
    Отправляет зондовое сообщение, узнаёт max_id, удаляет все сообщения батчами по 100.
    """
    from bot.services.user_service import get_approved_users

    users = await get_approved_users(session)
    stats = {"deleted": 0, "failed": 0}

    for user in users:
        try:
            probe = await bot.send_message(chat_id=user.telegram_id, text=".")
            max_id = probe.message_id
            await bot.delete_message(chat_id=user.telegram_id, message_id=max_id)

            # Удаляем батчами по 100 — Telegram поддерживает до 100 за раз
            all_ids = list(range(max_id - 1, 0, -1))
            for i in range(0, len(all_ids), 100):
                batch = all_ids[i:i + 100]
                try:
                    await bot.delete_messages(chat_id=user.telegram_id, message_ids=batch)
                    stats["deleted"] += len(batch)
                except Exception:
                    # Если батч не прошёл — пробуем поштучно
                    for msg_id in batch:
                        try:
                            await bot.delete_message(chat_id=user.telegram_id, message_id=msg_id)
                            stats["deleted"] += 1
                        except Exception:
                            stats["failed"] += 1

        except Exception as e:
            logger.warning("Не удалось очистить чат с tg_id=%s: %s", user.telegram_id, e)
            stats["failed"] += 1

    logger.info("Очистка чатов завершена: %s", stats)
    return stats


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
