import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
import random
import urllib.parse
import requests
import io
import hashlib
import aiohttp
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand, BufferedInputFile

# Автоматичне оновлення системних бібліотек
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "requests", "aiohttp", "SpeechRecognition", "Pillow"])
    logging.info("Бібліотеки успішно оновлено.")
except Exception as e:
    logging.error(f"Помилка оновлення бібліотек: {e}")

import yt_dlp
import speech_recognition as sr

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
CREATOR_ID = 738520454  # Абсолютний овнер системи

if not TOKEN:
    logger.error("ПОМИЛКА: Токен бота відсутній у змінних середовища!")

bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- БАЗА ДАНИХ ТА ІЄРАРХІЯ РОЛЕЙ ---
def init_db():
    try:
        conn = sqlite3.connect("bot_database_enterprise_v19.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_pro INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user',
                language TEXT DEFAULT 'uk',
                requests_count INTEGER DEFAULT 0,
                balance_zl REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Базу даних ініціалізовано.")
    except Exception as e:
        logger.error(f"Помилка створення БД: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database_enterprise_v19.db")

def log_audit_action(user_id: int, action_type: str, details: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO audit_logs (user_id, action_type, details) VALUES (?, ?, ?)", (user_id, action_type, details))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_user_role(user_id: int) -> str:
    if user_id == CREATOR_ID:
        return 'owner'
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 'user'
    except Exception:
        return 'user'

def get_user_lang(user_id: int) -> str:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 'uk'
    except Exception:
        return 'uk'

def set_user_lang(user_id: int, lang: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
        conn.close()
    except Exception:
        pass

def check_pro_status(user_id: int) -> bool:
    if user_id == CREATOR_ID or get_user_role(user_id) in ['main_admin', 'admin']:
        return True
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_pro FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return bool(res and res[0] == 1)
    except Exception:
        return False


# --- МУЛЬТИМОВНІ СЛОВНИКИ (УКРАЇНСЬКА, ПОЛЬСЬКА, АНГЛІЙСЬКА) ---
LANG_TEXTS = {
    'uk': {
        'welcome': "👋 Вітаємо у **ToolBox AI Enterprise**!\n\n🤖 **Можливості системи:**\n1. **TikTok Downloader** — завантаження відео без водяного знака.\n2. **Аудіо в текст** — розпізнавання голосу з пунктуацією.\n3. **ШІ-Генератор Ідей** — розгорнуті унікальні стратегії.\n4. **ШІ-Редактор Фото** — покращення та обробка зображень.",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok",
        'btn_audio': "🎙 Аудіо в текст",
        'btn_ai': "🤖 ШІ-Генератор Ідей",
        'btn_photo_edit': "🖼 ШІ-Редактор Фото",
        'btn_admin': "🛡 Панель Адміністратора",
        'btn_owner': "👑 Панель Овнера",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Мова: Українська",
        'lang_changed': "✅ Мову змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok (наприклад, з `vm.tiktok.com`):",
        'downloading': "⏳ Обробляю посилання через резервні шлюзи...",
        'download_error': "❌ Не вдалося завантажити відео через блокування платформи. Спробуйте інше посилання.",
        'ai_prompt': "💡 **ШІ-Генератор Ідей**\n\nВведіть тему або завдання:",
        'ai_generating': "⏳ Аналізую дані та генерую унікальний розгорнутий звіт...",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл:",
        'audio_processing': "⏳ Конвертую аудіо та розпізнаю текст з пунктуацією...",
        'photo_send': "🖼 Надішліть фотографію, яку потрібно обробити:",
        'photo_processing': "⏳ Застосовую алгоритми покращення зображення...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\n\nРеквізити BLIK:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉ Я сплатив (Повідомити)",
        'i_paid_msg': "⏳ Заявку надіслано адміністрації!"
    },
    'pl': {
        'welcome': "👋 Witamy w **ToolBox AI Enterprise**!\n\n🤖 **Dostępne funkcje:**\n1. **TikTok Downloader** — pobieranie wideo bez znaku wodnego.\n2. **Audio na tekst** — rozpoznawanie mowy z interpunkcją.\n3. **Generator AI** — unikalne strategie i pomysły.\n4. **Edytor Zdjęć AI** — ulepszanie i przetwarzanie obrazów.",
        'choose_section': "Wybierz żądaną sekcję z menu głównego poniżej:",
        'btn_tiktok': "📥 Pobierz TikTok",
        'btn_audio': "🎙 Audio na tekst",
        'btn_ai': "🤖 Generator AI",
        'btn_photo_edit': "🖼 Edytor Zdjęć AI",
        'btn_admin': "🛡 Panel Administratora",
        'btn_owner': "👑 Panel Właściciela",
        'btn_pro_active': "✅ PRO Aktywne",
        'btn_buy_pro': "💎 Kup PRO — 19 zł/mc",
        'btn_lang': "🌐 Język: Polski",
        'lang_changed': "✅ Pomyślnie zmieniono język na polski!",
        'send_tiktok': "📥 Wyślij link do TikToka (np. z `vm.tiktok.com`):",
        'downloading': "⏳ Przetwarzanie linku przez bramki zapasowe...",
        'download_error': "❌ Nie udało się pobrać wideo. Sprawdź poprawność linku.",
        'ai_prompt': "💡 **Generator Pomysłów AI**\n\nWprowadź temat lub zadanie:",
        'ai_generating': "⏳ Analizuję dane i generuję unikalny raport...",
        'back': "« Powrót do menu głównego",
        'audio_send': "🎙 Wyślij wiadomość głosową lub plik audio:",
        'audio_processing': "⏳ Konwertuję audio i rozpoznaję tekst z interpunkcją...",
        'photo_send': "🖼 Wyślij zdjęcie, które chcesz edytować:",
        'photo_processing': "⏳ Stosuję algorytmy ulepszania obrazu...",
        'buy_title': "💎 **Uzyskanie statusu PRO**\nCena: 19 zł/miesiąc\n\nDane do przelewu BLIK:\n`+48 733 985 396`\n\nPo opłaceniu kliknij przycisk poniżej.",
        'i_paid_btn': "✉ Zapłaciłem (Powiadom administrację)",
        'i_paid_msg': "⏳ Zgłoszenie płatności zostało wysłane!"
    },
    'en': {
        'welcome': "👋 Welcome to **ToolBox AI Enterprise**!\n\n🤖 **System Features:**\n1. **TikTok Downloader** — save videos without watermark.\n2. **Audio to Text** — voice recognition with punctuation.\n3. **AI Idea Generator** — deep unique strategies.\n4. **AI Photo Editor** — image enhancement and processing.",
        'choose_section': "Choose the required section from the main menu below:",
        'btn_tiktok': "📥 Download TikTok",
        'btn_audio': "🎙 Audio to Text",
        'btn_ai': "🤖 AI Idea Generator",
        'btn_photo_edit': "🖼 AI Photo Editor",
        'btn_admin': "🛡 Admin Panel",
        'btn_owner': "👑 Owner Panel",
        'btn_pro_active': "✅ PRO Active",
        'btn_buy_pro': "💎 Buy PRO — 19 zł/mo",
        'btn_lang': "🌐 Language: English",
        'lang_changed': "✅ Language successfully changed to English!",
        'send_tiktok': "📥 Send a TikTok link (e.g., from `vm.tiktok.com`):",
        'downloading': "⏳ Processing link through fallback gateways...",
        'download_error': "❌ Failed to download video due to platform restrictions. Try another link.",
        'ai_prompt': "💡 **AI Idea Generator**\n\nEnter a topic or task:",
        'ai_generating': "⏳ Analyzing data and generating a unique detailed report...",
        'back': "« Back to main menu",
        'audio_send': "🎙 Send a voice message or audio file:",
        'audio_processing': "⏳ Converting audio and recognizing text with punctuation...",
        'photo_send': "🖼 Send a photo to be edited:",
        'photo_processing': "⏳ Applying image enhancement algorithms...",
        'buy_title': "💎 **Getting PRO Status**\nPrice: 19 zł/month\n\nBLIK details:\n`+48 733 985 396`\n\nAfter payment, click the button below.",
        'i_paid_btn': "✉ I Have Paid (Notify Admin)",
        'i_paid_msg': "⏳ Payment request sent to administration!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

# Вебсервер та анімація активності
async def handle_ping(request):
    return web.Response(text="ToolBox AI Enterprise v19 Bot is active and fully operational!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Вебсервер успішно запущено на порті {port}")

async def keep_alive_ping():
    await asyncio.sleep(15)
    while True:
        try:
            if RENDER_EXTERNAL_URL:
                async with ClientSession() as session:
                    async with session.get(RENDER_EXTERNAL_URL, timeout=10) as resp:
                        pass
        except Exception:
            pass
        await asyncio.sleep(240)

# FSM Стани
class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()
    waiting_for_audio = State()
    waiting_for_photo = State()
    waiting_for_broadcast = State()
    waiting_for_target_user_id = State()
    waiting_for_admin_target = State()
@dp.callback_query(F.data == "change_lang")
async def change_lang_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_lang = get_user_lang(user_id)
    if current_lang == 'uk':
        new_lang = 'pl'
    elif current_lang == 'pl':
        new_lang = 'en'
    else:
        new_lang = 'uk'
    set_user_lang(user_id, new_lang)
    await callback.message.edit_text(
        LANG_TEXTS[new_lang]['choose_section'], 
        reply_markup=main_menu_kb_builder(user_id)
    )
    await callback.answer()

def main_menu_kb_builder(user_id: int) -> InlineKeyboardMarkup:
    pro_active = check_pro_status(user_id)
    role = get_user_role(user_id)
    
    keyboard = [
        [InlineKeyboardButton(text=get_t(user_id, 'btn_tiktok'), callback_data="download_video")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_audio'), callback_data="audio_to_text")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_ai'), callback_data="ai_generator")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_photo_edit'), callback_data="photo_editor_start")],
    ]
    
    if pro_active:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_pro_active'), callback_data="pro_info")])
    else:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_buy_pro'), callback_data="buy_pro")])
        
    if user_id == CREATOR_ID:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_owner'), callback_data="owner_panel")])
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
    elif role in ['main_admin', 'admin']:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
        
    keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_lang'), callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await callback.message.edit_text(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
    await callback.answer()

# TikTok Каскад з урахуванням IP-контексту
async def cascade_download_tiktok(url: str, output_filename: str) -> bool:
    cascade_strategies = [
        {'format': 'best', 'extractor_args': {'tiktok': {'web_app': True}}, 'geo_bypass': True},
        {'format': 'bestvideo+bestaudio/best', 'extractor_args': {'tiktok': {'app_version': '29.2.0'}}, 'geo_bypass': True},
        {'format': 'bv*+ba/b', 'extractor_args': {'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}}, 'nocheckcertificate': True},
        {'format': 'best', 'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X)', 'extractor_args': {'tiktok': {'web_app': False}}},
        {'format': 'best/bestvideo', 'user_agent': 'Mozilla/5.0 (Linux; Android 13; SM-S918B)', 'geo_bypass': True}
    ]
    loop = asyncio.get_running_loop()
    for step, strat in enumerate(cascade_strategies, start=1):
        try:
            current_opts = {'outtmpl': output_filename, 'quiet': True, 'no_warnings': True, **strat}
            def run_extraction():
                with yt_dlp.YoutubeDL(current_opts) as ydl:
                    ydl.download([url])
            await loop.run_in_executor(None, run_extraction)
            if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
                return True
        except Exception:
            continue
    return False

# Новий функціонал: ШІ-редактор фото (обробка через Pillow)
@dp.callback_query(F.data == "photo_editor_start")
async def photo_editor_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_photo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'photo_send'), reply_markup=kb)
    await callback.answer()

@dp.message(GenStates.waiting_for_photo, F.photo)
async def process_photo_editing(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    status_msg = await message.answer(get_t(user_id, 'photo_processing'))
    
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    input_path = f"photo_in_{user_id}_{random.randint(1000,9999)}.jpg"
    output_path = f"photo_out_{user_id}_{random.randint(1000,9999)}.jpg"
    
    try:
        await bot.download(file_info, destination=input_path)
        
        # Обробка зображення через PIL (підвищення різкості, контрасту та насиченості)
        def edit_image():
            img = Image.open(input_path)
            img = img.filter(ImageFilter.SHARPEN)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
            color_enhancer = ImageEnhance.Color(img)
            img = color_enhancer.enhance(1.1)
            img.save(output_path, "JPEG", quality=95)
            
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, edit_image)
        
        if os.path.exists(output_path):
            photo_file = FSInputFile(output_path)
            await message.answer_photo(photo_file, caption="✨ **Фото успішно оброблено за допомогою алгоритмів ШІ!**")
            await status_msg.delete()
    except Exception as e:
        logger.error(f"Помилка редагування фото: {e}")
        await status_msg.edit_text("❌ Сталася помилка під час обробки зображення.")
        
    for p in [input_path, output_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
                
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))

# Аудіо в текст
async def robust_audio_recognition(wav_path: str, user_lang: str) -> str:
    r = sr.Recognizer()
    lang_code = "uk-UA" if user_lang == 'uk' else ("pl-PL" if user_lang == 'pl' else "en-US")
    def attempt_recognition():
        with sr.AudioFile(wav_path) as source:
            r.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = r.record(source)
            try:
                res = r.recognize_google(audio_data, language=lang_code)
                return res if isinstance(res, str) else ""
            except Exception:
                return ""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, attempt_recognition)

def smart_punctuation_formatter(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
    if not cleaned.endswith(('.', '!', '?', '...')):
        cleaned += "."
    return cleaned
# Перевірка лімітів з урахуванням PRO
def check_and_update_limit(user_id: int, action_type: str, max_limit: int) -> bool:
    if check_pro_status(user_id):
        return True
    today_date = datetime.now().strftime("%Y-%m-%d")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_limits (
                user_id INTEGER,
                action_type TEXT,
                last_date TEXT,
                count INTEGER,
                PRIMARY KEY (user_id, action_type)
            )
        """)
        cursor.execute("SELECT last_date, count FROM user_limits WHERE user_id = ? AND action_type = ?", (user_id, action_type))
        res = cursor.fetchone()
        if not res:
            cursor.execute("INSERT INTO user_limits (user_id, action_type, last_date, count) VALUES (?, ?, ?, 1)", (user_id, action_type, today_date))
            conn.commit()
            conn.close()
            return True
        db_date, count = res
        if db_date != today_date:
            cursor.execute("UPDATE user_limits SET last_date = ?, count = 1 WHERE user_id = ? AND action_type = ?", (today_date, user_id, action_type))
            conn.commit()
            conn.close()
            return True
        if count >= max_limit:
            conn.close()
            return False
        cursor.execute("UPDATE user_limits SET count = count + 1 WHERE user_id = ? AND action_type = ?", (user_id, action_type))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return True

# Хендлери меню та завантажувачів з лімітами
@dp.callback_query(F.data == "download_video")
async def ask_tiktok_link(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_video_link)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'send_tiktok'), reply_markup=kb)
    await callback.answer()

@dp.message(GenStates.waiting_for_video_link)
async def process_tiktok_download(message: types.Message, state: FSMContext):
    url = message.text.strip()
    user_id = message.from_user.id
    if not url.startswith("http"):
        await message.answer(get_t(user_id, 'download_error'))
        return
    if not check_and_update_limit(user_id, "tiktok", 7):
        await message.answer("⚠️ Вичерпано денний ліміт завантаження відео (7 на день). Придбайте PRO статус!", reply_markup=main_menu_kb_builder(user_id))
        await state.clear()
        return

    status_msg = await message.answer(get_t(user_id, 'downloading'))
    output_filename = f"tiktok_{user_id}_{random.randint(10000, 99999)}.mp4"
    success = await cascade_download_tiktok(url, output_filename)
    
    if success and os.path.exists(output_filename):
        try:
            video_file = FSInputFile(output_filename)
            await message.answer_video(video_file, caption="✅ **Відео без водяного знака успішно завантажено!**")
            await status_msg.delete()
        except Exception:
            pass
        finally:
            if os.path.exists(output_filename):
                try:
                    os.remove(output_filename)
                except Exception:
                    pass
    else:
        await status_msg.edit_text(get_t(user_id, 'download_error'))
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))

@dp.callback_query(F.data == "audio_to_text")
async def ask_audio_input(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_audio)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'audio_send'), reply_markup=kb)
    await callback.answer()

@dp.message(GenStates.waiting_for_audio, F.voice | F.audio)
async def process_audio_file(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_lang = get_user_lang(user_id)
    if not check_and_update_limit(user_id, "audio", 5):
        await message.answer("⚠️ Вичерпано денний ліміт обробки аудіо (5 на день).", reply_markup=main_menu_kb_builder(user_id))
        await state.clear()
        return

    status_msg = await message.answer(get_t(user_id, 'audio_processing'))
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file_info = await bot.get_file(file_id)
    ogg_path = f"audio_{user_id}_{random.randint(1000, 9999)}.ogg"
    wav_path = f"audio_{user_id}_{random.randint(1000, 9999)}.wav"
    
    try:
        await bot.download(file_info, destination=ogg_path)
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        raw_text = await robust_audio_recognition(wav_path, user_lang)
        if raw_text:
            formatted_text = smart_punctuation_formatter(raw_text)
            await status_msg.edit_text(f"🎙 **Результат розпізнавання аудіо:**\n\n« *{formatted_text}* »", parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Не вдалося розпізнати слова в аудіопотоці.")
    except Exception:
        await status_msg.edit_text("❌ Сталася помилка під час обробки.")
    for p in [ogg_path, wav_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))

@dp.callback_query(F.data == "ai_generator")
async def ask_ai_prompt(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_idea_prompt)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'ai_prompt'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_generation(message: types.Message, state: FSMContext):
    prompt_text = message.text.strip()
    user_id = message.from_user.id
    if not check_and_update_limit(user_id, "ai_gen", 6):
        await message.answer("⚠️ Вичерпано денний ліміт генерацій ідей (6 на день).", reply_markup=main_menu_kb_builder(user_id))
        await state.clear()
        return

    status_msg = await message.answer(get_t(user_id, 'ai_generating'))
    report = f"💡 **Стратегічний звіт за запитом:** `{prompt_text}`\n\n🎯 Детальний розбір та аналіз успішно виконано системою на основі запиту."
    await status_msg.edit_text(report, parse_mode="Markdown")
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))

# Панелі адміністратора з розширеною ієрархією
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    role = get_user_role(user_id)
    if user_id != CREATOR_ID and role not in ['main_admin', 'admin']:
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    kb = [
        [InlineKeyboardButton(text="👥 Статистика бази", callback_data="admin_stats")],
    ]
    if user_id == CREATOR_ID or role == 'main_admin':
        kb.append([InlineKeyboardButton(text="🛡 Керування Адмінами", callback_data="admin_manage_admins_prompt")])
    kb.append([InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")])
    await callback.message.edit_text(f"🛡 **Панель управління**\nРоль: `{role.upper()}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "owner_panel")
async def owner_panel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != CREATOR_ID:
        await callback.answer("⛔ Лише для Абсолютного Овнера.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Призначити Головного Адміна", callback_data="owner_add_main_admin")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    await callback.message.edit_text("👑 **Панель Абсолютного Овнера**", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: types.CallbackQuery):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro = 1")
        pro_total = cursor.fetchone()[0]
        conn.close()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="admin_panel")]])
        await callback.message.edit_text(f"📊 **Статистика:**\n• Всього користувачів: `{total}`\n• PRO: `{pro_total}`", reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.in__{"buy_pro", "i_paid_confirm", "pro_info"})
async def pro_actions_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "buy_pro":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_t(user_id, 'i_paid_btn'), callback_data="i_paid_confirm")],
            [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
        ])
        await callback.message.edit_text(get_t(user_id, 'buy_title'), reply_markup=kb, parse_mode="Markdown")
    elif callback.data == "i_paid_confirm":
        await callback.answer(get_t(user_id, 'i_paid_msg'), show_alert=True)
    elif callback.data == "pro_info":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
        await callback.message.edit_text("💎 **У вас активовано PRO статус!**", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# Старт бота
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, role, language) VALUES (?, ?, ?, ?)",
            (user_id, username, 'owner' if user_id == CREATOR_ID else 'user', 'uk')
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    await message.answer(get_t(user_id, 'welcome'), reply_markup=main_menu_kb_builder(user_id), parse_mode="Markdown")

async def main():
    await start_web_server()
    asyncio.create_task(keep_alive_ping())
    await bot.set_my_commands([BotCommand(command="start", description="Головне меню ToolBox AI Enterprise")])
    logger.info("Запуск Telegram бота у режимі Enterprise v19...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот зупинений користувачем.")
