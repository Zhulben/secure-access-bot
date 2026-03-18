"""
Сервис для работы с пользователями.
Создание, обновление, поиск — без бизнес-логики одобрений/банов (это в admin_service).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete as sql_delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import UserRole, UserStatus
from bot.database.models import User
from bot.utils.logger import get_logger
from bot.utils.security import is_admin_by_telegram_id

logger = get_logger(__name__)

# Количество пользователей на одной странице
PAGE_SIZE = 10


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> Optional[User]:
    """Найти пользователя по telegram_id."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    """Найти пользователя по внутреннему id."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    tg_first_name: Optional[str],
    tg_last_name: Optional[str],
) -> tuple[User, bool]:
    """
    Получить или создать пользователя.

    Returns:
        (user, created) — created=True если пользователь создан впервые.
    """
    user = await get_user_by_telegram_id(session, telegram_id)

    if user is None:
        # Определить роль: если telegram_id в ADMIN_IDS — сразу ADMIN + APPROVED
        role = UserRole.ADMIN if is_admin_by_telegram_id(telegram_id) else UserRole.USER
        status = UserStatus.APPROVED if role == UserRole.ADMIN else UserStatus.PENDING

        user = User(
            telegram_id=telegram_id,
            username=username,
            tg_first_name=tg_first_name,
            tg_last_name=tg_last_name,
            role=role,
            status=status,
        )
        session.add(user)
        await session.flush()  # Получить id без commit
        logger.info("Создан новый пользователь: tg_id=%s role=%s", telegram_id, role)
        return user, True

    # Обновить данные Telegram (могут измениться)
    updated = False
    if user.username != username:
        user.username = username
        updated = True
    if user.tg_first_name != tg_first_name:
        user.tg_first_name = tg_first_name
        updated = True
    if user.tg_last_name != tg_last_name:
        user.tg_last_name = tg_last_name
        updated = True

    if updated:
        await session.flush()

    return user, False


async def update_last_seen(session: AsyncSession, user: User) -> None:
    """Обновить время последнего визита."""
    user.last_seen_at = datetime.now(timezone.utc)
    await session.flush()


async def set_registration_data(
    session: AsyncSession,
    user: User,
    first_name: str,
    last_name: str,
) -> None:
    """Сохранить введённые пользователем имя и фамилию."""
    user.entered_first_name = first_name
    user.entered_last_name = last_name
    await session.flush()


async def get_users_by_status(
    session: AsyncSession,
    status: UserStatus,
    page: int = 0,
) -> list[User]:
    """Получить список пользователей с заданным статусом (с пагинацией)."""
    result = await session.execute(
        select(User)
        .where(User.status == status)
        .order_by(User.created_at.desc())
        .offset(page * PAGE_SIZE)
        .limit(PAGE_SIZE + 1)  # +1 для определения наличия следующей страницы
    )
    return list(result.scalars().all())


async def get_all_users(
    session: AsyncSession,
    page: int = 0,
    exclude_status: Optional[UserStatus] = None,
) -> list[User]:
    """Получить всех пользователей с пагинацией."""
    query = select(User).order_by(User.created_at.desc())
    if exclude_status:
        query = query.where(User.status != exclude_status)
    query = query.offset(page * PAGE_SIZE).limit(PAGE_SIZE + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_approved_users(session: AsyncSession) -> list[User]:
    """Получить всех одобренных пользователей (для рассылки)."""
    result = await session.execute(
        select(User).where(User.status == UserStatus.APPROVED)
    )
    return list(result.scalars().all())


async def get_pending_users(session: AsyncSession) -> list[User]:
    """Получить всех pending-пользователей (для masked-рассылки)."""
    result = await session.execute(
        select(User).where(User.status == UserStatus.PENDING)
    )
    return list(result.scalars().all())


async def get_users_count_by_status(session: AsyncSession) -> dict[str, int]:
    """Получить количество пользователей по каждому статусу."""
    result = await session.execute(
        select(User.status, func.count(User.id)).group_by(User.status)
    )
    return {str(row[0]): row[1] for row in result.all()}


async def clear_all_users(session: AsyncSession, except_telegram_id: int) -> int:
    """Удалить всех пользователей кроме указанного. Возвращает количество удалённых."""
    result = await session.execute(
        sql_delete(User).where(User.telegram_id != except_telegram_id)
    )
    await session.flush()
    count = result.rowcount
    logger.info("Очищено пользователей: %d (кроме tg_id=%s)", count, except_telegram_id)
    return count


async def search_users(
    session: AsyncSession,
    query: str,
) -> list[User]:
    """
    Поиск пользователей по username или telegram_id.
    Возвращает не более 20 результатов.
    """
    query_clean = query.strip().lstrip("@")

    conditions = []
    if query_clean.isdigit():
        conditions.append(User.telegram_id == int(query_clean))
    conditions.append(User.username.ilike(f"%{query_clean}%"))
    conditions.append(User.entered_first_name.ilike(f"%{query_clean}%"))
    conditions.append(User.entered_last_name.ilike(f"%{query_clean}%"))

    from sqlalchemy import or_
    result = await session.execute(
        select(User).where(or_(*conditions)).limit(20)
    )
    return list(result.scalars().all())
