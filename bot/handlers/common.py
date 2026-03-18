"""
Общие обработчики: /help, /cancel, команда "Мой профиль", обработка неизвестных сообщений.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import UserStatus
from bot.keyboards.user import get_cancel_keyboard, get_user_main_menu, remove_keyboard
from bot.services.user_service import get_user_by_telegram_id
from bot.utils.logger import get_logger

logger = get_logger(__name__)
router = Router(name="common")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Помощь по использованию бота."""
    await message.answer(
        "Этот бот предоставляет доступ к закрытому контенту.\n\n"
        "Для начала работы введите /start и пройдите регистрацию.\n"
        "Вам потребуется ключ доступа.\n\n"
        "Если у вас возникли проблемы — обратитесь к администратору."
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Отменить текущее действие и сбросить FSM."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного действия для отмены.", reply_markup=remove_keyboard())
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=remove_keyboard())
    logger.info("Пользователь tg_id=%s отменил действие", message.from_user.id)


@router.message(F.text == "Отмена")
async def text_cancel(message: Message, state: FSMContext) -> None:
    """Отмена через reply-кнопку."""
    await cmd_cancel(message, state)


@router.message(F.text == "Мой профиль")
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    """Показать профиль пользователя."""
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user is None:
        await message.answer("Профиль не найден. Введите /start для регистрации.")
        return

    status_labels = {
        UserStatus.PENDING: "Ожидает одобрения",
        UserStatus.APPROVED: "Одобрен",
        UserStatus.REJECTED: "Отклонён",
        UserStatus.BANNED: "Заблокирован",
    }

    key_info = ""
    if user.access_key_id:
        key_info = f"\nКлюч доступа: #{user.access_key_id}"

    text = (
        f"Ваш профиль:\n\n"
        f"Имя: {user.entered_first_name or '—'}\n"
        f"Фамилия: {user.entered_last_name or '—'}\n"
        f"Username: @{user.username or '—'}\n"
        f"Telegram ID: {user.telegram_id}\n"
        f"Статус: {status_labels.get(user.status, user.status)}"
        f"{key_info}"
    )
    await message.answer(text)


@router.message(F.text == "Помощь")
async def text_help(message: Message) -> None:
    """Помощь через reply-кнопку."""
    await cmd_help(message)
