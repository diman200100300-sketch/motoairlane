import asyncio
import logging
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import aiohttp
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
import whisper  # Бібліотека для розпізнавання мови (OpenAI Whisper)
import moviepy.editor as mp  # Для перевірки тривалості відео та витягування аудіо

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

TOKEN = "8949626852:AAHhmqs-5ltgOuA7tdGedrBRWvp5ntP2SXQ"
ADMIN_ID = 738520454

bot = Bot(token=TOKEN)
dp = Dispatcher()

PRO_FILE = "pro_users.json"
ai_waiting_users = set()

# Завантажуємо модель Whisper (базова модель швидко працює на серверах)
print("Завантаження моделі Whisper...")
whisper_model = whisper.load_model("base")
print("Модель Whisper завантажено!")

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
        [InlineKeyboardButton(text="🎙 Аудіо інструменти (Транскрипція)", callback_data="menu_audio")],
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
    await send_main_menu(message, "Привіт! Я твій помічник для завантаження медіа, генерації ідей та перетворення голосу в текст.")

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
        await message.answer(f"✅ Користувачу `{tid}` активовано PRO!")
        await bot.send_message(tid, "🎉 Вашу оплату підтверджено! PRO активовано.")
    except:
        await message.answer("Помилка в ID.")

@dp.callback_query(F.data == "menu_video")
async def cb_vid(callback: types.CallbackQuery):
    text = "🎥 **Завантаження відео**\n\nНадішліть мені посилання на відео з **TikTok**, і я завантажу його без водяного знака!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

async def expand_url(url: str) -> str:
    if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, allow_redirects=True, timeout=10) as resp:
                    return str(resp.url)
        except:
            pass
    return url

@dp.message(F.text.startswith("http"))
async def down_media(message: types.Message):
    raw_url = message.text.strip()
    status = await message.answer("⏳ Завантажую відео з TikTok...")
    
    url = await expand_url(raw_url)
    tpl = f"downloads_{message.from_user.id}.%(ext)s"
    
    opts = {
        'outtmpl': tpl,
        'format': 'best/best',
        'noplaylist': True,
        'extractor_args': {'tiktok': {'web_app': ['1']}},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    try:
        def d():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
                
        f_path = await asyncio.to_thread(d)
        
        if os.path.exists(f_path):
            await message.answer_video(FSInputFile(f_path), caption="✅ Ось ваше відео!")
            os.remove(f_path)
        else:
            await message.answer("❌ Файл не знайдено.")
        
        await status.delete()
        await send_main_menu(message, "Готово! Що робимо далі?")
    except Exception as e:
        logging.error(f"Download error: {e}")
        await status.edit_text("❌ Помилка завантаження. Перевірте посилання на TikTok і спробуйте ще раз.")
        await send_main_menu(message)

@dp.callback_query(F.data == "menu_audio")
async def cb_aud(callback: types.CallbackQuery):
    text = (
        "🎙 **Аудіо інструменти (Транскрипція)**\n\n"
        "Надішліть мені **голосове повідомлення**, **аудіофайл** або **відео**, і я перетворю голос на текст!\n\n"
        "⏱ **Ліміти тривалості:**\n"
        "• Безкоштовний: до **2 хвилин**\n"
        "• PRO: до **12 хвилин**"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# Універсальний обробник аудіо, голосу та відео для перетворення в текст
@dp.message(F.voice | F.audio | F.video | F.document)
async def transcribe_media(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    # Визначаємо ліміт у секундах (Free = 120 сек / 2 хв, PRO = 720 сек / 12 хв)
    max_duration = 720 if is_pro else 120
    
    file_id = None
    duration = 0
    file_type = "аудіо/відео"
    
    if message.voice:
        file_id = message.voice.file_id
        duration = message.voice.duration
        file_type = "голосового повідомлення"
    elif message.audio:
        file_id = message.audio.file_id
        duration = message.audio.duration or 0
        file_type = "аудіофайлу"
    elif message.video:
        file_id = message.video.file_id
        duration = message.video.duration
        file_type = "відео"
    elif message.document:
        # Перевірка чи це аудіо/відео документ за міметайпом
        if message.document.mime_type and ("audio" in message.document.mime_type or "video" in message.document.mime_type):
            file_id = message.document.file_id
            file_type = "файлу"
        else:
            return
            
    # Перевірка на ліміт тривалості (якщо тривалість відома)
    if duration > 0 and duration > max_duration:
        limit_text = "12 хвилин" if is_pro else "2 хвилини"
        await message.answer(
            f"❌ Ваш файл триває {duration // 60} хв. {duration % 60} сек., що перевищує ліміт для вашого статусу ({limit_text}).\n"
            f"💎 Придбайте PRO-підписку, щоб збільшити ліміт до 12 хвилин!"
        )
        await send_main_menu(message)
        return

    status = await message.answer(f"⏳ Завантажую та розпізнаю текст із {file_type}...")
    
    file_info = await bot.get_file(file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    
    input_path = f"temp_{user_id}.tmp"
    audio_path = f"temp_{user_id}.mp3"
    
    with open(input_path, "wb") as f:
        f.write(downloaded_file.read())
        
    try:
        # Якщо це відео, витягуємо з нього аудіодорожку через moviepy
        if message.video or message.document:
            def extract_audio():
                clip = mp.VideoFileClip(input_path)
                # Перевірка тривалості через clip, якщо в об'єкті не було тривалості
                if clip.duration > max_duration:
                    clip.close()
                    raise ValueError("DURATION_EXCEEDED")
                clip.audio.write_audiofile(audio_path, logger=None)
                clip.close()
            
            try:
                await asyncio.to_thread(extract_audio)
            except ValueError:
                os.remove(input_path)
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                limit_str = "12 хвилин" if is_pro else "2 хвилини"
                await status.edit_text(f"❌ Відео занадто довге! Максимальна тривалість для вас — {limit_str}.")
                await send_main_menu(message)
                return
        else:
            # Для звичайного голосу / аудіо просто перейменовуємо/конвертуємо
            os.rename(input_path, audio_path)
            
        # Розпізнавання мови через Whisper в окремому потоці
        def run_whisper():
            result = whisper_model.transcribe(audio_path, language="uk") # Штучний інтелект розпізнає українську (або мову оригіналу)
            return result["text"]
            
        text_result = await asyncio.to_thread(run_whisper)
        
        # Видаляємо тимчасові файли
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(audio_path):
            os.remove(audio_path)
            
        await status.delete()
        
        if not text_result.strip():
            await message.answer("⚠️ Не вдалося розпізнати розмову в цьому файлі (можливо, тиша або занадто шумний звук).")
        else:
            await message.answer(f"📝 **Розпізнаний текст:**\n\n{text_result}", parse_mode="Markdown")
            
        await send_main_menu(message, "Що робимо далі?")
        
    except Exception as e:
        logging.error(f"Transcribe error: {e}")
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(audio_path):
            os.remove(audio_path)
        await status.edit_text("❌ Сталася помилка під час обробки аудіо/відео. Спробуйте ще раз.")
        await send_main_menu(message)

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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
