"""
Обработчики для обычных пользователей:
- /start (с проверкой статуса и антидублированием)
- Процесс регистрации (FSM: имя → фамилия → ключ)
"""
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import UserStatus
from bot.keyboards.user import (
    get_cancel_keyboard,
    get_registration_start_keyboard,
    get_user_main_menu,
    remove_keyboard,
)
from bot.services.approval_service import create_approval_request
from bot.services.auth_service import is_user_banned
from bot.services.key_service import validate_key_for_user
from bot.services.user_service import (
    get_or_create_user,
    set_registration_data,
    update_last_seen,
)
from bot.states.registration import RegistrationStates
from bot.utils.logger import get_logger
from bot.utils.security import get_admin_ids

logger = get_logger(__name__)
router = Router(name="user")


# ---------------------------------------------------------------------------
# /start — точка входа
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """
    Обработчик команды /start.
    Логика:
    1. Получить/создать пользователя (антидублирование через get_or_create_user).
    2. Обновить last_seen.
    3. Направить в нужную ветку по статусу.
    """
    tg_user = message.from_user
    user, is_new = await get_or_create_user(
        session=session,
        telegram_id=tg_user.id,
        username=tg_user.username,
        tg_first_name=tg_user.first_name,
        tg_last_name=tg_user.last_name,
    )
    await update_last_seen(session, user)

    logger.info(
        "Пользователь tg_id=%s (%s) запустил бота. Новый: %s. Статус: %s",
        tg_user.id, tg_user.username, is_new, user.status,
    )

    # Сбросить FSM, если пользователь повторно нажал /start во время регистрации
    await state.clear()

    # --- Маршрутизация по статусу ---

    if is_user_banned(user):
        await message.answer(
            "Ваш аккаунт заблокирован.\n"
            "Если вы считаете это ошибкой — обратитесь к администратору.",
            reply_markup=remove_keyboard(),
        )
        return

    if user.status == UserStatus.APPROVED:
        await message.answer(
            f"С возвращением, {user.entered_first_name or tg_user.first_name}!\n"
            "Вы авторизованы и имеете доступ.",
            reply_markup=get_user_main_menu(),
        )
        return

    if user.status == UserStatus.PENDING:
        await message.answer(
            "Ваша заявка уже находится на рассмотрении.\n"
            "Пожалуйста, дождитесь решения администратора.",
            reply_markup=remove_keyboard(),
        )
        return

    if user.status == UserStatus.REJECTED:
        await message.answer(
            "Ваша заявка была отклонена.\n"
            "Если хотите попробовать снова — нажмите кнопку ниже.",
            reply_markup=get_registration_start_keyboard(),
        )
        return

    # Новый пользователь или статус позволяет начать регистрацию заново
    await _start_registration(message, state)


@router.callback_query(F.data == "start_registration")
async def callback_start_registration(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Начало регистрации после повторного /start для rejected-пользователей."""
    # Сбросить старый статус на PENDING при повторной попытке
    from bot.services.user_service import get_user_by_telegram_id
    from bot.database.enums import UserStatus

    user = await get_user_by_telegram_id(session, call.from_user.id)
    if user and user.status == UserStatus.REJECTED:
        user.status = UserStatus.PENDING
        # Сбросить rejected_at
        user.rejected_at = None
        await session.flush()

    await call.message.delete()
    await _start_registration(call.message, state)
    await call.answer()


# ---------------------------------------------------------------------------
# Вспомогательная функция старта регистрации
# ---------------------------------------------------------------------------


async def _start_registration(message: Message, state: FSMContext) -> None:
    """Начать FSM-регистрацию: запросить имя."""
    await state.set_state(RegistrationStates.waiting_first_name)
    await message.answer(
        "Добро пожаловать! Давайте пройдём регистрацию.\n\n"
        "Шаг 1 из 3: Введите ваше имя:",
        reply_markup=get_cancel_keyboard(),
    )


# ---------------------------------------------------------------------------
# FSM: Ввод имени
# ---------------------------------------------------------------------------


@router.message(RegistrationStates.waiting_first_name)
async def process_first_name(message: Message, state: FSMContext) -> None:
    """Обработать ввод имени."""
    from bot.utils.validators import validate_name

    ok, result = validate_name(message.text or "")
    if not ok:
        await message.answer(
            f"Некорректное имя: {result}\n\nПожалуйста, введите имя ещё раз:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(first_name=result)
    await state.set_state(RegistrationStates.waiting_last_name)
    await message.answer(
        f"Имя принято: {result}\n\n"
        "Шаг 2 из 3: Введите вашу фамилию:",
        reply_markup=get_cancel_keyboard(),
    )


# ---------------------------------------------------------------------------
# FSM: Ввод фамилии
# ---------------------------------------------------------------------------


@router.message(RegistrationStates.waiting_last_name)
async def process_last_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Обработать ввод фамилии."""
    from bot.utils.validators import validate_name

    ok, result = validate_name(message.text or "")
    if not ok:
        await message.answer(
            f"Некорректная фамилия: {result}\n\nПожалуйста, введите фамилию ещё раз:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    first_name = data["first_name"]

    # Сохранить в БД
    from bot.services.user_service import get_user_by_telegram_id
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user:
        await set_registration_data(session, user, first_name, result)

    await state.update_data(last_name=result)
    await state.set_state(RegistrationStates.waiting_key)
    await message.answer(
        f"Фамилия принята: {result}\n\n"
        "Шаг 3 из 3: Введите ключ доступа.\n"
        "Ключ выдаётся администратором.",
        reply_markup=get_cancel_keyboard(),
    )


# ---------------------------------------------------------------------------
# FSM: Ввод ключа доступа
# ---------------------------------------------------------------------------


@router.message(RegistrationStates.waiting_key)
async def process_key(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Обработать ввод ключа. При успехе — создать заявку и уведомить админов."""
    from bot.services.user_service import get_user_by_telegram_id

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user is None:
        await message.answer("Ошибка: пользователь не найден. Введите /start.")
        await state.clear()
        return

    key_text = message.text or ""
    valid, error_msg, key = await validate_key_for_user(session, key_text, user)

    if not valid:
        await message.answer(
            f"{error_msg}\n\nПопробуйте ввести ключ ещё раз:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    # Создать заявку (антидублирование внутри create_approval_request)
    request, created = await create_approval_request(session, user, key)

    await state.clear()
    await message.answer(
        "Заявка отправлена администратору.\n\n"
        "Вы получите уведомление после рассмотрения вашей заявки.",
        reply_markup=remove_keyboard(),
    )

    if created:
        # Уведомить всех администраторов
        await _notify_admins_about_request(bot, session, user, request)


async def _notify_admins_about_request(
    bot: Bot,
    session: AsyncSession,
    user,
    request,
) -> None:
    """Разослать уведомление о новой заявке всем администраторам."""
    from bot.keyboards.admin import get_approval_keyboard

    text = (
        f"Новая заявка на доступ!\n\n"
        f"Пользователь: {user.display_name}\n"
        f"Telegram ID: {user.telegram_id}\n"
        f"Имя: {user.entered_first_name} {user.entered_last_name}\n"
        f"Заявка #: {request.id}"
    )

    for admin_id in get_admin_ids():
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=get_approval_keyboard(user.id),
            )
        except Exception as e:
            logger.error("Не удалось уведомить администратора tg_id=%s: %s", admin_id, e)
