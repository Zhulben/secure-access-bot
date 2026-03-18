"""FSM-состояния процесса регистрации пользователя."""
from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Шаги регистрации нового пользователя."""
    waiting_first_name = State()   # Ожидание ввода имени
    waiting_last_name = State()    # Ожидание ввода фамилии
    waiting_key = State()          # Ожидание ввода ключа доступа
