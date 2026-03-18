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
    ViewBroadcastCallback,
    get_cancel_keyboard,
    get_registration_start_keyboard,
    get_user_main_menu,
    remove_keyboard,
)
from bot.services.approval_service import create_approval_request, get_pending_request_for_user
from bot.services.auth_service import is_user_banned
from bot.services.broadcast_service import get_highlighted_broadcasts, get_last_broadcasts, send_broadcast_content_to_user
from bot.services.key_service import validate_key_for_user
from bot.services.user_service import (
    get_or_create_user,
    get_user_by_telegram_id,
    set_registration_data,
    update_last_seen,
)
from bot.services.viewer_code_service import validate_viewer_code
from bot.states.registration import RegistrationStates
from bot.states.viewer import ViewerStates
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

    # Рекламное сообщение с VPN-ссылкой
    await message.answer(
        'Если у вас не работает или плохо работает телеграмм, советую вот этот VPN\n'
        '<a href="https://t.me/FixPriceVPN_bot?start=partner_2046293957">https://t.me/FixPriceVPN_bot?start=partner_2046293957</a>'
    )

    # --- Маршрутизация по статусу ---

    if is_user_banned(user):
        await message.answer(
            "Ваш аккаунт заблокирован.\n"
            "Если вы считаете это ошибкой — обратитесь к администратору.",
            reply_markup=remove_keyboard(),
        )
        return

    if user.status == UserStatus.APPROVED:
        is_admin = tg_user.id in get_admin_ids()
        await message.answer(
            f"С возвращением, {user.entered_first_name or tg_user.first_name}!\n"
            "Вы авторизованы и имеете доступ.",
            reply_markup=get_user_main_menu(is_admin=is_admin),
        )
        return

    if user.status == UserStatus.PENDING:
        # Показать "заявка на рассмотрении" только если заявка реально существует
        pending_request = await get_pending_request_for_user(session, user.id)
        if pending_request:
            await message.answer(
                "Ваша заявка уже находится на рассмотрении.\n"
                "Пожалуйста, дождитесь решения администратора.",
                reply_markup=remove_keyboard(),
            )
            return
        # Заявки нет — пользователь ещё не прошёл регистрацию
        await _start_registration(message, state)
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

    request, created = await create_approval_request(session, user, key)
    await state.clear()
    await message.answer(
        "Заявка отправлена администратору.\n\n"
        "Вы получите уведомление после рассмотрения вашей заявки.",
        reply_markup=remove_keyboard(),
    )
    if created:
        await _notify_admins_about_request(bot, session, user, request)


# ---------------------------------------------------------------------------
# Последние сообщения администратора
# ---------------------------------------------------------------------------


@router.message(F.text == "📌 Актуальное")
async def show_highlighted(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Запросить код для просмотра актуальных сообщений."""
    broadcasts = await get_highlighted_broadcasts(session)
    if not broadcasts:
        await message.answer("Актуальных сообщений пока нет.")
        return
    await state.set_state(ViewerStates.waiting_code)
    await state.update_data(view_type="highlighted")
    await message.answer(
        f"📌 Актуальных сообщений: {len(broadcasts)}\n\n"
        "Введите код для просмотра (доступны 5 минут):",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(F.text == "📨 Последние сообщения")
async def show_last_messages(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Запросить код для просмотра последних сообщений."""
    broadcasts = await get_last_broadcasts(session, limit=5)
    if not broadcasts:
        await message.answer("Сообщений от администратора пока нет.")
        return
    await state.set_state(ViewerStates.waiting_code)
    await state.update_data(view_type="last")
    await message.answer(
        f"📨 Последних сообщений: {len(broadcasts)}\n\n"
        "Введите код для просмотра (доступны 5 минут):",
        reply_markup=get_cancel_keyboard(),
    )


@router.callback_query(ViewBroadcastCallback.filter())
async def view_broadcast_by_button(
    call: CallbackQuery,
    callback_data: ViewBroadcastCallback,
    state: FSMContext,
) -> None:
    """Нажатие кнопки 'Просмотреть' на уведомлении о рассылке."""
    await state.set_state(ViewerStates.waiting_code)
    await state.update_data(
        view_type="broadcast",
        broadcast_id=callback_data.broadcast_id,
        notification_message_id=call.message.message_id,
    )
    await call.message.answer(
        "Введите код для просмотра сообщения (доступно 5 минут):",
        reply_markup=get_cancel_keyboard(),
    )
    await call.answer()


@router.message(ViewerStates.waiting_code)
async def process_viewer_code(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Обработать введённый код просмотра."""
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=remove_keyboard())
        return

    valid = await validate_viewer_code(session, message.text or "")

    # Удалить сообщение с кодом из чата
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        pass

    if not valid:
        await message.answer(
            "Неверный код. Попробуйте ещё раз:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    await state.clear()
    view_type = data.get("view_type")

    await message.answer(
        "✅ Код принят. Сообщения будут удалены через 5 минут.",
        reply_markup=remove_keyboard(),
    )

    if view_type == "broadcast":
        from bot.database.models import Broadcast
        from sqlalchemy import select
        result = await session.execute(
            select(Broadcast).where(Broadcast.id == data.get("broadcast_id"))
        )
        broadcast = result.scalar_one_or_none()
        if broadcast:
            await send_broadcast_content_to_user(
                bot, broadcast, message.from_user.id,
                notification_message_id=data.get("notification_message_id"),
            )

    elif view_type == "highlighted":
        broadcasts = await get_highlighted_broadcasts(session)
        for bc in broadcasts:
            await send_broadcast_content_to_user(bot, bc, message.from_user.id)

    elif view_type == "last":
        broadcasts = await get_last_broadcasts(session, limit=5)
        for bc in broadcasts:
            await send_broadcast_content_to_user(bot, bc, message.from_user.id)


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
