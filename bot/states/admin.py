"""FSM-состояния для различных административных действий."""
from aiogram.fsm.state import State, StatesGroup


class AdminConfirmStates(StatesGroup):
    """Подтверждение опасных действий администратора."""
    waiting_confirm = State()   # Ожидание подтверждения (да/нет)


class UserSearchStates(StatesGroup):
    """Поиск пользователя."""
    waiting_query = State()     # Ввод запроса (username или telegram_id)


class AdminManageStates(StatesGroup):
    """Добавление нового администратора."""
    waiting_telegram_id = State()   # Ввод Telegram ID нового администратора


class ViewerCodeStates(StatesGroup):
    """Установка кастомного кода просмотра."""
    waiting_custom_code = State()
