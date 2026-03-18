from aiogram.fsm.state import State, StatesGroup


class RegisterState(StatesGroup):
    waiting_first_name = State()
    waiting_last_name = State()


class CreateKeyState(StatesGroup):
    waiting_key_value = State()


class BroadcastState(StatesGroup):
    waiting_text = State()


class BanState(StatesGroup):
    waiting_user_id = State()


class UnbanState(StatesGroup):
    waiting_user_id = State()


class BroadcastPhotoState(StatesGroup):
    waiting_photo = State()
