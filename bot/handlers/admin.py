"""
Обработчики для администраторов.
Управление пользователями, ключами, рассылкой и статистикой.
Все роуты защищены AdminMiddleware.
"""
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.enums import BroadcastType, KeyType, UserStatus
from bot.database.models import User
from bot.keyboards.admin import (
    BroadcastActionCallback,
    KeyActionCallback,
    KeyTypeCallback,
    PaginationCallback,
    PendingBroadcastCallback,
    UserActionCallback,
    get_admin_main_menu,
    get_approval_keyboard,
    get_broadcast_confirm_keyboard,
    get_broadcast_type_keyboard,
    get_custom_or_auto_key_keyboard,
    get_key_actions_keyboard,
    get_key_confirm_delete_keyboard,
    get_key_list_keyboard,
    get_key_type_keyboard,
    get_pending_broadcast_keyboard,
    get_pending_requests_keyboard,
    get_skip_keyboard,
    get_user_actions_keyboard,
    get_users_list_keyboard,
)
from bot.keyboards.user import get_cancel_keyboard, remove_keyboard
from bot.services.admin_service import approve_user, ban_user, reject_user, unban_user
from bot.services.approval_service import (
    get_all_pending_requests,
    get_pending_request_for_user,
)
from bot.services.broadcast_service import create_broadcast, send_broadcast
from bot.services.key_service import (
    activate_key,
    create_key,
    deactivate_key,
    delete_key,
    get_key_by_id,
    get_keys_paginated,
)
from bot.services.user_service import (
    PAGE_SIZE,
    get_all_users,
    get_user_by_id,
    get_users_by_status,
    get_users_count_by_status,
    search_users,
)
from bot.states.admin import UserSearchStates
from bot.states.broadcast import BroadcastStates
from bot.states.key_management import KeyCreateStates
from bot.utils.logger import get_logger
from bot.utils.validators import validate_broadcast_text, validate_key_value

logger = get_logger(__name__)
router = Router(name="admin")


# ---------------------------------------------------------------------------
# Главное меню
# ---------------------------------------------------------------------------


@router.message(Command("admin"))
async def cmd_admin(message: Message, admin_user: Optional[User]) -> None:
    """Открыть главное меню администратора."""
    if admin_user is None:
        await message.answer("У вас нет прав администратора.")
        return
    await message.answer(
        f"Панель управления.\n"
        f"Вы вошли как: {admin_user.display_name}",
        reply_markup=get_admin_main_menu(),
    )


# ---------------------------------------------------------------------------
# Раздел: Заявки (Pending)
# ---------------------------------------------------------------------------


@router.message(F.text == "Заявки")
async def show_pending_requests(
    message: Message,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Показать список ожидающих заявок."""
    if admin_user is None:
        return

    requests = await get_all_pending_requests(session)
    if not requests:
        await message.answer("Нет ожидающих заявок.", reply_markup=get_admin_main_menu())
        return

    # Загружаем данные пользователей для отображения
    items: list[tuple[int, str, int]] = []
    for req in requests:
        user = await get_user_by_id(session, req.user_id)
        if user:
            items.append((req.id, user.display_name, user.id))

    await message.answer(
        f"Заявки на рассмотрении: {len(items)}",
        reply_markup=get_pending_requests_keyboard(items),
    )


@router.callback_query(UserActionCallback.filter(F.action == "view"))
async def view_user_request(
    call: CallbackQuery,
    callback_data: UserActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Показать детали пользователя и кнопки действий."""
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    user = await get_user_by_id(session, callback_data.user_id)
    if user is None:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    request = await get_pending_request_for_user(session, user.id)
    is_banned = user.status == UserStatus.BANNED

    status_labels = {
        UserStatus.PENDING: "Ожидает одобрения",
        UserStatus.APPROVED: "Одобрен",
        UserStatus.REJECTED: "Отклонён",
        UserStatus.BANNED: "Заблокирован",
    }

    text = (
        f"Пользователь: {user.display_name}\n"
        f"Telegram ID: {user.telegram_id}\n"
        f"Имя: {user.entered_first_name or '—'} {user.entered_last_name or '—'}\n"
        f"Статус: {status_labels.get(user.status, str(user.status))}\n"
        f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else '—'}"
    )

    if request is not None:
        keyboard = get_approval_keyboard(user.id)
    else:
        keyboard = get_user_actions_keyboard(user.id, is_banned)

    await call.message.edit_text(text, reply_markup=keyboard)
    await call.answer()


