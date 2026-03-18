"""
Сервис для управления ключами доступа.
Создание, валидация, проверка, деактивация.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_config
from bot.database.enums import KeyType
from bot.database.models import AccessKey, KeyUsage, User
from bot.utils.generators import generate_key
from bot.utils.logger import get_logger
from bot.utils.validators import validate_key_value

logger = get_logger(__name__)

PAGE_SIZE = 10


async def get_key_by_value(session: AsyncSession, key_value: str) -> Optional[AccessKey]:
    """Найти ключ по значению."""
    result = await session.execute(
        select(AccessKey).where(AccessKey.key_value == key_value.strip().upper())
    )
    return result.scalar_one_or_none()


async def get_key_by_id(session: AsyncSession, key_id: int) -> Optional[AccessKey]:
    """Найти ключ по id."""
    result = await session.execute(select(AccessKey).where(AccessKey.id == key_id))
    return result.scalar_one_or_none()


async def validate_key_for_user(
    session: AsyncSession, key_value: str, user: User
) -> tuple[bool, str, Optional[AccessKey]]:
    """
    Проверить ключ при регистрации пользователя.

    Returns:
        (valid, error_message, key_object)
        Если valid=True, error_message="", key_object заполнен.
    """
    # Формат ключа
    ok, cleaned = validate_key_value(key_value)
    if not ok:
        return False, "Некорректный формат ключа.", None

    key = await get_key_by_value(session, cleaned)
    if key is None:
        return False, "Ключ не найден. Проверьте правильность ввода.", None

    if not key.is_active:
        return False, "Этот ключ деактивирован.", None

    if key.is_expired:
        return False, "Срок действия ключа истёк.", None

    if key.is_exhausted:
        return False, "Лимит использований этого ключа исчерпан.", None

    # Для одноразового ключа проверим, не использовал ли уже кто-то его
    if key.key_type == KeyType.ONE_TIME and key.usage_count >= 1:
        return False, "Этот ключ уже был использован.", None

    return True, "", key


async def create_key(
    session: AsyncSession,
    key_type: KeyType,
    admin_user: User,
    custom_value: Optional[str] = None,
    usage_limit: Optional[int] = None,
    expires_at: Optional[datetime] = None,
) -> AccessKey:
    """
    Создать новый ключ доступа.

    Args:
        custom_value: Если None — ключ генерируется автоматически.
        usage_limit: None = безлимит (только для reusable).
    """
    config = get_config()

    if custom_value:
        ok, cleaned = validate_key_value(custom_value)
        if not ok:
            raise ValueError(f"Некорректный ключ: {cleaned}")
        key_value = cleaned
    else:
        # Генерация + проверка уникальности
        for _ in range(10):
            candidate = generate_key(config.key_prefix, config.key_random_length)
            existing = await get_key_by_value(session, candidate)
            if existing is None:
                key_value = candidate
                break
        else:
            raise RuntimeError("Не удалось сгенерировать уникальный ключ.")

    key = AccessKey(
        key_value=key_value,
        key_type=key_type,
        created_by_admin_id=admin_user.id,
        usage_limit=usage_limit if key_type == KeyType.REUSABLE else 1,
        expires_at=expires_at,
        is_active=True,
        usage_count=0,
    )
    session.add(key)
    await session.flush()
    logger.info(
        "Создан ключ: value=%s type=%s admin=%s",
        key_value, key_type, admin_user.telegram_id,
    )
    return key


async def record_key_usage(
    session: AsyncSession, key: AccessKey, user: User
) -> None:
    """Записать использование ключа и увеличить счётчик."""
    usage = KeyUsage(key_id=key.id, user_id=user.id)
    session.add(usage)
    key.usage_count += 1

    # Одноразовый ключ после использования деактивируем
    if key.key_type == KeyType.ONE_TIME:
        key.is_active = False

    await session.flush()
    logger.info("Ключ %s использован пользователем tg_id=%s", key.key_value, user.telegram_id)


async def deactivate_key(session: AsyncSession, key: AccessKey) -> None:
    """Деактивировать ключ (is_active = False)."""
    key.is_active = False
    await session.flush()
    logger.info("Ключ %s деактивирован", key.key_value)


async def activate_key(session: AsyncSession, key: AccessKey) -> None:
    """Активировать ключ (is_active = True)."""
    key.is_active = True
    await session.flush()
    logger.info("Ключ %s активирован", key.key_value)


async def delete_key(session: AsyncSession, key: AccessKey) -> None:
    """Удалить ключ."""
    await session.delete(key)
    await session.flush()
    logger.info("Ключ %s удалён", key.key_value)


async def get_keys_paginated(
    session: AsyncSession, page: int = 0
) -> list[AccessKey]:
    """Получить список ключей с пагинацией."""
    result = await session.execute(
        select(AccessKey)
        .order_by(AccessKey.created_at.desc())
        .offset(page * PAGE_SIZE)
        .limit(PAGE_SIZE + 1)
    )
    return list(result.scalars().all())


async def get_all_keys(session: AsyncSession) -> list[AccessKey]:
    """Получить все ключи (для статистики)."""
    result = await session.execute(
        select(AccessKey).order_by(AccessKey.created_at.desc())
    )
    return list(result.scalars().all())
