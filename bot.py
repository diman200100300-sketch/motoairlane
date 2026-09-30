import asyncio
import logging
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Твій токен бота від BotFather
TOKEN = "8949626852:AAFpFd6EyoNA56aP6EnjPWOB54Kpsht_5CE"

# Твій числовий Telegram ID (адмін)
ADMIN_ID = 738520454

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Файл для збереження PRO користувачів
PRO_FILE = "pro_users.json"

def load_pro_users():
    if os.path.exists(PRO_FILE):
        try:
            with open(PRO_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_pro_users(users):
    with open(PRO_FILE, "w") as f:
        json.dump(users, f)

pro_users = load_pro_users()

DAILY_LIMIT = 7
BLIK_NUMBER = "+48 733 985 396"
PRICE = "19 PLN / місяць"

def get_main_menu(is_pro: bool):
    keyboard = [
        [InlineKeyboardButton(text="🎥 Відео інструменти", callback_data="menu_video")],
        [InlineKeyboardButton(text="🎵 Аудіо інструменти", callback_data="menu_audio")],
        [InlineKeyboardButton(text="🤖 ШІ Генератор ідей", callback_data="menu_ai")],
    ]
    if not is_pro:
        keyboard.append([InlineKeyboardButton(text="⭐ Купити PRO (19 PLN)", callback_data="buy_pro")])
    else:
        keyboard.append([InlineKeyboardButton(text="✅ PRO Активно", callback_data="pro_info")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    status_text = "⭐ Статус: **PRO (Безліміт)**" if is_pro else f"⭐ Статус: **Безкоштовний** (Ліміт: {DAILY_LIMIT} запитів на день)"
    
    text = (
        f"Привіт! Я твій багатофункціональний бот для відео, аудіо та ШІ.\n\n"
        f"{status_text}\n\n"
        f"Вибери потрібний розділ нижче:"
    )
    await message.answer(text, reply_markup=get_main_menu(is_pro), parse_mode="Markdown")

@dp.callback_query(F.data == "buy_pro")
async def process_buy_pro(callback: types.CallbackQuery):
    text = (
        f"💎 **Отримання PRO підписки**\n\n"
        f"Ціна: **{PRICE}**\n"
        f"Оплата через **BLIK** на номер:\n`{BLIK_NUMBER}`\n\n"
        f"Після переказу натисніть кнопку нижче, щоб надіслати підтвердження."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Я оплатив", callback_data="paid_confirm")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "paid_confirm")
async def process_paid_confirm(callback: types.CallbackQuery):
    user = callback.from_user
    user_link = f"@{user.username}" if user.username else f"ID: {user.id}"
    
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 **Нова заявка на PRO!**\nКористувач: {user_link} (ID: `{user.id}`)\n"
                f"Зробив переказ на BLIK.\n"
                f"Активуйте йому PRO командою:\n`/givepro {user.id}`",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Помилка надсилання адміну: {e}")

    await callback.answer("Заявку надіслано! Адмін перевірить оплату та активує PRO.", show_alert=True)
    
@dp.callback_query(F.data == "back_home")
async def process_back_home(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    await callback.message.edit_text("Головне меню:", reply_markup=get_main_menu(is_pro))
    await callback.answer()

@dp.message(Command("givepro"))
async def cmd_give_pro(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Вкажіть ID користувача. Приклад: `/givepro 123456789`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        if target_id not in pro_users:
            pro_users.append(target_id)
            save_pro_users(pro_users)
        await message.answer(f"✅ Користувачу `{target_id}` успішно активовано PRO статус!", parse_mode="Markdown")
        
        try:
            await bot.send_message(target_id, "🎉 Вашу оплату підтверджено! Вам активовано **PRO статус** у боті.", parse_mode="Markdown")
        except:
            pass
    except ValueError:
        await message.answer("Неправильний формат ID.")

@dp.callback_query(F.data == "menu_video")
async def menu_video(callback: types.CallbackQuery):
    is_pro = (callback.from_user.id == ADMIN_ID) or (callback.from_user.id in pro_users)
    await callback.message.edit_text("🎥 Меню відео інструментів у розробці.", reply_markup=get_main_menu(is_pro))
    await callback.answer()

@dp.callback_query(F.data == "menu_audio")
async def menu_audio(callback: types.CallbackQuery):
    is_pro = (callback.from_user.id == ADMIN_ID) or (callback.from_user.id in pro_users)
    await callback.message.edit_text("🎵 Меню аудіо інструментів у розробці.", reply_markup=get_main_menu(is_pro))
    await callback.answer()

@dp.callback_query(F.data == "menu_ai")
async def menu_ai(callback: types.CallbackQuery):
    is_pro = (callback.from_user.id == ADMIN_ID) or (callback.from_user.id in pro_users)
    await callback.message.edit_text("🤖 ШІ Генератор ідей у розробці.", reply_markup=get_main_menu(is_pro))
    await callback.answer()

async def main():
    print("Бот запущено і працює...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
