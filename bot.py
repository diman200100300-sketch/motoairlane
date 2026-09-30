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

# Постоянная нижняя клавиатура
def get_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Генератор идей")],
            [KeyboardButton(text="⭐ Мой профиль / Лимиты")],
            [KeyboardButton(text="💎 Купить PRO — 19 zł/мес")]
        ],
        resize_keyboard=True
    )

# Инлайн меню внутри сообщений
def get_inline_menu(is_pro: bool):
    keyboard = [
        [InlineKeyboardButton(text="🎥 Скачать видео/аудио (TikTok, Inst, YT)", callback_data="menu_video")],
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
    
    text = (
        f"Привет! Я твой бот для скачивания медиа и генерации идей.\n\n"
        f"{status_text}\n\n"
        f"Выбери нужный раздел ниже:"
    )
    await message.answer(text, reply_markup=get_reply_menu())
    await message.answer("Главное меню управления:", reply_markup=get_inline_menu(is_pro))

# Обработка текстовых кнопок снизу
@dp.message(F.text == "💡 Генератор идей")
async def btn_ai_ideas(message: types.Message):
    await show_ai_generator(message)

@dp.message(F.text == "⭐ Мой профиль / Лимиты")
async def btn_profile(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status = "PRO (Безлимит)" if is_pro else "Бесплатный"
    await message.answer(f"👤 Твой профиль:\nID: `{user_id}`\nСтатус: **{status}**", parse_mode="Markdown")

@dp.message(F.text.startswith("💎 Купить PRO"))
async def btn_buy(message: types.Message):
    await send_buy_info(message)

async def send_buy_info(message_or_callback):
    text = (
        f"💎 **Получение PRO подписки**\n\n"
        f"Цена: **{PRICE}**\n"
        f"Оплата через **BLIK** на номер:\n`{BLIK_NUMBER}`\n\n"
        f"После перевода нажмите кнопку ниже или отправьте скриншот админу."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Я оплатил", callback_data="paid_confirm")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
    ])
    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data == "buy_pro")
async def process_buy_pro_callback(callback: types.CallbackQuery):
    await send_buy_info(callback)

@dp.callback_query(F.data == "paid_confirm")
async def process_paid_confirm(callback: types.CallbackQuery):
    user = callback.from_user
    user_link = f"@{user.username}" if user.username else f"ID: {user.id}"
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 **Новая заявка на PRO!**\nПользователь: {user_link} (ID: `{user.id}`)\n"
                f"Активируйте PRO командой:\n`/givepro {user.id}`",
                parse_mode="Markdown"
            )
        except:
            pass
    await callback.answer("Заявка отправлена админу!", show_alert=True)

@dp.callback_query(F.data == "back_home")
async def process_back_home(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    await callback.message.edit_text("Главное меню:", reply_markup=get_inline_menu(is_pro))
    await callback.answer()

@dp.message(Command("givepro"))
async def cmd_give_pro(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Пример: `/givepro 123456789`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        if target_id not in pro_users:
            pro_users.append(target_id)
            save_pro_users(pro_users)
        await message.answer(f"✅ Пользователю `{target_id}` активирован PRO!")
        await bot.send_message(target_id, "🎉 Ваша оплата подтверждена! PRO успешно активирован.")
    except:
        await message.answer("Ошибка ID.")

# --- ВИДЕО ИНСТРУМЕНТЫ ---
@dp.callback_query(F.data.in_({"menu_video", "menu_video_tools"}))
async def menu_video(callback: types.CallbackQuery):
    text = (
        "🎥 **Загрузка видео и аудио**\n\n"
        "Отправь мне ссылку на видео из **TikTok, YouTube или Instagram**, и я скачаю его для тебя без водяного знака!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text.startswith("http"))
async def download_media(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("⏳ Скачиваю медиа без водяного знака...")
    
    output_template = f"downloads_{message.from_user.id}.%(ext)s"
    ydl_opts = {
        'outtmpl': output_template,
        'format': 'best',
        'noplaylist': True,
    }
    
    try:
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
        
        file_path = await asyncio.to_thread(download)
        
        if os.path.exists(file_path):
            await message.answer_video(FSInputFile(file_path), caption="✅ Вот твое видео без водяного знака!")
            os.remove(file_path)
        else:
            await message.answer("❌ Не удалось найти файл по этой ссылке.")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text("❌ Ошибка загрузки: проверь ссылку или попробуй другую.")

# --- АУДИО ИНСТРУМЕНТЫ ---
@dp.callback_query(F.data.in_({"menu_audio", "menu_audio_tools"}))
async def menu_audio(callback: types.CallbackQuery):
    text = (
        "🎙 **Аудио инструменты**\n\n"
        "Здесь ты можешь отправить голосовое сообщение, и я помогу с его обработкой и переводом в текст."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.voice)
async def voice_processing(message: types.Message):
    await message.answer("🎙 Голосовое сообщение получено! (Функция распознавания текста активно готовится).")

# --- ИИ ГЕНЕРАТОР ИДЕЙ ---
async def show_ai_generator(message_or_callback):
    user_id = message_or_callback.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    if not is_pro:
        text = "⭐ **ИИ Генератор идей** доступен только для владельцев PRO подписки! Приобретите PRO для безлимитного доступа."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить PRO (19 zł)", callback_data="buy_pro")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
        ])
    else:
        text = (
            "🤖 **ИИ Генератор идей для TikTok**\n\n"
            "🔥 *Тренд-идея:* Снять атмосферное видео ночного автопробега или деталей салона под кастомный бас-трек с эффектом замедления (slowmo).\n\n"
            "Нажми кнопку ниже, чтобы сгенерировать следующую идею!"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сгенерировать еще", callback_data="menu_ai")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
        ])

    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data.in_({"menu_ai", "menu_ai_generator"}))
async def menu_ai_callback(callback: types.CallbackQuery):
    await show_ai_generator(callback)

async def main():
    print("Бот обновлен и запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
