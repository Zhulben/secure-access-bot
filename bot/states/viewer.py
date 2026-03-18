"""FSM-состояния для просмотра рассылок по коду."""
from aiogram.fsm.state import State, StatesGroup


class ViewerStates(StatesGroup):
    waiting_code = State()  # Ожидание ввода кода просмотра
