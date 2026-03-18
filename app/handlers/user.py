from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message
from aiogram.fsm.context import FSMContext

from app.config import ADMIN_IDS
from app.db import (
    find_active_key_by_hash,
    get_access_info,
    get_latest_photo_from_db,
    get_user,
    grant_daily_access,
    has_valid_access,
    upsert_user,
)
from app.keyboards import admin_main_kb, approve_user_kb, user_main_kb
from app.states import RegisterState
from app.utils import fmt_dt, hash_key

user_router = Router()


async def notify_admins(bot, tg_id: int, username: str | None, first_name: str, last_name: str) -> None:
    text = (
        f"🆕 Новая заявка\n\n"
        f"ID: <code>{tg_id}</code>\n"
        f"Username: @{username if username else '-'}\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=approve_user_kb(tg_id))
        except Exception:
            pass


@user_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    if message.from_user.id in ADMIN_IDS:
        await message.answer("Вы вошли как администратор.", reply_markup=admin_main_kb())
        return

    user = await get_user(message.from_user.id)
    if user:
        status = user["status"]
        if status == "pending":
            await message.answer("⏳ Ваша заявка уже отправлена. Ожидайте подтверждения.")
            return
        if status == "approved":
            if await has_valid_access(message.from_user.id):
                await message.answer("✅ Доступ активен.", reply_markup=user_main_kb())
            else:
                await message.answer("🔑 Введите ключ командой:\n/key ВАШ_КЛЮЧ", reply_markup=user_main_kb())
            return
        if status == "banned":
            await message.answer("⛔ Вам запрещён доступ к боту.")
            return

    await message.answer("Введите имя:")
    await state.set_state(RegisterState.waiting_first_name)


@user_router.message(RegisterState.waiting_first_name)
async def get_first_name(message: Message, state: FSMContext) -> None:
    first_name = (message.text or "").strip()
    if len(first_name) < 2:
        await message.answer("Имя слишком короткое. Введите ещё раз.")
        return
    await state.update_data(first_name=first_name)
    await message.answer("Введите фамилию:")
    await state.set_state(RegisterState.waiting_last_name)


@user_router.message(RegisterState.waiting_last_name)
async def get_last_name(message: Message, state: FSMContext) -> None:
    last_name = (message.text or "").strip()
    if len(last_name) < 2:
        await message.answer("Фамилия слишком короткая. Введите ещё раз.")
        return

    data = await state.get_data()
    first_name = data["first_name"]
    await upsert_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=first_name,
        last_name=last_name,
    )
    await notify_admins(message.bot, message.from_user.id, message.from_user.username, first_name, last_name)
    await message.answer("⏳ Заявка отправлена администратору.")
    await state.clear()


@user_router.message(Command("key"))
async def cmd_key(message: Message, command: CommandObject) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start")
        return
    if user["status"] != "approved":
        await message.answer("⏳ Вы ещё не подтверждены администратором.")
        return
    if not command.args:
        await message.answer("Пример:\n/key MY_SECRET_KEY")
        return

    key = await find_active_key_by_hash(hash_key(command.args.strip()))
    if not key:
        await message.answer("❌ Ключ неверный или истёк.")
        return

    await grant_daily_access(message.from_user.id, key["id"])
    await message.answer("✅ Доступ открыт на 24 часа.", reply_markup=user_main_kb())


@user_router.message(F.text == "🔑 Ввести ключ")
async def enter_key_hint(message: Message) -> None:
    await message.answer("Введите ключ командой:\n/key ВАШ_КЛЮЧ")


@user_router.message(F.text == "ℹ️ Мой статус")
async def my_status(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start")
        return

    access = await get_access_info(message.from_user.id)
    text = (
        f"Статус: {user['status']}\n"
        f"Имя: {user['first_name']}\n"
        f"Фамилия: {user['last_name']}\n"
    )
    if access:
        text += f"Доступ до: {fmt_dt(access['expires_at'])}"
    else:
        text += "Активного доступа нет"
    await message.answer(text)


@user_router.message(Command("photo"))
@user_router.message(F.text == "📷 Получить фото")
async def get_photo(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start")
        return
    if user["status"] != "approved":
        await message.answer("⏳ Вы ещё не подтверждены.")
        return
    if not await has_valid_access(message.from_user.id):
        await message.answer("🔒 Доступ истёк. Введите новый ключ.")
        return

    latest = await get_latest_photo_from_db()
    if not latest:
        await message.answer("Пока нет доступных фотографий.")
        return

    file = BufferedInputFile(latest["photo_data"], filename=latest["filename"])
    await message.answer_photo(file, caption="📷 Последняя фотография из базы данных")
