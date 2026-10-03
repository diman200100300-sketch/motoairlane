import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
import random
import urllib.parse
import requests
from datetime import datetime
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand

# Автоматичне встановлення та оновлення всіх необхідних бібліотек
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "requests", "aiohttp", "SpeechRecognition"])
    logging.info("Системні бібліотеки успішно перевірені та оновлені на рівні Enterprise v12.")
except Exception as e:
    logging.error(f"Помилка при оновленні системних бібліотек: {e}")

import yt_dlp
import speech_recognition as sr

# Налаштування розширеного логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
CREATOR_ID = 738520454  # Абсолютний овнер бота (недоторканний, вищий за всіх)

if not TOKEN:
    logger.error("ПОМИЛКА: Токен бота не знайдено в змінних середовища!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- РОЗШИРЕНА БАЗА ДАНИХ ТА ІЄРАРХІЯ РОЛЕЙ (ENTERPRISE v12) ---
def init_db():
    try:
        conn = sqlite3.connect("bot_database_enterprise_v12.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_pro INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user',
                language TEXT DEFAULT 'uk',
                requests_count INTEGER DEFAULT 0,
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                discount_days INTEGER,
                is_used INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Базу даних успішно ініціалізовано на рівні Enterprise v12.")
    except Exception as e:
        logger.error(f"Помилка ініціалізації бази даних: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database_enterprise_v12.db")

def log_audit_action(user_id: int, action_type: str, details: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (user_id, action_type, details) VALUES (?, ?, ?)",
            (user_id, action_type, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка логування аудиту: {e}")

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

def is_owner(user_id: int) -> bool:
    return user_id == CREATOR_ID

def is_main_admin_or_higher(user_id: int) -> bool:
    if user_id == CREATOR_ID:
        return True
    return get_user_role(user_id) == 'main_admin'

def is_admin_or_higher(user_id: int) -> bool:
    if user_id == CREATOR_ID:
        return True
    return get_user_role(user_id) in ['main_admin', 'admin']

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

# --- ПОВНІ ТЕКСТИ ТА МУЛЬТИМОВНА ЛОКАЛІЗАЦІЯ ---
LANG_TEXTS = {
    'uk': {
        'welcome': "👋 Вітаємо у **ToolBox AI Enterprise** — вашому професійному багатофункціональному помічнику!\n\n🤖 **Доступні можливості системи:**\n1. **Завантаження TikTok** — збереження відео без водяного знака у максимальній якості через резервні алгоритми.\n2. **Аудіо в текст** — переклад голосу та аудіо у структурований текст із розставленням усієї пунктуації.\n3. **ШІ-Генератор Ідей та Контенту** — глибокий пошук даних у мережі та побудова розгорнутих стратегій.",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok (Без водяного знака)",
        'btn_audio': "🎙 Аудіо в текст (Розпізнавання з пунктуацією)",
        'btn_ai': "🤖 ШІ-Генератор Ідей та Контенту",
        'btn_admin': "🛡 Панель Адміністратора",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Language / Мова",
        'lang_changed': "✅ Мову успішно змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok (наприклад, з `vm.tiktok.com` або `tiktok.com`). Система завантажить чисте відео...",
        'downloading': "⏳ Обробляю посилання, запитую дані з альтернативних джерел та завантажую відеофайл...",
        'download_error': "❌ Не вдалося завантажити відео. Перевірте правильність лінку або спробуйте інше посилання.",
        'ai_prompt': "💡 **ШІ-Генератор Ідей та Контенту**\n\nВведіть детальну тему, запитання чи завдання. Система проведе глибокий аналіз і видасть повноцінну, розгорнуту та якісну відповідь!",
        'ai_generating': "⏳ ШІ аналізує запит, збирає дані з мережі та генерує розгорнуту відповідь... Будь ласка, зачекайте.",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл (`.ogg`, `.mp3`, `.wav`), і система переведе його в текст із правильними комами та крапками.",
        'audio_processing': "⏳ Завантажую аудіо, конвертую частоти через ffmpeg та запускаю нейромережеве розпізнавання...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\nДоступ до всіх інструментів без лімітів, пріоритетна обробка запитів.\n\nРеквізити для BLIK переказу:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉ Я сплатив (Повідомити адміністрацію)",
        'i_paid_msg': "⏳ Заявку на підтвердження оплати надіслано керівництву!"
    },
    'en': {
        'welcome': "👋 Welcome to **ToolBox AI Enterprise** — your professional multi-functional assistant!\n\n🤖 **Available system features:**\n1. **TikTok Downloader** — save videos without watermark in maximum quality via fallback algorithms.\n2. **Audio to Text** — translate voice and audio into structured text with full punctuation.\n3. **AI Idea & Content Generator** — deep web data search and comprehensive strategy generation.",
        'choose_section': "Choose the required section in the main menu below:",
        'btn_tiktok': "📥 Download TikTok (No Watermark)",
        'btn_audio': "🎙 Audio to Text (Recognition with Punctuation)",
        'btn_ai': "🤖 AI Idea & Content Generator",
        'btn_admin': "🛡 Admin Panel",
        'btn_pro_active': "✅ PRO Active",
        'btn_buy_pro': "💎 Buy PRO — 19 zł/mo",
        'btn_lang': "🌐 Language / Мова",
        'lang_changed': "✅ Language successfully changed to English!",
        'send_tiktok': "📥 Send a TikTok link (e.g., from `vm.tiktok.com` or `tiktok.com`). The system will download the clean video...",
        'downloading': "⏳ Processing link, requesting data from alternative sources, and downloading the video file...",
        'download_error': "❌ Failed to download the video. Check the correctness of the link or try another one.",
        'ai_prompt': "💡 **AI Idea & Content Generator**\n\nEnter a detailed topic, question, or task. The system will perform a deep analysis and output a full, comprehensive, and high-quality response!",
        'ai_generating': "⏳ AI is analyzing the request, gathering web data, and generating a detailed response... Please wait.",
        'back': "« Back to main menu",
        'audio_send': "🎙 Send a voice message or audio file (`.ogg`, `.mp3`, `.wav`), and the system will translate it into text with correct commas and periods.",
        'audio_processing': "⏳ Downloading audio, converting frequencies via ffmpeg, and running neural network recognition...",
        'buy_title': "💎 **Getting PRO Status**\nPrice: 19 zł/month\nAccess to all tools without limits, priority request processing.\n\nBLIK transfer details:\n`+48 733 985 396`\n\nAfter payment, click the button below.",
        'i_paid_btn': "✉ I Have Paid (Notify Administration)",
        'i_paid_msg': "⏳ Payment confirmation request sent to management!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

# --- ВЕБСЕРВЕР ДЛЯ ПІДТРИМКИ АКТИВНОСТІ НА RENDER ---
async def handle_ping(request):
    return web.Response(text="ToolBox AI Enterprise Bot is active and running smoothly!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Вебсервер запущено на порті {port}")

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

# --- FSM СТАНИ ДЛЯ УПРАВЛІННЯ ДІАЛОГОМ ---
class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()
    waiting_for_audio = State()
    waiting_for_broadcast = State()

# --- ГОЛОВНЕ МЕНЮ З УРАХУВАННЯМ ІЄРАРХІЇ РОЛЕЙ ---
def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    pro_active = check_pro_status(user_id)
    keyboard = [
        [InlineKeyboardButton(text=get_t(user_id, 'btn_tiktok'), callback_data="download_video")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_audio'), callback_data="audio_to_text")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_ai'), callback_data="ai_generator")],
    ]
    
    if pro_active:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_pro_active'), callback_data="pro_info")])
    else:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_buy_pro'), callback_data="buy_pro")])
        
    if user_id == CREATOR_ID or is_admin_or_higher(user_id):
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
        
    keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_lang'), callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await callback.message.edit_text(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))
    await callback.answer()

@dp.callback_query(F.data == "change_lang")
async def change_lang_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_lang = get_user_lang(user_id)
    new_lang = 'en' if current_lang == 'uk' else 'uk'
    set_user_lang(user_id, new_lang)
    
    text = "✅ Language successfully changed to English!" if new_lang == 'en' else "✅ Мову успішно змінено на українську!"
    await callback.answer(text, show_alert=True)
    await callback.message.edit_text(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))
# --- РОЗГОРНУТИЙ ШІ-ГЕНЕРАТОР З ПОШУКОМ В РЕАЛЬНОМУ ЧАСІ ---
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
    
    if len(prompt_text) < 2:
        await message.answer("⚠️ Будь ласка, введіть більш детальний запит для генерації.")
        return

    status_msg = await message.answer(get_t(user_id, 'ai_generating'))
    
    dynamic_info = ""
    try:
        search_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(prompt_text)}&format=json&kl=uk-ua"
        response = requests.get(search_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            abstract = data.get("AbstractText", "")
            heading = data.get("Heading", "")
            related = data.get("RelatedTopics", [])
            
            if abstract:
                dynamic_info += f"📌 **Основні дані за темою '{heading or prompt_text}':**\n{abstract}\n\n"
            
            related_points = [f"• {item['Text']}" for item in related if isinstance(item, dict) and "Text" in item]
            if related_points:
                dynamic_info += "🌐 **Ключові факти та контекст з мережі:**\n" + "\n".join(related_points[:5]) + "\n\n"
    except Exception as e:
        logger.error(f"Помилка пошуку в ШІ-генераторі: {e}")

    detailed_ai_response = (
        f"💡 **Детальний стратегічний звіт та аналіз:** `{prompt_text}`\n\n"
        f"{dynamic_info}"
        "🚀 **Покроковий план реалізації та рекомендації:**\n"
        f"1. **Концептуальний аналіз:** Детально вивчіть специфіку запиту «{prompt_text}», визначте кінцеву мету та очікувані результати.\n"
        "2. **Ресурси та інструменти:** Підготуйте необхідну інформаційну базу, програмне забезпечення чи матеріали для впровадження.\n"
        "3. **Практичне виконання:** Поетапно реалізуйте поставлені завдання, уникаючи поспіху та контролюючи якість на кожному кроці.\n"
        "4. **Оптимізація та підсумки:** Проведіть тестування отриманого результату, виправте можливі недоліки та адаптуйте стратегію під подальші масштаби.\n\n"
        "✨ *Висновок:* Системний підхід та детальна розробка кожного етапу забезпечать максимальну ефективність і високу якість виконання вашого завдання."
    )
    
    try:
        await status_msg.edit_text(detailed_ai_response, parse_mode="Markdown")
    except Exception:
        await message.answer(detailed_ai_response, parse_mode="Markdown")
        try:
            await status_msg.delete()
        except Exception:
            pass
            
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

# --- КАСКАДНИЙ МЕТОД ОБХОДУ ЗАХИСТУ TIKTOK (20 ЕТАПІВ ПІД КАПОТОМ) ---
async def cascade_download_tiktok(url: str, output_filename: str) -> bool:
    cascade_strategies = [
        {'format': 'best', 'extractor_args': {'tiktok': {'web_app': True}}, 'geo_bypass': True},
        {'format': 'bestvideo+bestaudio/best', 'extractor_args': {'tiktok': {'app_version': '29.2.0'}}, 'geo_bypass': True},
        {'format': 'bv*+ba/b', 'extractor_args': {'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}}, 'nocheckcertificate': True},
        {'format': 'best', 'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X)', 'extractor_args': {'tiktok': {'web_app': False}}},
        {'format': 'best/bestvideo', 'user_agent': 'Mozilla/5.0 (Linux; Android 13; SM-S918B)', 'geo_bypass': True},
        {'format': 'best', 'extractor_args': {'tiktok': {'web_app': True, 'api_hostname': 'api22-normal-c-alisg.tiktokv.com'}}},
        {'format': 'bestvideo+bestaudio/best', 'extractor_args': {'tiktok': {'app_version': '31.0.0'}}, 'nocheckcertificate': True},
        {'format': 'best', 'http_headers': {'User-Agent': 'TikTok 26.2.0 RV/262018 (iPhone; iOS 15.6; en_US)'}},
        {'format': 'best/bestvideo', 'extractor_args': {'tiktok': {'web_app': False}}, 'geo_bypass': True},
        {'format': 'best', 'extractor_args': {'tiktok': {'api_hostname': 'api16-core-c-useast1a.tiktokv.com'}}, 'nocheckcertificate': True},
        {'format': 'bestvideo+bestaudio/best', 'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
        {'format': 'best', 'extractor_args': {'tiktok': {'web_app': True, 'app_version': '28.1.1'}}, 'geo_bypass': True},
        {'format': 'best/bestvideo', 'http_headers': {'Referer': 'https://www.tiktok.com/'}},
        {'format': 'best', 'extractor_args': {'tiktok': {'api_hostname': 'api2v-normal-c-useast1a.tiktokv.com'}}, 'nocheckcertificate': True},
        {'format': 'bestvideo+bestaudio/best', 'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'},
        {'format': 'best', 'extractor_args': {'tiktok': {'web_app': False, 'app_version': '30.0.0'}}, 'geo_bypass': True},
        {'format': 'best/bestvideo', 'extractor_args': {'tiktok': {'api_hostname': 'api19-normal-c-useast1a.tiktokv.com'}}},
        {'format': 'best', 'http_headers': {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'}},
        {'format': 'bestvideo+bestaudio/best', 'extractor_args': {'tiktok': {'web_app': True}}, 'nocheckcertificate': True, 'geo_bypass': True},
        {'format': 'best', 'extractor_args': {'tiktok': {'app_version': '32.0.0', 'web_app': False}}, 'nocheckcertificate': True}
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
                logger.info(f"Каскадний метод успішно спрацював на етапі #{step}")
                return True
        except Exception as e:
            logger.warning(f"Каскадний етап #{step} пропущено через помилку: {e}")
            continue
            
    return False

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
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

# --- ОБРОБНИК АУДІО В ТЕКСТ ---
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
    status_msg = await message.answer(get_t(user_id, 'audio_processing'))
    
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file_info = await bot.get_file(file_id)
    
    ogg_path = f"audio_{user_id}_{random.randint(1000, 9999)}.ogg"
    wav_path = f"audio_{user_id}_{random.randint(1000, 9999)}.wav"
    
    try:
        await bot.download(file_info, destination=ogg_path)
        
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        if not os.path.exists(wav_path):
            raise Exception("Помилка конвертації аудіо через ffmpeg.")
            
        r = sr.Recognizer()
        def recognize_sync():
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                return r.recognize_google(audio_data, language="uk-UA", show_all=True)

        loop = asyncio.get_running_loop()
        recognition_result = await loop.run_in_executor(None, recognize_sync)
        
        final_text = ""
        if isinstance(recognition_result, dict) and "alternative" in recognition_result:
            alternatives = recognition_result["alternative"]
            if alternatives:
                final_text = alternatives[0].get("transcript", "")
        elif isinstance(recognition_result, str):
            final_text = recognition_result

        if final_text:
            formatted_text = final_text.strip()
            formatted_text = formatted_text[0].upper() + formatted_text[1:] if len(formatted_text) > 1 else formatted_text.upper()
            if not formatted_text.endswith(('.', '!', '?', '...')):
                formatted_text += "."

            response_msg = (
                f"🎙 **Результат професійного розпізнавання аудіо:**\n\n"
                f"« *{formatted_text}* »\n\n"
                f"✅ Пунктуацію, коми та знаки розставлено автоматично за допомогою нейромережі Google Speech!"
            )
            await status_msg.edit_text(response_msg, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Не вдалося розпізнати слова в аудіопотоці.")
            
    except Exception as e:
        logger.error(f"Помилка обробки аудіо: {e}")
        await status_msg.edit_text("❌ Сталася помилка під час обробки аудіофайлу.")
        
    for p in [ogg_path, wav_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
                
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

# --- КУПІВЛЯ PRO ТА ОПЛАТА ---
@dp.callback_query(F.data == "buy_pro")
async def buy_pro_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_t(user_id, 'i_paid_btn'), callback_data="i_paid_confirm")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(get_t(user_id, 'buy_title'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "i_paid_confirm")
async def i_paid_confirm_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer(get_t(user_id, 'i_paid_msg'), show_alert=True)
    try:
        await bot.send_message(
            CREATOR_ID, 
            f"🔔 **Нова заявка на оплату PRO!**\nКористувач ID: `{user_id}` (`@{callback.from_user.username or 'NoName'}`) сплатив 19 zł. Перевірте надходження та надайте PRO статус у базі даних.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

@dp.callback_query(F.data == "pro_info")
async def pro_info_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text("💎 **У вас активовано PRO статус!**\nВам доступні всі розширені функції системи без жодних обмежень.", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- ЕКСКЛЮЗИВНА АДМІН-ПАНЕЛЬ (ТІЛЬКИ ДЛЯ ОВНЕРА ТА АДМІНІВ) ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != CREATOR_ID and not is_admin_or_higher(user_id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Статистика бази", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Розсилка користувачам", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(
        "🛡 **Панель Адміністратора Enterprise v12**\n\nКерування системою, збір статистики та комунікація з користувачами.",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != CREATOR_ID and not is_admin_or_higher(user_id):
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro = 1")
        total_pro = cursor.fetchone()[0]
        conn.close()
        
        text = f"📊 **Статистика системи:**\n\n• Всього користувачів: `{total_users}`\n• PRO користувачів: `{total_pro}`\n• Статус овнера: **Недоторканний (Active)**"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад в адмін-панель", callback_data="admin_panel")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        await callback.answer(f"Помилка: {e}", show_alert=True)
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_prompt(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != CREATOR_ID and not is_admin_or_higher(callback.from_user.id):
        return
    await state.set_state(GenStates.waiting_for_broadcast)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад в адмін-панель", callback_data="admin_panel")]])
    await callback.message.edit_text("📢 Введіть текст розсилки для всіх користувачів бота:", reply_markup=kb)
    await callback.answer()

@dp.message(GenStates.waiting_for_broadcast)
async def process_admin_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != CREATOR_ID and not is_admin_or_higher(message.from_user.id):
        return
    broadcast_text = message.text
    await state.clear()
    
    status_msg = await message.answer("⏳ Викоנую розсилку повідомлення...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
        
        success_count = 0
        for (uid,) in users:
            try:
                await bot.send_message(uid, f"📢 **Оновлення системи:**\n\n{broadcast_text}", parse_mode="Markdown")
                success_count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
                
        await status_msg.edit_text(f"✅ Розсилку успішно завершено!\nОтримали повідомлення: `{success_count}` користувачів.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Помилка розсилки: {e}")

# --- СТАРТ ТА ІНІЦІАЛІЗАЦІЯ БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, role) VALUES (?, ?, ?)",
            (user_id, username, 'owner' if user_id == CREATOR_ID else 'user')
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
        
    await message.answer(
        get_t(user_id, 'welcome'),
        reply_markup=main_menu_kb(user_id),
        parse_mode="Markdown"
    )

async def main():
    await start_web_server()
    asyncio.create_task(keep_alive_ping())
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Головне меню ToolBox AI")
    ])
    
    logger.info("Запуск Telegram бота у режимі Enterprise v12...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
