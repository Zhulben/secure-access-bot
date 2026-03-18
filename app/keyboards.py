from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def user_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 Получить фото")],
            [KeyboardButton(text="🔑 Ввести ключ"), KeyboardButton(text="ℹ️ Мой статус")],
        ],
        resize_keyboard=True,
    )


def admin_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Ожидающие заявки"), KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="🔐 Создать ключ"), KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="🖼 Загрузить фото"), KeyboardButton(text="📷 Последнее фото всем")],
            [KeyboardButton(text="📢 Фото + текст всем")],
            [KeyboardButton(text="⛔ Забанить"), KeyboardButton(text="✅ Разбанить")],
        ],
        resize_keyboard=True,
    )


def approve_user_kb(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve:{tg_id}"),
                InlineKeyboardButton(text="⛔ Бан", callback_data=f"ban:{tg_id}"),
            ]
        ]
    )
