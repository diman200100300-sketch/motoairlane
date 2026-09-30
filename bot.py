import asyncio
import logging
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
import yt_dlp

# --- МІНІ-ВЕБСЕРВЕР ДЛЯ RENDER (щоб не було Timed Out) ---
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
# -----------------------------------------------------------

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
PRICE = "19 PLN / місяць"

def get_main_menu(is_pro: bool):
    keyboard = [
        [InlineKeyboardButton(text="🎥 Скачати відео/аудіо (TikTok, Inst, YT)", callback_data="menu_video")],
        [InlineKeyboardButton(text="🎙 Голосове в текст", callback_data="menu_audio")],
        [InlineKeyboardButton(text="🤖 ШІ Генератор ідей для TikTok", callback_data="menu_ai")],
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
    
    status_text = "⭐ Статус: **PRO (Безліміт)**" if is_pro else "⭐ Статус: **Безкоштовний**"
    
    text = (
        f"Привіт! Я твій бот для скачування медіа та генерації ідей.\n\n"
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
        f"Після переказу натисніть кнопку нижче."
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
                f"Активуйте PRO командою:\n`/givepro {user.id}`",
                parse_mode="Markdown"
            )
        except:
            pass
    await callback.answer("Заявку надіслано адміну!", show_alert=True)

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
        await message.answer("Приклад: `/givepro 123456789`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        if target_id not in pro_users:
            pro_users.append(target_id)
            save_pro_users(pro_users)
        await message.answer(f"✅ Користувачу `{target_id}` активовано PRO!")
        await bot.send_message(target_id, "🎉 Вашу оплату підтверджено! PRO активковано.")
    except:
        await message.answer("Помилка ID.")

@dp.callback_query(F.data == "menu_video")
async def menu_video(callback: types.CallbackQuery):
    text = (
        "🎥 **Завантаження відео та аудіо**\n\n"
        "Надішли мені посилання на відео з **TikTok, YouTube або Instagram**, і я завантажу його для тебе без водяного знака!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text.startswith("http"))
async def download_media(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("⏳ Завантажую медіа з посилання...")
    
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
            await message.answer_video(FSInputFile(file_path), caption="✅ Ось твоє відео!")
            os.remove(file_path)
        else:
            await message.answer("❌ Не вдалося знайти файл за цим посиланням.")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text("❌ Помилка завантаження: перевір посилання.")

@dp.callback_query(F.data == "menu_audio")
async def menu_audio(callback: types.CallbackQuery):
    text = "🎙 **Голосове в текст**\n\nНадішли мені голосове повідомлення, і я допоможу з його обробкою!"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_ai")
async def menu_ai(callback: types.CallbackQuery):
    is_pro = (callback.from_user.id == ADMIN_ID) or (callback.from_user.id in pro_users)
    if not is_pro:
        await callback.answer("⭐ Ця функція доступна лише для PRO підписки!", show_alert=True)
        return
    
    text = (
        "🤖 **ШІ Генератор ідей для TikTok**\n\n"
        "🔥 *Ідея:* Зняти топ-добірку рідкісних машин або поїздів у місті під атмосферний трек зі slow-mo ефектом.\n\n"
        "Натисни кнопку нижче для оновлення ідеї!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Згенерувати ще", callback_data="menu_ai")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

async def main():
    print("Бот запущено і працює...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
