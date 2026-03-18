"""
Клавиатуры для администраторов.
Использует CallbackData для типобезопасных callback-данных.
"""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# ---------------------------------------------------------------------------
# CallbackData-фабрики
# ---------------------------------------------------------------------------


class UserActionCallback(CallbackData, prefix="usr"):
    """Действие с конкретным пользователем."""
    action: str   # approve | reject | ban | unban | view | back
    user_id: int


class KeyActionCallback(CallbackData, prefix="key"):
    """Действие с конкретным ключом."""
    action: str   # view | edit | delete | toggle | back
    key_id: int


class BroadcastActionCallback(CallbackData, prefix="bc"):
    """Действие в процессе создания рассылки."""
    action: str   # type_text | type_photo | type_photo_caption | confirm | cancel


class PaginationCallback(CallbackData, prefix="pg"):
    """Пагинация списков."""
    section: str  # users_pending | users_all | keys
    page: int


class KeyTypeCallback(CallbackData, prefix="ktype"):
    """Выбор типа ключа."""
    key_type: str  # reusable | one_time


class PendingBroadcastCallback(CallbackData, prefix="pbc"):
    """Опция рассылки pending-пользователям."""
    send_masked: bool


# ---------------------------------------------------------------------------
# Главное меню администратора
# ---------------------------------------------------------------------------


def get_admin_main_menu() -> ReplyKeyboardMarkup:
    """Reply-клавиатура главного меню администратора."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="Заявки")
    builder.button(text="Пользователи")
    builder.button(text="Ключи")
    builder.button(text="Рассылка")
    builder.button(text="Статистика")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


# ---------------------------------------------------------------------------
# Список ожидающих заявок
# ---------------------------------------------------------------------------


def get_pending_requests_keyboard(
    requests: list[tuple[int, str, int]]  # [(request_id, display_name, user_id), ...]
) -> InlineKeyboardMarkup:
    """Список заявок с кнопками для просмотра каждой."""
    builder = InlineKeyboardBuilder()
    for req_id, name, user_id in requests:
        builder.button(
            text=f"👤 {name}",
            callback_data=UserActionCallback(action="view", user_id=user_id),
        )
        builder.adjust(1)
    return builder.as_markup()


def get_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Кнопки одобрить / отклонить для конкретного пользователя."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Одобрить",
        callback_data=UserActionCallback(action="approve", user_id=user_id),
    )
    builder.button(
        text="Отклонить",
        callback_data=UserActionCallback(action="reject", user_id=user_id),
    )
    builder.button(
        text="Назад к заявкам",
        callback_data=UserActionCallback(action="back", user_id=0),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Управление пользователями
# ---------------------------------------------------------------------------


def get_user_actions_keyboard(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    """Действия с пользователем: бан / разбан."""
    builder = InlineKeyboardBuilder()
    if is_banned:
        builder.button(
            text="Разбанить",
            callback_data=UserActionCallback(action="unban", user_id=user_id),
        )
    else:
        builder.button(
            text="Заблокировать",
            callback_data=UserActionCallback(action="ban", user_id=user_id),
        )
    builder.button(
        text="Назад",
        callback_data=UserActionCallback(action="back", user_id=0),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_users_list_keyboard(
    users: list[tuple[int, str]],  # [(user_id, display_name), ...]
    page: int,
    has_next: bool,
    section: str = "users_all",
) -> InlineKeyboardMarkup:
    """Список пользователей с пагинацией."""
    builder = InlineKeyboardBuilder()
    for user_id, name in users:
        builder.button(
            text=f"👤 {name}",
            callback_data=UserActionCallback(action="view", user_id=user_id),
        )
    builder.adjust(1)

    # Пагинация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            ("Предыдущая", PaginationCallback(section=section, page=page - 1))
        )
    if has_next:
        nav_buttons.append(
            ("Следующая", PaginationCallback(section=section, page=page + 1))
        )
    for label, cb in nav_buttons:
        builder.button(text=label, callback_data=cb)
    if nav_buttons:
        builder.adjust(*([1] * len(users)), len(nav_buttons))

    return builder.as_markup()


# ---------------------------------------------------------------------------
# Управление ключами
# ---------------------------------------------------------------------------


def get_key_type_keyboard() -> InlineKeyboardMarkup:
    """Выбор типа ключа при создании."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Одноразовый",
        callback_data=KeyTypeCallback(key_type="one_time"),
    )
    builder.button(
        text="Многоразовый",
        callback_data=KeyTypeCallback(key_type="reusable"),
    )
    builder.adjust(2)
    return builder.as_markup()


