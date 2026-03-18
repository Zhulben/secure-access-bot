"""
Сервис глобального кода просмотра рассылок.
Один код на всех — администратор управляет им из панели.
"""
import secrets
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import ViewerCode
from bot.utils.logger import get_logger

logger = get_logger(__name__)

_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 8


def _make_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


async def get_viewer_code(session: AsyncSession) -> str | None:
    """Вернуть текущий код просмотра или None если ещё не создан."""
    result = await session.execute(select(ViewerCode).limit(1))
    vc = result.scalar_one_or_none()
    return vc.code if vc else None


async def get_or_create_viewer_code(session: AsyncSession) -> str:
    """Вернуть текущий код, создать новый если нет."""
    result = await session.execute(select(ViewerCode).limit(1))
    vc = result.scalar_one_or_none()
    if vc is None:
        code = _make_code()
        vc = ViewerCode(code=code)
        session.add(vc)
        await session.flush()
        logger.info("Создан новый код просмотра: %s", code)
    return vc.code


async def regenerate_viewer_code(session: AsyncSession) -> str:
    """Сгенерировать новый код просмотра и сохранить."""
    result = await session.execute(select(ViewerCode).limit(1))
    vc = result.scalar_one_or_none()
    code = _make_code()
    if vc is None:
        vc = ViewerCode(code=code)
        session.add(vc)
    else:
        vc.code = code
    await session.flush()
    logger.info("Код просмотра обновлён: %s", code)
    return code


async def validate_viewer_code(session: AsyncSession, entered: str) -> bool:
    """Проверить введённый код."""
    result = await session.execute(select(ViewerCode).limit(1))
    vc = result.scalar_one_or_none()
    if vc is None:
        return False
    return vc.code.upper() == entered.strip().upper()
