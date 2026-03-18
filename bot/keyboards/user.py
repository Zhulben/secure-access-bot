"""
Клавиатуры для обычных пользователей.
Пользовательский интерфейс минимален: бот ведёт диалог сообщениями.
"""
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def remove_keyboard() -> ReplyKeyboardRemove:
    """Убрать reply-клавиатуру."""
    return ReplyKeyboardRemove()


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка отмены текущего действия."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="Отмена")
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)



def get_registration_start_keyboard() -> InlineKeyboardMarkup:
    """Кнопка начала регистрации."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Начать регистрацию", callback_data="start_registration")
    return builder.as_markup()


def get_user_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Главное меню одобренного пользователя."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="👤 Мой профиль")
    builder.button(text="📌 Актуальное")
    builder.button(text="📨 Последние сообщения")
    builder.button(text="❓ Помощь")
    if is_admin:
        builder.button(text="⚙️ Панель администратора")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)
