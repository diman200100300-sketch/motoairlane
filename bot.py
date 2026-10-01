import asyncio
import logging
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import yt_dlp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton
)

# --- МІНІ-ВЕБСЕРВЕР ДЛЯ RENDER ---
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

TOKEN = "8949626852:AAFkv7WtvaCe5ueAZEU2oC9wGgaWorqkVMs"  # Вставте ваш токен сюди
ADMIN_ID = 738520454

bot = Bot(token=TOKEN)
dp = Dispatcher()

PRO_FILE = "pro_users.json"
ai_waiting_users = set()

def load_pro_users():
    if os.path.exists(PRO_FILE):
        try:
            with open(PRO_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except:
            return []
    return []

def save_pro_users(users):
    try:
        with open(PRO_FILE, "w") as f:
            json.dump(users, f)
    except Exception as e:
        logging.error(f"Помилка збереження PRO користувачів: {e}")

pro_users = load_pro_users()

BLIK_NUMBER = "+48 733 985 396"
PRICE = "19 zł/місяць"

def get_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Генератор ідей")],
            [KeyboardButton(text="⭐ Мій профіль")],
            [KeyboardButton(text="💎 Купити PRO — 19 zł/міс")]
        ],
        resize_keyboard=True
    )

def get_inline_menu(is_pro: bool):
    keyboard = [
        [InlineKeyboardButton(text="🎥 Завантажити відео (TikTok)", callback_data="menu_video")],
        [InlineKeyboardButton(text="🎙 Аудіо інструменти", callback_data="menu_audio")],
        [InlineKeyboardButton(text="🤖 ШІ Генератор ідей", callback_data="menu_ai")],
    ]
    if not is_pro:
        keyboard.append([InlineKeyboardButton(text="⭐ Купити PRO (19 zł)", callback_data="buy_pro")])
    else:
        keyboard.append([InlineKeyboardButton(text="✅ PRO Активно", callback_data="pro_info")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_main_menu(message: types.Message, text_prefix=""):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status_text = "⭐ Статус: **PRO (Безліміт)**" if is_pro else "⭐ Статус: **Безкоштовний**"
    
    text = f"{text_prefix}\n\n{status_text}\n\nОберіть розділ нижче:" if text_prefix else f"{status_text}\n\nОберіть розділ нижче:"
    await message.answer(text, reply_markup=get_reply_menu(), parse_mode="Markdown")
    await message.answer("Меню керування:", reply_markup=get_inline_menu(is_pro))

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    ai_waiting_users.discard(message.from_user.id)
    await send_main_menu(message, "Привіт! Я твій помічник для завантаження медіа та генерації ідей.")

@dp.message(F.text == "💡 Генератор ідей")
async def btn_ai(message: types.Message):
    await show_ai(message)

@dp.message(F.text == "⭐ Мій профіль")
async def btn_prof(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status = "PRO (Безліміт)" if is_pro else "Безкоштовний"
    await message.answer(f"👤 Ваш ID: `{user_id}`\nСтатус: **{status}**", parse_mode="Markdown")
    await send_main_menu(message)

@dp.message(F.text.startswith("💎 Купити PRO"))
async def btn_buy_text(message: types.Message):
    await send_buy(message)

async def send_buy(target):
    text = f"💎 **Отримання PRO**\nЦіна: **{PRICE}**\nОплата через **BLIK** на номер:\n`{BLIK_NUMBER}`\n\nПісля переказу натисніть кнопку нижче:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Я сплатив", callback_data="paid_confirm")],
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
            await bot.send_message(ADMIN_ID, f"🔔 Заявка на PRO!\nКористувач: {user_link} (`{user.id}`)\nАктивуйте командою:\n`/givepro {user.id}`", parse_mode="Markdown")
        except:
            pass
    await callback.answer("Заявку надіслано адміністратору!", show_alert=True)

@dp.callback_query(F.data == "back_home")
async def cb_home(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    ai_waiting_users.discard(user_id)
    await callback.message.edit_text("Головне меню:", reply_markup=get_inline_menu(is_pro))
    await callback.answer()

@dp.callback_query(F.data == "pro_info")
async def cb_pro_info(callback: types.CallbackQuery):
    await callback.answer("У вас вже активовано PRO-статус!", show_alert=True)

@dp.message(Command("givepro"))
async def cmd_give(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Приклад: `/givepro ID`", parse_mode="Markdown")
        return
    try:
        tid = int(args[1])
        if tid not in pro_users:
            pro_users.append(tid)
            save_pro_users(pro_users)
        await message.answer(f"✅ Користувачу `{tid}` успішно активовано та збережено PRO!")
        await bot.send_message(tid, "🎉 Вашу оплату підтверджено! PRO активовано.")
    except:
        await message.answer("Помилка в ID.")

@dp.callback_query(F.data == "menu_video")
async def cb_vid(callback: types.CallbackQuery):
    text = "🎥 **Завантаження відео**\n\nНадішліть мені посилання на відео з **TikTok**, і я завантажу його без водяного знака!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

async def get_tiktok_direct_url(video_url: str) -> str:
    def extract():
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}}
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url')
            except Exception as e:
                logging.error(f"yt-dlp extraction error: {e}")
                return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, extract)

