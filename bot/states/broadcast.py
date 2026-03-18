"""FSM-состояния для создания рассылки."""
from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    """Шаги создания рассылки администратором."""
    waiting_type = State()            # Выбор типа рассылки
    waiting_text = State()            # Ввод текста
    waiting_photo = State()           # Загрузка фото
    waiting_caption = State()         # Ввод подписи к фото
    waiting_pending_option = State()  # Отправлять ли pending-пользователям
    confirm = State()                 # Финальное подтверждение и отправка