def get_key_list_keyboard(
    keys: list[tuple[int, str, str, bool]],  # [(key_id, value, type, is_active), ...]
    page: int,
    has_next: bool,
) -> InlineKeyboardMarkup:
    """Список ключей с пагинацией."""
    builder = InlineKeyboardBuilder()
    for key_id, value, ktype, is_active in keys:
        status_icon = "✅" if is_active else "❌"
        type_label = "1x" if ktype == "one_time" else "∞"
        builder.button(
            text=f"{status_icon} [{type_label}] {value}",
            callback_data=KeyActionCallback(action="view", key_id=key_id),
        )
    builder.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(("Предыдущая", PaginationCallback(section="keys", page=page - 1)))
    if has_next:
        nav_buttons.append(("Следующая", PaginationCallback(section="keys", page=page + 1)))
    for label, cb in nav_buttons:
        builder.button(text=label, callback_data=cb)
    if nav_buttons:
        builder.adjust(*([1] * len(keys)), len(nav_buttons))

    return builder.as_markup()


def get_key_actions_keyboard(key_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """Действия с конкретным ключом."""
    builder = InlineKeyboardBuilder()
    toggle_label = "Деактивировать" if is_active else "Активировать"
    builder.button(
        text=toggle_label,
        callback_data=KeyActionCallback(action="toggle", key_id=key_id),
    )
    builder.button(
        text="Удалить",
        callback_data=KeyActionCallback(action="delete", key_id=key_id),
    )
    builder.button(
        text="Назад к списку",
        callback_data=KeyActionCallback(action="back", key_id=0),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_key_confirm_delete_keyboard(key_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления ключа."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, удалить",
        callback_data=KeyActionCallback(action="delete_confirmed", key_id=key_id),
    )
    builder.button(
        text="Отмена",
        callback_data=KeyActionCallback(action="back", key_id=0),
    )
    builder.adjust(2)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Рассылка
# ---------------------------------------------------------------------------


def get_broadcast_type_keyboard() -> InlineKeyboardMarkup:
    """Выбор типа рассылки."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Текст",
        callback_data=BroadcastActionCallback(action="type_text"),
    )
    builder.button(
        text="Фото",
        callback_data=BroadcastActionCallback(action="type_photo"),
    )
    builder.button(
        text="Фото + подпись",
        callback_data=BroadcastActionCallback(action="type_photo_caption"),
    )
    builder.button(
        text="Отмена",
        callback_data=BroadcastActionCallback(action="cancel"),
    )
    builder.adjust(3, 1)
    return builder.as_markup()


def get_pending_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Опция отправки masked-уведомления pending-пользователям."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, уведомить (маскированно)",
        callback_data=PendingBroadcastCallback(send_masked=True),
    )
    builder.button(
        text="Нет, только одобренным",
        callback_data=PendingBroadcastCallback(send_masked=False),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение отправки рассылки."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отправить",
        callback_data=BroadcastActionCallback(action="confirm"),
    )
    builder.button(
        text="Отмена",
        callback_data=BroadcastActionCallback(action="cancel"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Общие
# ---------------------------------------------------------------------------


def get_confirm_keyboard(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    """Универсальная клавиатура подтверждения с произвольными callback-данными."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data=confirm_cb)
    builder.button(text="Отмена", callback_data=cancel_cb)
    builder.adjust(2)
    return builder.as_markup()


def get_skip_keyboard() -> InlineKeyboardMarkup:
    """Кнопка 'Пропустить' для необязательных полей."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="skip")
    return builder.as_markup()


def get_custom_or_auto_key_keyboard() -> InlineKeyboardMarkup:
    """Выбор: сгенерировать ключ автоматически или ввести вручную."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Сгенерировать автоматически", callback_data="key_auto")
    builder.button(text="Ввести вручную", callback_data="key_manual")
    builder.adjust(1)
    return builder.as_markup()