@router.callback_query(UserActionCallback.filter(F.action == "approve"))
async def approve_user_callback(
    call: CallbackQuery,
    callback_data: UserActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
    bot: Bot,
) -> None:
    """Одобрить заявку пользователя."""
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    user = await get_user_by_id(session, callback_data.user_id)
    if user is None:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    request = await get_pending_request_for_user(session, user.id)
    if request is None:
        await call.answer("Активная заявка не найдена.", show_alert=True)
        return

    await approve_user(session, user, request, admin_user)

    logger.info(
        "Администратор tg_id=%s одобрил пользователя tg_id=%s",
        admin_user.telegram_id, user.telegram_id,
    )

    await call.message.edit_text(
        f"Пользователь {user.display_name} одобрен."
    )
    await call.answer("Пользователь одобрен!")

    # Уведомить пользователя
    await _notify_user(
        bot,
        user.telegram_id,
        "Ваша заявка одобрена! Добро пожаловать!\n\nВведите /start для начала работы.",
    )


@router.callback_query(UserActionCallback.filter(F.action == "reject"))
async def reject_user_callback(
    call: CallbackQuery,
    callback_data: UserActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
    bot: Bot,
) -> None:
    """Отклонить заявку пользователя."""
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    user = await get_user_by_id(session, callback_data.user_id)
    if user is None:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    request = await get_pending_request_for_user(session, user.id)
    if request is None:
        await call.answer("Активная заявка не найдена.", show_alert=True)
        return

    await reject_user(session, user, request, admin_user)

    logger.info(
        "Администратор tg_id=%s отклонил пользователя tg_id=%s",
        admin_user.telegram_id, user.telegram_id,
    )

    await call.message.edit_text(f"Пользователь {user.display_name} отклонён.")
    await call.answer("Пользователь отклонён.")

    await _notify_user(
        bot,
        user.telegram_id,
        "К сожалению, ваша заявка была отклонена.\n"
        "Вы можете попробовать снова через /start.",
    )


