from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

common_router = Router()


@common_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — начать\n"
        "/admin — админ-панель\n"
        "/key ВАШ_КЛЮЧ — активировать доступ на 24 часа\n"
        "/photo — получить фото из базы"
    )
