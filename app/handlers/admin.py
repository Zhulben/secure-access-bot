from __future__ import annotations

import io

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from app.config import ADMIN_IDS
from app.db import (
    clear_all_data,
    create_access_key,
    get_latest_photo_from_db,
    get_user,
    grant_daily_access,
    invalidate_key_by_hash,
    list_all_users,
    list_approved_users,
    list_users_for_notification,
    list_pending_users,
    list_users_with_valid_access,
    replace_key,
    save_photo_to_db,
    set_user_status,
)
from app.keyboards import admin_main_kb, approve_user_kb, confirm_clear_kb
from app.states import BanState, BroadcastPhotoState, BroadcastState, CreateKeyState, InvalidateKeyState, ReplaceKeyState, UnbanState
from app.utils import fmt_dt, hash_key

admin_router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@admin_router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Панель администратора", reply_markup=admin_main_kb())


@admin_router.message(F.text == "📥 Ожидающие заявки")
async def pending_users(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    users = await list_pending_users()
    if not users:
        await message.answer("Нет ожидающих заявок.")
        return

    for user in users:
        text = (
            f"🕐 Заявка\n\n"
            f"ID: <code>{user['tg_id']}</code>\n"
            f"Username: @{user['username'] if user['username'] else '-'}\n"
            f"Имя: {user['first_name']}\n"
            f"Фамилия: {user['last_name']}\n"
            f"Дата: {fmt_dt(user['created_at'])}"
        )
        await message.answer(text, reply_markup=approve_user_kb(user["tg_id"]))


@admin_router.callback_query(F.data.startswith("approve:"))
async def approve_user(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    tg_id = int(callback.data.split(":")[1])
    user = await get_user(tg_id)
    await set_user_status(tg_id, "approved")
    await callback.message.edit_text(callback.message.text + "\n\n✅ Одобрен")
    await callback.answer("Пользователь подтверждён")
    try:
        if user and user.get("pending_key_id"):
            await grant_daily_access(tg_id, user["pending_key_id"])
            await callback.bot.send_message(tg_id, "✅ Ваша заявка подтверждена. Доступ открыт!")
        else:
            await callback.bot.send_message(tg_id, "✅ Ваша заявка подтверждена.")
    except Exception:
        pass


@admin_router.callback_query(F.data.startswith("ban:"))
async def ban_callback(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    tg_id = int(callback.data.split(":")[1])
    await set_user_status(tg_id, "banned")
    await callback.message.edit_text(callback.message.text + "\n\n⛔ Забанен")
    await callback.answer("Пользователь забанен")
    try:
        await callback.bot.send_message(tg_id, "⛔ Вам закрыт доступ к боту.")
    except Exception:
        pass


@admin_router.message(F.text == "👥 Пользователи")
async def all_users(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    users = await list_all_users()
    if not users:
        await message.answer("Пользователей нет.")
        return

    lines = []
    for user in users:
        lines.append(
            f"{user['first_name']} {user['last_name']} | {user['status']} | <code>{user['tg_id']}</code> | @{user['username'] if user['username'] else '-'}"
        )

    chunk = []
    for line in lines:
        chunk.append(line)
        if len(chunk) >= 20:
            await message.answer("\n".join(chunk))
            chunk = []
    if chunk:
        await message.answer("\n".join(chunk))


@admin_router.message(F.text == "🔐 Создать ключ")
async def ask_key(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введите новый ключ. Он будет действовать 7 дней.")
    await state.set_state(CreateKeyState.waiting_key_value)


@admin_router.message(CreateKeyState.waiting_key_value)
async def create_key_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_key = (message.text or "").strip()
    if len(raw_key) < 4:
        await message.answer("Ключ слишком короткий.")
        return

    try:
        await create_access_key(hash_key(raw_key), message.from_user.id, days=7)
        await message.answer(f"✅ Ключ создан на 7 дней:\n<code>{raw_key}</code>")
    except Exception as e:
        await message.answer(f"Ошибка создания ключа: {e}")
    await state.clear()


@admin_router.message(F.text == "🖼 Загрузить фото")
async def upload_photo_hint(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Отправьте фото следующим сообщением. Оно будет сохранено в PostgreSQL.")


@admin_router.message(F.text == "📢 Фото + текст всем")
async def ask_broadcast_photo(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Отправьте фото с подписью (или без). Будет разослано всем участникам с активным ключом.")
    await state.set_state(BroadcastPhotoState.waiting_photo)


@admin_router.message(BroadcastPhotoState.waiting_photo, F.photo)
async def broadcast_photo_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    users = await list_users_with_valid_access()
    caption = message.caption or ""
    photo_file_id = message.photo[-1].file_id
    ok_count = 0
    fail_count = 0

    for user in users:
        try:
            await message.bot.send_photo(user["tg_id"], photo_file_id, caption=caption or None)
            ok_count += 1
        except Exception:
            fail_count += 1

    for user in await list_users_for_notification():
        try:
            await message.bot.send_message(
                user["tg_id"],
                "🔔 Новое фото от администратора. Введите ключ, чтобы получить доступ к содержимому.",
            )
        except Exception:
            pass

    await message.answer(f"Фото + текст разосланы.\nУспешно: {ok_count}\nОшибок: {fail_count}")
    await state.clear()


@admin_router.message(BroadcastPhotoState.waiting_photo)
async def broadcast_photo_no_photo(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await message.answer("Пожалуйста, отправьте именно фото.")


@admin_router.message(F.photo)
async def save_photo_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    photo = message.photo[-1]
    tg_file = await message.bot.get_file(photo.file_id)
    buffer = io.BytesIO()
    await message.bot.download_file(tg_file.file_path, destination=buffer)
    photo_data = buffer.getvalue()
    filename = tg_file.file_path.split("/")[-1] if tg_file.file_path else f"{photo.file_id}.jpg"

    await save_photo_to_db(
        filename=filename,
        mime_type="image/jpeg",
        photo_data=photo_data,
        uploaded_by=message.from_user.id,
    )
    await message.answer("✅ Фото сохранено в базе данных.")


@admin_router.message(F.text == "📢 Рассылка")
async def ask_broadcast(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введите текст рассылки.")
    await state.set_state(BroadcastState.waiting_text)


@admin_router.message(BroadcastState.waiting_text)
async def broadcast_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    users = await list_users_with_valid_access()
    text = message.text or ""
    ok_count = 0
    fail_count = 0

    for user in users:
        try:
            await message.bot.send_message(user["tg_id"], f"📢 Сообщение от администратора:\n\n{text}")
            ok_count += 1
        except Exception:
            fail_count += 1

    for user in await list_users_for_notification():
        try:
            await message.bot.send_message(
                user["tg_id"],
                "🔔 Новое сообщение от администратора. Введите ключ, чтобы получить доступ к содержимому.",
            )
        except Exception:
            pass

    await message.answer(f"Готово.\nУспешно: {ok_count}\nОшибок: {fail_count}")
    await state.clear()


@admin_router.message(F.text == "📷 Последнее фото всем")
async def send_latest_photo_to_all(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    latest = await get_latest_photo_from_db()
    if not latest:
        await message.answer("Фото ещё не загружались.")
        return

    ok_count = 0
    fail_count = 0
    users = await list_users_with_valid_access()
    for user in users:
        try:
            file = BufferedInputFile(latest["photo_data"], filename=latest["filename"])
            await message.bot.send_photo(user["tg_id"], file, caption="📷 Новая фотография")
            ok_count += 1
        except Exception:
            fail_count += 1

    await message.answer(f"Фото отправлено.\nУспешно: {ok_count}\nОшибок: {fail_count}")


@admin_router.message(F.text == "❌ Обнулить ключ")
async def ask_invalidate_key(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введите ключ для обнуления. Доступ всех пользователей, использовавших этот ключ, будет отозван.")
    await state.set_state(InvalidateKeyState.waiting_key_value)


@admin_router.message(InvalidateKeyState.waiting_key_value)
async def invalidate_key_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_key = (message.text or "").strip()
    if len(raw_key) < 4:
        await message.answer("Ключ слишком короткий.")
        return

    found = await invalidate_key_by_hash(hash_key(raw_key))
    if found:
        await message.answer("✅ Ключ обнулён. Доступ отозван у всех, кто его использовал.")
    else:
        await message.answer("❌ Активный ключ не найден.")
    await state.clear()


@admin_router.message(F.text == "🔄 Заменить ключ")
async def ask_replace_key(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введите СТАРЫЙ ключ, который нужно заменить.")
    await state.set_state(ReplaceKeyState.waiting_old_key)


@admin_router.message(ReplaceKeyState.waiting_old_key)
async def replace_key_old_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_key = (message.text or "").strip()
    if len(raw_key) < 4:
        await message.answer("Ключ слишком короткий.")
        return

    await state.update_data(old_hash=hash_key(raw_key))
    await message.answer("Введите НОВЫЙ ключ.")
    await state.set_state(ReplaceKeyState.waiting_new_key)


@admin_router.message(ReplaceKeyState.waiting_new_key)
async def replace_key_new_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_new = (message.text or "").strip()
    if len(raw_new) < 4:
        await message.answer("Ключ слишком короткий.")
        return

    data = await state.get_data()
    success = await replace_key(data["old_hash"], hash_key(raw_new), message.from_user.id)
    if success:
        await message.answer(f"✅ Ключ заменён на 7 дней:\n<code>{raw_new}</code>")
    else:
        await message.answer("❌ Старый активный ключ не найден.")
    await state.clear()


@admin_router.message(F.text == "⛔ Забанить")
async def ask_ban(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введите Telegram ID пользователя для бана.")
    await state.set_state(BanState.waiting_user_id)


@admin_router.message(BanState.waiting_user_id)
async def ban_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if not (message.text and message.text.isdigit()):
        await message.answer("Введите корректный Telegram ID.")
        return
    tg_id = int(message.text)
    await set_user_status(tg_id, "banned")
    await message.answer(f"⛔ Пользователь {tg_id} забанен.")
    await state.clear()


@admin_router.message(F.text == "✅ Разбанить")
async def ask_unban(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введите Telegram ID пользователя для разбана.")
    await state.set_state(UnbanState.waiting_user_id)


@admin_router.message(UnbanState.waiting_user_id)
async def unban_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if not (message.text and message.text.isdigit()):
        await message.answer("Введите корректный Telegram ID.")
        return
    tg_id = int(message.text)
    await set_user_status(tg_id, "approved")
    await message.answer(f"✅ Пользователь {tg_id} разбанен.")
    await state.clear()


@admin_router.message(F.text == "🗑 Очистить базу")
async def ask_clear_db(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "⚠️ Вы уверены? Это удалит ВСЕХ пользователей, ключи, доступы и фотографии. Действие необратимо.",
        reply_markup=confirm_clear_kb(),
    )


@admin_router.callback_query(F.data == "clear_db:confirm")
async def confirm_clear_db(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await clear_all_data()
    await callback.message.edit_text("🗑 База данных полностью очищена.")
    await callback.answer()


@admin_router.callback_query(F.data == "clear_db:cancel")
async def cancel_clear_db(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("❌ Очистка отменена.")
    await callback.answer()