@router.callback_query(UserActionCallback.filter(F.action == "back"))
async def back_to_requests(
    call: CallbackQuery,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Вернуться к списку заявок."""
    if admin_user is None:
        await call.answer()
        return
    requests = await get_all_pending_requests(session)
    items: list[tuple[int, str, int]] = []
    for req in requests:
        user = await get_user_by_id(session, req.user_id)
        if user:
            items.append((req.id, user.display_name, user.id))

    if not items:
        await call.message.edit_text("Нет ожидающих заявок.")
    else:
        await call.message.edit_text(
            f"Заявки на рассмотрении: {len(items)}",
            reply_markup=get_pending_requests_keyboard(items),
        )
    await call.answer()


# ---------------------------------------------------------------------------
# Раздел: Пользователи (все)
# ---------------------------------------------------------------------------


@router.message(F.text == "Пользователи")
async def show_all_users(
    message: Message,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Показать список всех пользователей."""
    if admin_user is None:
        return
    await _render_users_list(message, session, page=0)


async def _render_users_list(
    message: Message,
    session: AsyncSession,
    page: int,
) -> None:
    """Отрисовать список пользователей с пагинацией."""
    raw_users = await get_all_users(session, page=page)
    has_next = len(raw_users) > PAGE_SIZE
    users = raw_users[:PAGE_SIZE]

    if not users:
        await message.answer("Пользователи не найдены.")
        return

    items = [(u.id, u.display_name) for u in users]
    await message.answer(
        f"Все пользователи (стр. {page + 1}):",
        reply_markup=get_users_list_keyboard(items, page=page, has_next=has_next),
    )


@router.callback_query(PaginationCallback.filter(F.section == "users_all"))
async def paginate_users(
    call: CallbackQuery,
    callback_data: PaginationCallback,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer()
        return
    page = callback_data.page
    raw_users = await get_all_users(session, page=page)
    has_next = len(raw_users) > PAGE_SIZE
    users = raw_users[:PAGE_SIZE]
    items = [(u.id, u.display_name) for u in users]
    await call.message.edit_text(
        f"Все пользователи (стр. {page + 1}):",
        reply_markup=get_users_list_keyboard(items, page=page, has_next=has_next),
    )
    await call.answer()


# ---------------------------------------------------------------------------
# Бан / Разбан
# ---------------------------------------------------------------------------


@router.callback_query(UserActionCallback.filter(F.action == "ban"))
async def ban_user_callback(
    call: CallbackQuery,
    callback_data: UserActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
    bot: Bot,
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    user = await get_user_by_id(session, callback_data.user_id)
    if user is None:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    await ban_user(session, user, admin_user)

    logger.info(
        "Администратор tg_id=%s заблокировал пользователя tg_id=%s",
        admin_user.telegram_id, user.telegram_id,
    )

    await call.message.edit_text(
        f"Пользователь {user.display_name} заблокирован."
    )
    await call.answer("Пользователь заблокирован.")

    await _notify_user(
        bot,
        user.telegram_id,
        "Ваш аккаунт был заблокирован администратором.",
    )


@router.callback_query(UserActionCallback.filter(F.action == "unban"))
async def unban_user_callback(
    call: CallbackQuery,
    callback_data: UserActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
    bot: Bot,
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    user = await get_user_by_id(session, callback_data.user_id)
    if user is None:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    await unban_user(session, user, admin_user)

    logger.info(
        "Администратор tg_id=%s разбанил пользователя tg_id=%s",
        admin_user.telegram_id, user.telegram_id,
    )

    await call.message.edit_text(f"Пользователь {user.display_name} разблокирован.")
    await call.answer("Пользователь разблокирован.")

    await _notify_user(
        bot,
        user.telegram_id,
        "Ваш аккаунт был разблокирован. Введите /start для продолжения.",
    )


# ---------------------------------------------------------------------------
# Раздел: Ключи
# ---------------------------------------------------------------------------


@router.message(F.text == "Ключи")
async def show_keys(
    message: Message,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Показать список ключей с кнопкой создания нового."""
    if admin_user is None:
        return

    raw_keys = await get_keys_paginated(session, page=0)
    has_next = len(raw_keys) > PAGE_SIZE
    keys = raw_keys[:PAGE_SIZE]

    # Кнопка создания + список
    await message.answer(
        "Для создания нового ключа введите /newkey\n\n"
        f"Существующие ключи (стр. 1):",
        reply_markup=get_key_list_keyboard(
            [(k.id, k.key_value, k.key_type, k.is_active) for k in keys],
            page=0,
            has_next=has_next,
        ) if keys else None,
    )
    if not keys:
        await message.answer("Ключей пока нет. Создайте первый через /newkey")


@router.message(Command("newkey"))
async def cmd_new_key(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Начало FSM создания нового ключа."""
    if admin_user is None:
        await message.answer("У вас нет прав администратора.")
        return
    await state.set_state(KeyCreateStates.waiting_key_type)
    await message.answer(
        "Создание нового ключа доступа.\n\n"
        "Выберите тип ключа:",
        reply_markup=get_key_type_keyboard(),
    )


@router.callback_query(KeyTypeCallback.filter())
async def process_key_type_selection(
    call: CallbackQuery,
    callback_data: KeyTypeCallback,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Обработка выбора типа ключа."""
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    current_state = await state.get_state()
    if current_state != KeyCreateStates.waiting_key_type:
        await call.answer()
        return

    await state.update_data(key_type=callback_data.key_type)
    await state.set_state(KeyCreateStates.waiting_custom_value)
    await call.message.edit_text(
        f"Тип ключа: {'Одноразовый' if callback_data.key_type == 'one_time' else 'Многоразовый'}\n\n"
        "Хотите задать значение ключа вручную или сгенерировать автоматически?",
        reply_markup=get_custom_or_auto_key_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data == "key_auto")
async def process_key_auto(
    call: CallbackQuery,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Автоматическая генерация значения ключа."""
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    current_state = await state.get_state()
    if current_state != KeyCreateStates.waiting_custom_value:
        await call.answer()
        return

    await state.update_data(custom_value=None)

    data = await state.get_data()
    if data.get("key_type") == "reusable":
        await state.set_state(KeyCreateStates.waiting_usage_limit)
        await call.message.edit_text(
            "Введите лимит использований (число).\n"
            "Отправьте 0 или нажмите 'Пропустить' для безлимитного ключа:",
            reply_markup=get_skip_keyboard(),
        )
    else:
        await state.set_state(KeyCreateStates.waiting_expires_at)
        await call.message.edit_text(
            "Введите дату истечения ключа в формате ДД.ММ.ГГГГ\n"
            "или нажмите 'Пропустить' для бессрочного ключа:",
            reply_markup=get_skip_keyboard(),
        )
    await call.answer()


@router.callback_query(F.data == "key_manual")
async def process_key_manual_prompt(
    call: CallbackQuery,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Запросить ручной ввод значения ключа."""
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return

    current_state = await state.get_state()
    if current_state != KeyCreateStates.waiting_custom_value:
        await call.answer()
        return

    await call.message.edit_text(
        "Введите значение ключа (латинские буквы, цифры, дефис):\n"
        "Пример: VIP-ACCESS-2024",
    )
    await call.answer()


@router.message(KeyCreateStates.waiting_custom_value)
async def process_key_custom_value(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Принять кастомное значение ключа."""
    if admin_user is None:
        return

    ok, cleaned = validate_key_value(message.text or "")
    if not ok:
        await message.answer(
            f"Некорректное значение: {cleaned}\n\nВведите ключ ещё раз:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(custom_value=cleaned)
    data = await state.get_data()

    if data.get("key_type") == "reusable":
        await state.set_state(KeyCreateStates.waiting_usage_limit)
        await message.answer(
            "Введите лимит использований (число).\n"
            "Отправьте 0 для безлимитного ключа:",
            reply_markup=get_skip_keyboard(),
        )
    else:
        await state.set_state(KeyCreateStates.waiting_expires_at)
        await message.answer(
            "Введите дату истечения ключа в формате ДД.ММ.ГГГГ\n"
            "или нажмите 'Пропустить' для бессрочного ключа:",
            reply_markup=get_skip_keyboard(),
        )


@router.callback_query(F.data == "skip", KeyCreateStates.waiting_usage_limit)
async def skip_usage_limit(
    call: CallbackQuery,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Пропустить лимит использований (безлимитный ключ)."""
    if admin_user is None:
        await call.answer()
        return
    await state.update_data(usage_limit=None)
    await state.set_state(KeyCreateStates.waiting_expires_at)
    await call.message.answer(
        "Введите дату истечения ключа в формате ДД.ММ.ГГГГ\n"
        "или нажмите 'Пропустить' для бессрочного ключа:",
        reply_markup=get_skip_keyboard(),
    )
    await call.answer()


@router.message(KeyCreateStates.waiting_usage_limit)
async def process_usage_limit(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Принять лимит использований ключа (числовой ввод)."""
    if admin_user is None:
        return
    from bot.utils.validators import validate_usage_limit
    ok, usage_limit = validate_usage_limit(message.text or "")
    if not ok:
        await message.answer(
            "Некорректное значение. Введите целое число (0 = безлимит):",
            reply_markup=get_cancel_keyboard(),
        )
        return
    await state.update_data(usage_limit=usage_limit)
    await state.set_state(KeyCreateStates.waiting_expires_at)
    await message.answer(
        "Введите дату истечения ключа в формате ДД.ММ.ГГГГ\n"
        "или нажмите 'Пропустить' для бессрочного ключа:",
        reply_markup=get_skip_keyboard(),
    )


async def _finalize_key_creation(
    state: FSMContext,
    session: AsyncSession,
    admin_user: User,
    expires_at,
    reply_func,
) -> None:
    """Общая логика финального создания ключа."""
    data = await state.get_data()
    key_type = KeyType.ONE_TIME if data.get("key_type") == "one_time" else KeyType.REUSABLE
    try:
        key = await create_key(
            session=session,
            key_type=key_type,
            admin_user=admin_user,
            custom_value=data.get("custom_value"),
            usage_limit=data.get("usage_limit"),
            expires_at=expires_at,
        )
        await state.clear()
        expires_str = expires_at.strftime("%d.%m.%Y") if expires_at else "бессрочно"
        limit_str = str(data.get("usage_limit")) if data.get("usage_limit") else "безлимит"
        await reply_func(
            f"Ключ успешно создан!\n\n"
            f"Значение: <code>{key.key_value}</code>\n"
            f"Тип: {'Одноразовый' if key_type == KeyType.ONE_TIME else 'Многоразовый'}\n"
            f"Лимит: {limit_str}\n"
            f"Действует до: {expires_str}",
            parse_mode="HTML",
            reply_markup=get_admin_main_menu(),
        )
    except (ValueError, RuntimeError) as e:
        await state.clear()
        await reply_func(f"Ошибка создания ключа: {e}", reply_markup=get_admin_main_menu())


@router.callback_query(F.data == "skip", KeyCreateStates.waiting_expires_at)
async def skip_expires_at(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Пропустить дату истечения (бессрочный ключ)."""
    if admin_user is None:
        await call.answer()
        return
    await call.answer()
    await _finalize_key_creation(state, session, admin_user, None, call.message.answer)


@router.message(KeyCreateStates.waiting_expires_at)
async def process_expires_at(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Принять дату истечения и создать ключ."""
    if admin_user is None:
        return
    from datetime import datetime, timezone
    expires_at = None
    text = (message.text or "").strip()
    if text:
        try:
            expires_at = datetime.strptime(text, "%d.%m.%Y").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            await message.answer(
                "Некорректный формат даты. Используйте ДД.ММ.ГГГГ (например, 31.12.2025)\n"
                "Или нажмите 'Пропустить':",
                reply_markup=get_skip_keyboard(),
            )
            return
    await _finalize_key_creation(state, session, admin_user, expires_at, message.answer)


@router.callback_query(PaginationCallback.filter(F.section == "keys"))
async def paginate_keys(
    call: CallbackQuery,
    callback_data: PaginationCallback,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer()
        return
    page = callback_data.page
    raw_keys = await get_keys_paginated(session, page=page)
    has_next = len(raw_keys) > PAGE_SIZE
    keys = raw_keys[:PAGE_SIZE]
    await call.message.edit_text(
        f"Ключи доступа (стр. {page + 1}):",
        reply_markup=get_key_list_keyboard(
            [(k.id, k.key_value, k.key_type, k.is_active) for k in keys],
            page=page,
            has_next=has_next,
        ),
    )
    await call.answer()


@router.callback_query(KeyActionCallback.filter(F.action == "view"))
async def view_key(
    call: CallbackQuery,
    callback_data: KeyActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    key = await get_key_by_id(session, callback_data.key_id)
    if key is None:
        await call.answer("Ключ не найден.", show_alert=True)
        return

    expires_str = key.expires_at.strftime("%d.%m.%Y") if key.expires_at else "бессрочно"
    limit_str = str(key.usage_limit) if key.usage_limit else "безлимит"
    status_str = "Активен" if key.is_active else "Неактивен"

    text = (
        f"Ключ: <code>{key.key_value}</code>\n"
        f"Тип: {'Одноразовый' if key.key_type == KeyType.ONE_TIME else 'Многоразовый'}\n"
        f"Статус: {status_str}\n"
        f"Использований: {key.usage_count} / {limit_str}\n"
        f"Действует до: {expires_str}\n"
        f"Создан: {key.created_at.strftime('%d.%m.%Y %H:%M')}"
    )
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_key_actions_keyboard(key.id, key.is_active),
    )
    await call.answer()


@router.callback_query(KeyActionCallback.filter(F.action == "toggle"))
async def toggle_key(
    call: CallbackQuery,
    callback_data: KeyActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    key = await get_key_by_id(session, callback_data.key_id)
    if key is None:
        await call.answer("Ключ не найден.", show_alert=True)
        return

    if key.is_active:
        await deactivate_key(session, key)
        await call.answer("Ключ деактивирован.")
    else:
        await activate_key(session, key)
        await call.answer("Ключ активирован.")

    await call.message.edit_reply_markup(
        reply_markup=get_key_actions_keyboard(key.id, key.is_active)
    )


@router.callback_query(KeyActionCallback.filter(F.action == "delete"))
async def confirm_delete_key(
    call: CallbackQuery,
    callback_data: KeyActionCallback,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    await call.message.edit_text(
        "Вы уверены, что хотите удалить этот ключ?\n"
        "Это действие необратимо.",
        reply_markup=get_key_confirm_delete_keyboard(callback_data.key_id),
    )
    await call.answer()


@router.callback_query(KeyActionCallback.filter(F.action == "delete_confirmed"))
async def execute_delete_key(
    call: CallbackQuery,
    callback_data: KeyActionCallback,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    key = await get_key_by_id(session, callback_data.key_id)
    if key is None:
        await call.answer("Ключ не найден.", show_alert=True)
        return

    key_value = key.key_value
    await delete_key(session, key)
    await call.message.edit_text(f"Ключ {key_value} удалён.")
    await call.answer("Ключ удалён.")


@router.callback_query(KeyActionCallback.filter(F.action == "back"))
async def back_to_keys(
    call: CallbackQuery,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer()
        return
    raw_keys = await get_keys_paginated(session, page=0)
    has_next = len(raw_keys) > PAGE_SIZE
    keys = raw_keys[:PAGE_SIZE]
    await call.message.edit_text(
        "Ключи доступа:",
        reply_markup=get_key_list_keyboard(
            [(k.id, k.key_value, k.key_type, k.is_active) for k in keys],
            page=0,
            has_next=has_next,
        ) if keys else None,
    )
    if not keys:
        await call.message.edit_text("Ключей нет. Создайте новый через /newkey")
    await call.answer()


# ---------------------------------------------------------------------------
# Раздел: Рассылка
# ---------------------------------------------------------------------------


@router.message(F.text == "Рассылка")
async def start_broadcast(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Начало FSM создания рассылки."""
    if admin_user is None:
        return
    await state.set_state(BroadcastStates.waiting_type)
    await message.answer(
        "Создание рассылки.\n\nВыберите тип контента:",
        reply_markup=get_broadcast_type_keyboard(),
    )


@router.callback_query(BroadcastActionCallback.filter(F.action == "type_text"))
async def broadcast_type_text(
    call: CallbackQuery,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    current_state = await state.get_state()
    if current_state != BroadcastStates.waiting_type:
        await call.answer()
        return
    await state.update_data(broadcast_type=BroadcastType.TEXT.value)
    await state.set_state(BroadcastStates.waiting_text)
    await call.message.edit_text("Введите текст рассылки:")
    await call.answer()


@router.callback_query(BroadcastActionCallback.filter(F.action == "type_photo"))
async def broadcast_type_photo(
    call: CallbackQuery,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    current_state = await state.get_state()
    if current_state != BroadcastStates.waiting_type:
        await call.answer()
        return
    await state.update_data(broadcast_type=BroadcastType.PHOTO.value)
    await state.set_state(BroadcastStates.waiting_photo)
    await call.message.edit_text("Отправьте фото для рассылки:")
    await call.answer()


@router.callback_query(BroadcastActionCallback.filter(F.action == "type_photo_caption"))
async def broadcast_type_photo_caption(
    call: CallbackQuery,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    current_state = await state.get_state()
    if current_state != BroadcastStates.waiting_type:
        await call.answer()
        return
    await state.update_data(broadcast_type=BroadcastType.PHOTO_CAPTION.value)
    await state.set_state(BroadcastStates.waiting_photo)
    await call.message.edit_text("Отправьте фото для рассылки:")
    await call.answer()


@router.message(BroadcastStates.waiting_text)
async def process_broadcast_text(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        return
    ok, result = validate_broadcast_text(message.text or "")
    if not ok:
        await message.answer(f"{result}\n\nВведите текст ещё раз:")
        return
    await state.update_data(text=result)
    await state.set_state(BroadcastStates.waiting_pending_option)
    await message.answer(
        f"Текст принят ({len(result)} симв.)\n\n"
        "Отправить уведомление пользователям, ожидающим одобрения?",
        reply_markup=get_pending_broadcast_keyboard(),
    )


@router.message(BroadcastStates.waiting_photo, F.photo)
async def process_broadcast_photo(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        return
    # Берём наибольшее фото
    photo: PhotoSize = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)

    data = await state.get_data()
    if data.get("broadcast_type") == BroadcastType.PHOTO_CAPTION.value:
        await state.set_state(BroadcastStates.waiting_caption)
        await message.answer("Фото принято. Введите подпись к фото:")
    else:
        await state.set_state(BroadcastStates.waiting_pending_option)
        await message.answer(
            "Фото принято.\n\n"
            "Отправить уведомление пользователям, ожидающим одобрения?",
            reply_markup=get_pending_broadcast_keyboard(),
        )


@router.message(BroadcastStates.waiting_photo)
async def process_broadcast_no_photo(message: Message) -> None:
    """Если вместо фото пришло что-то другое."""
    await message.answer("Пожалуйста, отправьте именно фото (не файл, не ссылку).")


@router.message(BroadcastStates.waiting_caption)
async def process_broadcast_caption(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        return
    ok, result = validate_broadcast_text(message.text or "")
    if not ok:
        await message.answer(f"{result}\n\nВведите подпись ещё раз:")
        return
    await state.update_data(text=result)
    await state.set_state(BroadcastStates.waiting_pending_option)
    await message.answer(
        "Подпись принята.\n\n"
        "Отправить уведомление пользователям, ожидающим одобрения?",
        reply_markup=get_pending_broadcast_keyboard(),
    )


@router.callback_query(PendingBroadcastCallback.filter())
async def process_pending_option(
    call: CallbackQuery,
    callback_data: PendingBroadcastCallback,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    current_state = await state.get_state()
    if current_state != BroadcastStates.waiting_pending_option:
        await call.answer()
        return

    await state.update_data(send_to_pending_masked=callback_data.send_masked)
    data = await state.get_data()

    # Сформировать превью
    btype = data.get("broadcast_type", "text")
    text_preview = (data.get("text") or "")[:200]
    has_photo = bool(data.get("photo_file_id"))
    pending_str = "Да (маскированно)" if callback_data.send_masked else "Нет"

    preview = (
        f"Проверьте рассылку:\n\n"
        f"Тип: {btype}\n"
        f"Фото: {'да' if has_photo else 'нет'}\n"
        f"Текст: {text_preview or '—'}\n"
        f"Pending-уведомление: {pending_str}\n\n"
        "Отправить?"
    )
    await state.set_state(BroadcastStates.confirm)
    await call.message.edit_text(preview, reply_markup=get_broadcast_confirm_keyboard())
    await call.answer()


@router.callback_query(BroadcastActionCallback.filter(F.action == "confirm"))
async def execute_broadcast(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    admin_user: Optional[User],
    bot: Bot,
) -> None:
    if admin_user is None:
        await call.answer("Нет прав.", show_alert=True)
        return
    current_state = await state.get_state()
    if current_state != BroadcastStates.confirm:
        await call.answer()
        return

    data = await state.get_data()
    await state.clear()

    await call.message.edit_text("Рассылка запущена, пожалуйста подождите...")
    await call.answer()

    broadcast = await create_broadcast(
        session=session,
        admin_id=admin_user.id,
        broadcast_type=BroadcastType(data.get("broadcast_type", BroadcastType.TEXT.value)),
        text=data.get("text"),
        photo_file_id=data.get("photo_file_id"),
        send_to_pending_masked=data.get("send_to_pending_masked", False),
    )
    # commit промежуточный чтобы broadcast.id был доступен при логировании
    await session.commit()

    stats = await send_broadcast(bot, session, broadcast)

    await call.message.answer(
        f"Рассылка завершена!\n\n"
        f"Успешно: {stats['success']}\n"
        f"Ошибок: {stats['failed']}\n"
        f"Пропущено: {stats['skipped']}",
        reply_markup=get_admin_main_menu(),
    )


@router.callback_query(BroadcastActionCallback.filter(F.action == "cancel"))
async def cancel_broadcast(
    call: CallbackQuery,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        await call.answer()
        return
    await state.clear()
    await call.message.edit_text("Рассылка отменена.")
    await call.answer("Отменено.")


# ---------------------------------------------------------------------------
# Раздел: Статистика
# ---------------------------------------------------------------------------


@router.message(F.text == "Статистика")
async def show_statistics(
    message: Message,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    """Показать общую статистику бота."""
    if admin_user is None:
        return

    from bot.services.key_service import get_all_keys
    counts = await get_users_count_by_status(session)
    keys = await get_all_keys(session)

    active_keys = sum(1 for k in keys if k.is_active)

    text = (
        "Статистика бота:\n\n"
        f"Пользователей всего: {sum(counts.values())}\n"
        f"  Одобрено: {counts.get('approved', 0)}\n"
        f"  Ожидают: {counts.get('pending', 0)}\n"
        f"  Отклонено: {counts.get('rejected', 0)}\n"
        f"  Заблокировано: {counts.get('banned', 0)}\n\n"
        f"Ключей всего: {len(keys)}\n"
        f"  Активных: {active_keys}\n"
        f"  Неактивных: {len(keys) - active_keys}"
    )
    await message.answer(text)


# ---------------------------------------------------------------------------
# Поиск пользователей
# ---------------------------------------------------------------------------


@router.message(Command("finduser"))
async def cmd_find_user(
    message: Message,
    state: FSMContext,
    admin_user: Optional[User],
) -> None:
    """Запустить поиск пользователя."""
    if admin_user is None:
        await message.answer("У вас нет прав администратора.")
        return
    await state.set_state(UserSearchStates.waiting_query)
    await message.answer(
        "Введите username (с @ или без), имя или Telegram ID:",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(UserSearchStates.waiting_query)
async def process_user_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    admin_user: Optional[User],
) -> None:
    if admin_user is None:
        return
    query = message.text or ""
    users = await search_users(session, query)
    await state.clear()

    if not users:
        await message.answer("Пользователи не найдены.", reply_markup=get_admin_main_menu())
        return

    items = [(u.id, u.display_name) for u in users]
    await message.answer(
        f"Найдено пользователей: {len(items)}",
        reply_markup=get_users_list_keyboard(items, page=0, has_next=False),
    )


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


async def _notify_user(bot: Bot, telegram_id: int, text: str) -> None:
    """Безопасно отправить уведомление пользователю."""
    try:
        await bot.send_message(chat_id=telegram_id, text=text)
    except Exception as e:
        logger.error(
            "Не удалось отправить уведомление пользователю tg_id=%s: %s",
            telegram_id, e,
        )