@dp.message(F.text.startswith("http"))
async def down_media(message: types.Message):
    raw_url = message.text.strip()
    status = await message.answer("⏳ Отримую відео без водяного знака...")
    
    video_link = await get_tiktok_direct_url(raw_url)
    
    if not video_link:
        await status.edit_text("❌ Не вдалося завантажити відео. Спробуйте інше посилання.")
        await send_main_menu(message)
        return

    try:
        await message.answer_video(video_link, caption="✅ Ось ваше відео без водяного знака!")
        await status.delete()
        await send_main_menu(message, "Готово! Що робимо далі?")
    except Exception as e:
        logging.error(f"Send video error: {e}")
        await status.edit_text("❌ Помилка при надсиланні відео.")
        await send_main_menu(message)

@dp.callback_query(F.data == "menu_audio")
async def cb_aud(callback: types.CallbackQuery):
    text = (
        "🎙 **Аудіо інструменти**\n\n"
        "Надішліть голосове повідомлення або аудіо.\n\n"
        "⏱ **Ліміти тривалості:**\n"
        "• Безкоштовний: до **2 хвилин**\n"
        "• PRO: до **12 хвилин**"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.voice | F.audio)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    max_duration = 720 if is_pro else 120
    duration = message.voice.duration if message.voice else (message.audio.duration or 0)
    
    if duration > max_duration:
        limit_text = "12 хвилин" if is_pro else "2 хвилини"
        await message.answer(f"❌ Файл занадто довгий! Максимальна тривалість для вашого статусу — {limit_text}.")
        await send_main_menu(message)
        return

    await message.answer("🎙 Голосове повідомлення успішно отримано та перевірено на ліміт!")
    await send_main_menu(message, "Що робимо далі?")

@dp.callback_query(F.data == "menu_ai")
async def cb_ai_menu(callback: types.CallbackQuery):
    await show_ai(callback)

async def show_ai(target):
    user_id = target.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    if not is_pro:
        text = "⭐ **Генератор ідей** доступний тільки для PRO-підписників.\n\nПридбайте підписку, щоб отримати безлімітний доступ!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купити PRO (19 zł)", callback_data="buy_pro")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
        ])
        if isinstance(target, types.CallbackQuery):
            await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            await target.answer()
        else:
            await target.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        ai_waiting_users.add(user_id)
        text = "💡 **Універсальний ШІ Генератор ідей**\n\nНапишіть **абсолютно будь-яке слово чи фразу** (наприклад: *поїзд*, *БМВ*, *ніч*, *кава* тощо), і я згенерую унікальні ідеї!"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
        if isinstance(target, types.CallbackQuery):
            await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            await target.answer()
        else:
            await target.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.message(F.text)
async def handle_text_messages(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id in ai_waiting_users:
        is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
        if not is_pro:
            ai_waiting_users.discard(user_id)
            await message.answer("⭐ Ця функція доступна лише для PRO користувачів.")
            return
            
        wait_msg = await message.answer(f"🧠 ШІ аналізує слово «{text}» та генерує концепції...")
        await asyncio.sleep(1.2)
        
        response_text = (
            f"🎯 **Концепції контенту для запиту:** _{text}_\n\n"
            f"1️⃣ **POV-формат (Ефект присутності)**\n"
            f"   • *Ідея:* Покажи ситуацію від першої особи, пов'язану з темою «{text}».\n"
            f"   • *Хук (початок):* «Ніколи не робіть цього з {text}...» або «Коли вперше стикнувся з цим».\n\n"
            f"2️⃣ **Естетичне / Атмосферне відео (Slow-mo / Vibe)**\n"
            f"   • *Ідея:* Змонтуй швидкі, плавні кадри на тему «{text}» під трендовий трек.\n\n"
            f"3️⃣ **Цікавий факт або лайфхак**\n"
            f"   • *Ідея:* Розкрий неочевидну річ або секрет про «{text}».\n\n"
            f"🔥 *Хештеги:* `#тренди #{text.replace(' ', '')} #reels #tiktok`"
        )
        
        await wait_msg.edit_text(response_text, parse_mode="Markdown")
        
        ai_waiting_users.discard(user_id)
        await send_main_menu(message, "Бажаєте згенерувати ще ідеї чи завантажити відео?")
        return

    await message.answer("Скористайтеся меню нижче або натисніть /start для вибору розділу.")
    await send_main_menu(message)

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот запущено!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
