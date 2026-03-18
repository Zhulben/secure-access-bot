"""FSM-состояния для создания и редактирования ключей доступа."""
from aiogram.fsm.state import State, StatesGroup


class KeyCreateStates(StatesGroup):
    """Шаги создания нового ключа доступа."""
    waiting_key_type = State()       # Выбор типа: одноразовый / многоразовый
    waiting_custom_value = State()   # Ввод кастомного значения (или авто-генерация)
    waiting_usage_limit = State()    # Ввод лимита использований (для многоразового)
    waiting_expires_at = State()     # Ввод срока действия (необязательно)
    confirm = State()                # Подтверждение создания


class KeyEditStates(StatesGroup):
    """Шаги редактирования существующего ключа."""
    waiting_field = State()          # Выбор поля для редактирования
    waiting_new_value = State()      # Ввод нового значения
    confirm = State()                # Подтверждение изменения
