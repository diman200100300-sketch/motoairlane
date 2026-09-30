import asyncio
import logging
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    FSInputFile
)
import yt_dlp

# --- МИНИ-ВЕБСЕРВЕР ДЛЯ RENDER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()
# -----------------------------------

TOKEN = "8949626852:AAFpFd6EyoNA56aP6EnjPWOB54Kpsht_5CE"
ADMIN_ID = 738520454

bot = Bot(token=TOKEN)
dp = Dispatcher()

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
BLIK_NUMBER = "+48 733 985 396"
PRICE = "19 zł/месяц"

def get_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Генератор идей")],
            [KeyboardButton(text="⭐ Мой профиль")],
            [KeyboardButton(text="💎 Купить PRO — 19 zł/мес")]
        ],
        resize_keyboard=True
    )

def get_inline_menu(is_pro: bool):
    keyboard = [
        [InlineKeyboardButton(text="🎥 Скачать видео (TikTok, Inst, YT)", callback_data="menu_video")],
        [InlineKeyboardButton(text="🎙 Аудио инструменты", callback_data="menu_audio")],
        [InlineKeyboardButton(text="🤖 ИИ Генератор идей", callback_data="menu_ai")],
    ]
    if not is_pro:
        keyboard.append([InlineKeyboardButton(text="⭐ Купить PRO (19 zł)", callback_data="buy_pro")])
    else:
        keyboard.append([InlineKeyboardButton(text="✅ PRO Активно", callback_data="pro_info")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status_text = "⭐ Статус: **PRO (Безлимит)**" if is_pro else "⭐ Статус: **Бесплатный**"
    
    text = f"Привет! Я бот для скачивания медиа и идей.\n\n{status_text}\n\nВыберите раздел:"
    await message.answer(text, reply_markup=get_reply_menu(), parse_mode="Markdown")
    await message.answer("Меню управления:", reply_markup=get_inline_menu(is_pro))

@dp.message(F.text == "💡 Генератор идей")
async def btn_ai(message: types.Message):
    await show_ai(message)

@dp.message(F.text == "⭐ Мой профиль")
async def btn_prof(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status = "PRO (Безлимит)" if is_pro else "Бесплатный"
    await message.answer(f"👤 Ваш ID: `{user_id}`\nСтатус: **{status}**", parse_mode="Markdown")

@dp.message(F.text.startswith("💎 Купить PRO"))
async def btn_buy_text(message: types.Message):
    await send_buy(message)

async def send_buy(target):
    text = f"💎 **Получение PRO**\nЦена: **{PRICE}**\nОплата через **BLIK** на номер:\n`{BLIK_NUMBER}`\n\nПосле перевода нажмите кнопку ниже:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Я оплатил", callback_data="paid_confirm")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
    ])
    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "buy_pro")
async def cb_buy(callback: types.CallbackQuery):
    await send_buy(callback)

@dp.callback_query(F.data == "paid_confirm")
async def cb_paid(callback: types.CallbackQuery):
    user = callback.from_user
    user_link = f"@{user.username}" if user.username else f"ID: {user.id}"
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🔔 Заявка на PRO!\nПользователь: {user_link} (`{user.id}`)\nАктивируйте командой:\n`/givepro {user.id}`", parse_mode="Markdown")
        except:
            pass
    await callback.answer("Заявка отправлена администратору!", show_alert=True)

@dp.callback_query(F.data == "back_home")
async def cb_home(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    await callback.message.edit_text("Главное меню:", reply_markup=get_inline_menu(is_pro))
    await callback.answer()

@dp.message(Command("givepro"))
async def cmd_give(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Пример: `/givepro ID`", parse_mode="Markdown")
        return
    try:
        tid = int(args[1])
        if tid not in pro_users:
            pro_users.append(tid)
            save_pro_users(pro_users)
        await message.answer(f"✅ Пользователю `{tid}` активирован PRO!")
        await bot.send_message(tid, "🎉 Ваша оплата подтверждена! PRO активирован.")
    except:
        await message.answer("Ошибка в ID.")

@dp.callback_query(F.data == "menu_video")
async def cb_vid(callback: types.CallbackQuery):
    text = "🎥 **Скачивание видео**\n\nОтправьте мне ссылку на видео из TikTok, YouTube или Instagram, и я скачаю его без водяного знака!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text.startswith("http"))
async def down_media(message: types.Message):
    url = message.text.strip()
    status = await message.answer("⏳ Скачиваю видео...")
    tpl = f"downloads_{message.from_user.id}.%(ext)s"
    opts = {'outtmpl': tpl, 'format': 'best', 'noplaylist': True}
    try:
        def d():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
        f_path = await asyncio.to_thread(d)
        if os.path.exists(f_path):
            await message.answer_video(FSInputFile(f_path), caption="✅ Вот ваше видео!")
            os.remove(f_path)
        else:
            await message.answer("❌ Файл не найден.")
        await status.delete()
    except:
        await status.edit_text("❌ Ошибка загрузки. Проверьте правильность ссылки.")

@dp.callback_query(F.data == "menu_audio")
async def cb_aud(callback: types.CallbackQuery):
    text = "🎙 **Аудио инструменты**\n\nОтправьте голосовое сообщение или используйте ссылку на видео для извлечения аудио."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.voice)
async def voice_msg(message: types.Message):
    await message.answer("🎙 Голосовое сообщение получено!")

async def show_ai(target):
    user_id = target.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    if not is_pro:
        text = "⭐ Генератор идей доступен только для PRO-подписчиков!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить PRO (19 zł)", callback_data="buy_pro")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
        ])
    else:
        text = "🤖 **ИИ Генератор идей для TikTok**\n\n🔥 *Идея:* Топ-3 редких автомобиля или поезда города под ночной бас-трек со slowmo."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Еще идея", callback_data="menu_ai")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
        ])
    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "menu_ai")
async def cb_ai(callback: types.CallbackQuery):
    await show_ai(callback)

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
