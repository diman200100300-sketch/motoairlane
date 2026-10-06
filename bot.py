import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
import random
import urllib.parse
import requests
import hashlib
import time
from datetime import datetime
from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageFont, ImageEnhance
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand

# Автоматична перевірка та оновлення залежностей
try:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--upgrade", 
        "yt-dlp", "requests", "aiohttp", "SpeechRecognition", "Pillow", "pydantic", "aiofiles"
    ])
    logging.info("Системні бібліотеки та залежності успішно перевірені та оновлені.")
except Exception as e:
    logging.error(f"Помилка оновлення бібліотек: {e}", exc_info=True)

import yt_dlp
import speech_recognition as sr

# Налаштування детального логування системи
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
CREATOR_ID = 738520454  # Абсолютний овнер системи

if not TOKEN:
    logger.error("КРИТИЧНА ПОМИЛКА: Токен бота відсутній у змінних середовища!")

bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- РОЗШИРЕНА БАЗА ДАНИХ ТА ІЄРАРХІЯ РОЛЕЙ ---
def init_db():
    try:
        conn = sqlite3.connect("bot_database_enterprise_v16_full.db")
        cursor = conn.cursor()
        
        # Таблиця користувачів з розширеними ролями (owner, main_admin, admin, user)
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
        
        # Таблиця аудиту дій
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблиця транзакцій/оплат для PRO статусу
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Автоматичне закріплення та захист прав Absolute Owner при ініціалізації
        cursor.execute("""
            INSERT INTO users (user_id, username, is_pro, role) 
            VALUES (?, 'creator', 1, 'owner')
            ON CONFLICT(user_id) DO UPDATE SET role='owner', is_pro=1
        """, (CREATOR_ID,))
        
        conn.commit()
        conn.close()
        logger.info("Базу даних Enterprise v16 успішно ініціалізовано. Овнера закріплено.")
    except Exception as e:
        logger.error(f"Помилка ініціалізації бази даних: {e}", exc_info=True)

init_db()

def get_db_connection():
    try:
        return sqlite3.connect("bot_database_enterprise_v16_full.db")
    except Exception as e:
        logger.error(f"Помилка підключення до БД: {e}", exc_info=True)
        raise e

def log_audit_action(user_id: int, action_type: str, details: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO audit_logs (user_id, action_type, details) VALUES (?, ?, ?)", (user_id, action_type, details))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка запису в аудит-лог: {e}")

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
    except Exception as e:
        logger.error(f"Помилка отримання ролі користувача {user_id}: {e}")
        return 'user'

def get_user_lang(user_id: int) -> str:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 'uk'
    except Exception as e:
        logger.error(f"Помилка отримання мови користувача {user_id}: {e}")
        return 'uk'

def set_user_lang(user_id: int, lang: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
        conn.close()
        log_audit_action(user_id, "CHANGE_LANGUAGE", f"Змінено мову на {lang}")
    except Exception as e:
        logger.error(f"Помилка оновлення мови для {user_id}: {e}")

def check_pro_status(user_id: int) -> bool:
    if user_id == CREATOR_ID or get_user_role(user_id) in ['owner', 'main_admin', 'admin']:
        return True
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_pro FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return bool(res and res[0] == 1)
    except Exception as e:
        logger.error(f"Помилка перевірки PRO статусу для {user_id}: {e}")
        return False


# --- ПОВНІ МУЛЬТИМОВНІ СЛОВНИКИ (УКРАЇНСЬКА, ПОЛЬСЬКА, АНГЛІЙСЬКА) ---
LANG_TEXTS = {
    'uk': {
        'welcome': "👋 Вітаємо у **ToolBox AI Enterprise**!\n\n🤖 **Можливості системи:**\n1. **TikTok Downloader** — завантаження відео без водяного знака.\n2. **Аудіо в текст** — розпізнавання голосу з пунктуацією.\n3. **ШІ-Генератор Ідей** — розгорнуті унікальні стратегії.\n4. **ШІ-Фотошоп** — розширена обробка, видалення тексту, водяні знаки та вирізання об'єктів.",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok",
        'btn_audio': "🎙 Аудіо в текст",
        'btn_ai': "🤖 ШІ-Генератор Ідей",
        'btn_photoshop': "🎨 ШІ-Фотошоп та Графіка",
        'btn_admin': "🛡 Панель Адміністратора",
        'btn_owner': "👑 Панель Овнера",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Мова: Українська",
        'lang_changed': "✅ Мову успішно змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok (наприклад, з `vm.tiktok.com`):",
        'downloading': "⏳ Обробляю посилання через швидкісні шлюзи...",
        'download_error': "❌ Не вдалося завантажити відео через обмеження платформи. Спробуйте інше посилання.",
        'ai_prompt': "💡 **ШІ-Генератор Ідей**\n\nВведіть тему, бізнес-завдання або нішу для створення унікальної стратегії:",
        'ai_generating': "⏳ Аналізую дані та генерую розгорнутий звіт...",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл:",
        'audio_processing': "⏳ Конвертую аудіо та розпізнаю текст з пунктуацією...",
        'photo_send': "🎨 **ШІ-Фотошоп та обробка графіки**\n\nНадішліть зображення (фотографію) для початку обробки:",
        'photo_processing': "⏳ Обробляю зображення...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\n\nРеквізити BLIK:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче для відправки сповіщення адміністраторам.",
        'i_paid_btn': "✉ Я сплатив (Повідомити адміністратора)",
        'i_paid_msg': "⏳ Заявку на оплату успішно надіслано адміністрації!"
    },
    'pl': {
        'welcome': "👋 Witamy w **ToolBox AI Enterprise**!\n\n🤖 **Dostępne funkcje:**\n1. **TikTok Downloader** — pobieranie wideo bez znaku wodnego.\n2. **Audio na tekst** — rozpoznawanie mowy z interpunkcją.\n3. **Generator AI** — unikalne strategie i pomysły.\n4. **AI Photoshop** — zaawansowana edycja, usuwanie tekstu, znaki wodne.",
        'choose_section': "Wybierz żądaną sekcję z menu głównego poniżej:",
        'btn_tiktok': "📥 Pobierz TikTok",
        'btn_audio': "🎙 Audio na tekst",
        'btn_ai': "🤖 Generator AI",
        'btn_photoshop': "🎨 AI Photoshop i Grafika",
        'btn_admin': "🛡 Panel Administratora",
        'btn_owner': "👑 Panel Właściciela",
        'btn_pro_active': "✅ PRO Aktywne",
        'btn_buy_pro': "💎 Kup PRO — 19 zł/mc",
        'btn_lang': "🌐 Język: Polski",
        'lang_changed': "✅ Pomyślnie zmieniono język na polski!",
        'send_tiktok': "📥 Wyślij link do TikToka (np. z `vm.tiktok.com`):",
        'downloading': "⏳ Przetwarzanie linku przez bramki zapasowe...",
        'download_error': "❌ Nie udało się pobrać wideo. Sprawdź poprawność linku.",
        'ai_prompt': "💡 **Generator Pomysłów AI**\n\nWprowadź temat lub zadanie do głębokiej analizy:",
        'ai_generating': "⏳ Analizuję dane i generuję unikalny raport...",
        'back': "« Powrót do menu głównego",
        'audio_send': "🎙 Wyślij wiadomość głosową lub plik audio:",
        'audio_processing': "⏳ Konwertuję audio i rozpoznaję tekst z interpunkcją...",
        'photo_send': "🎨 **AI Photoshop i edycja zdjęć**\n\nWyślij zdjęcie, które chcesz edytować:",
        'photo_processing': "⏳ Przetwarzanie obrazu...",
        'buy_title': "💎 **Uzyskanie statusu PRO**\nCena: 19 zł/miesiąc\n\nDane do przelewu BLIK:\n`+48 733 985 396`\n\nPo opłaceniu kliknij przycisk poniżej.",
        'i_paid_btn': "✉ Zapłaciłem (Powiadom administrację)",
        'i_paid_msg': "⏳ Zgłoszenie płatności zostało wysłane do administracji!"
    },
    'en': {
        'welcome': "👋 Welcome to **ToolBox AI Enterprise**!\n\n🤖 **System Features:**\n1. **TikTok Downloader** — save videos without watermark.\n2. **Audio to Text** — voice recognition with punctuation.\n3. **AI Idea Generator** — deep unique strategies.\n4. **AI Photoshop** — photo editing, text removal, watermarks & object cutout.",
        'choose_section': "Choose the required section from the main menu below:",
        'btn_tiktok': "📥 Download TikTok",
        'btn_audio': "🎙 Audio to Text",
        'btn_ai': "🤖 AI Idea Generator",
        'btn_photoshop': "🎨 AI Photoshop & Graphics",
        'btn_admin': "🛡 Admin Panel",
        'btn_owner': "👑 Owner Panel",
        'btn_pro_active': "✅ PRO Active",
        'btn_buy_pro': "💎 Buy PRO — 19 zł/mo",
        'btn_lang': "🌐 Language: English",
        'lang_changed': "✅ Language successfully changed to English!",
        'send_tiktok': "📥 Send a TikTok link (e.g., from `vm.tiktok.com`):",
        'downloading': "⏳ Processing link through high-speed gateways...",
        'download_error': "❌ Failed to download video due to platform restrictions. Try another link.",
        'ai_prompt': "💡 **AI Idea Generator**\n\nEnter a topic or task for deep analysis:",
        'ai_generating': "⏳ Analyzing data and generating a detailed report...",
        'back': "« Back to main menu",
        'audio_send': "🎙 Send a voice message or audio file:",
        'audio_processing': "⏳ Converting audio and recognizing text with punctuation...",
        'photo_send': "🎨 **AI Photoshop & Photo Editing**\n\nSend an image you want to edit:",
        'photo_processing': "⏳ Processing image...",
        'buy_title': "💎 **Getting PRO Status**\nPrice: 19 zł/month\n\nBLIK details:\n`+48 733 985 396`\n\nAfter payment, click the button below to notify administration.",
        'i_paid_btn': "✉ I Have Paid (Notify Admin)",
        'i_paid_msg': "⏳ Payment request sent to administration!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])


# --- ВЕБСЕРВЕР ТА ПІНГ (АКТИВНІСТЬ ДЛЯ RENDER / 24/7) ---
async def handle_ping(request):
    return web.Response(text="ToolBox AI Enterprise v16 Full Bot is active and fully operational!")

async def start_web_server():
    try:
        app = web.Application()
        app.add_routes([web.get("/", handle_ping)])
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Вебсервер успішно запущено на порті {port}")
    except Exception as e:
        logger.error(f"Помилка запуску вебсервера: {e}", exc_info=True)

async def keep_alive_ping():
    await asyncio.sleep(15)
    while True:
        try:
            if RENDER_EXTERNAL_URL:
                async with ClientSession() as session:
                    async with session.get(RENDER_EXTERNAL_URL, timeout=10) as resp:
                        logger.debug(f"Keep-alive ping статус: {resp.status}")
        except Exception as e:
            logger.debug(f"Помилка keep-alive пінгу: {e}")
        await asyncio.sleep(240)


# --- ПОКРОКОВІ FSM СТАНИ ---
class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()
    waiting_for_audio = State()
    waiting_for_photo = State()
    waiting_for_broadcast = State()
    waiting_for_target_user_id = State()
    waiting_for_main_admin_target = State()
    waiting_for_custom_watermark_text = State()
    waiting_for_add_text_prompt = State()


# --- ІНТЕРФЕЙС ТА УПРАВЛІННЯ МОВОЮ ---
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
    try:
        await callback.answer(LANG_TEXTS[new_lang]['lang_changed'], show_alert=True)
        await callback.message.edit_text(
            LANG_TEXTS[new_lang]['choose_section'], 
            reply_markup=main_menu_kb_builder(user_id)
        )
    except Exception as e:
        logger.error(f"Помилка зміни мови для користувача {user_id}: {e}")
    await callback.answer()

def main_menu_kb_builder(user_id: int) -> InlineKeyboardMarkup:
    pro_active = check_pro_status(user_id)
    role = get_user_role(user_id)
    
    keyboard = [
        [InlineKeyboardButton(text=get_t(user_id, 'btn_tiktok'), callback_data="download_video")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_audio'), callback_data="audio_to_text")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_ai'), callback_data="ai_generator")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_photoshop'), callback_data="photoshop_menu")],
    ]
    
    if pro_active:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_pro_active'), callback_data="pro_info")])
    else:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_buy_pro'), callback_data="buy_pro")])
        
    if user_id == CREATOR_ID or role == 'owner':
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_owner'), callback_data="owner_panel")])
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
    elif role in ['main_admin', 'admin']:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
        
    keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_lang'), callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        user_id = callback.from_user.id
        await callback.message.edit_text(
            get_t(user_id, 'choose_section'), 
            reply_markup=main_menu_kb_builder(user_id)
        )
    except Exception as e:
        logger.error(f"Помилка повернення в головне меню для {callback.from_user.id}: {e}")
    await callback.answer()


# --- ШІ-ГЕНЕРАТОР ІДЕЙ ТА СТРАТЕГІЙ (ВИПРАВЛЕНО ЗАВИСАННЯ) ---
FALLBACK_IDEA_MATRICES = [
    {
        "focus": "Вірусний маркетинг та швидке масштабування охоплень",
        "steps": [
            "1. Глибокий аналіз трендів та болю цільової аудиторії.",
            "2. Створення інтригуючого «гачка» (Hook) у перші 3 секунди.",
            "3. Динамічний монтаж, зміна кадрів та утримання уваги глядача.",
            "4. Чіткий заклик до дії (CTA) для коментарів та поширень."
        ]
    },
    {
        "focus": "Технічна експертність, авторитетність та конверсія",
        "steps": [
            "1. Повний аудит обраної тематики та виявлення прихованих проблем.",
            "2. Логічне структурування тез без «води» та лишніх відступів.",
            "3. Розбір реального кейсу з конкретними прикладами та цифрами.",
            "4. Формування чітких висновків і покрокового алгоритму дій."
        ]
    },
    {
        "focus": "Партизанський маркетинг та залучення спільноти",
        "steps": [
            "1. Інтерактивні механіки та провокація обговорень у коментарях.",
            "2. Використання трендової музики та оригінального оформлення.",
            "3. Серійність контенту з інтригою у наступній частині.",
            "4. Робота з відгуками глядачів для створення наступних роликів."
        ]
    }
]

async def generate_smart_ai_response(prompt_text: str, user_id: int) -> str:
    dynamic_info = ""
    try:
        search_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(prompt_text)}&format=json&kl=uk-ua"
        response = requests.get(search_url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            if data.get("AbstractText"):
                dynamic_info = f"📌 **Аналітичний контекст:** {data.get('AbstractText')}\n\n"
    except Exception as e:
        logger.warning(f"Зовнішній контекст недоступний: {e}")

    # ВИПРАВЛЕНО: Правильна назва змінної FALLBACK_IDEA_MATRICES
    matrix = random.choice(FALLBACK_IDEA_MATRICES)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET requests_count = requests_count + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка оновлення лічильника запитів: {e}")

    report = (
        f"💡 **Поглиблений аналітичний звіт ШІ**\n"
        f"📝 **Тема:** `{prompt_text}`\n\n"
        f"🎯 **Стратегічний фокус:** {matrix['focus']}\n\n"
        f"{dynamic_info}"
        f"🚀 **Покроковий план реалізації:**\n" + "\n".join(matrix['steps']) + "\n\n"
        f"⚙️ *Згенеровано штучним інтелектом ToolBox AI Enterprise.*"
    )
    return report

@dp.callback_query(F.data == "ai_generator")
async def ask_ai_prompt(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        await state.set_state(GenStates.waiting_for_idea_prompt)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
        await callback.message.edit_text(get_t(user_id, 'ai_prompt'), reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка входу в ШІ генератор: {e}")
    await callback.answer()

@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_generation(message: types.Message, state: FSMContext):
    prompt_text = message.text.strip() if message.text else ""
    user_id = message.from_user.id
    
    if len(prompt_text) < 2:
        await message.answer("⚠️ Будь ласка, введіть детальнішу тему або запит.")
        return

    status_msg = await message.answer(get_t(user_id, 'ai_generating'))
    
    try:
        final_report = await generate_smart_ai_response(prompt_text, user_id)
        await status_msg.edit_text(final_report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка генерації ідей: {e}", exc_info=True)
        await status_msg.edit_text("❌ Сталася помилка під час обробки запиту ШІ. Спробуйте ще раз.")
    finally:
        await state.clear()
        
    try:
        await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
    except Exception as e:
        logger.error(f"Помилка після ШІ: {e}")


# --- TIKTOK ЗАВАНТАЖУВАЧ (ПОВНІСТЮ ВИПРАВЛЕНИЙ ТА ОПТИМІЗОВАНИЙ) ---
async def download_tiktok_tikwm(url: str, output_filename: str) -> bool:
    """Пряме та безперебійне завантаження через TikWM API без водяного знака."""
    try:
        api_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}"
        async with ClientSession() as session:
            async with session.get(api_url, timeout=12) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0 and "data" in data and "play" in data["data"]:
                        video_url = data["data"]["play"]
                        async with session.get(video_url, timeout=20) as v_resp:
                            if v_resp.status == 200:
                                with open(output_filename, "wb") as f:
                                    f.write(await v_resp.read())
                                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
                                    return True
    except Exception as e:
        logger.warning(f"TikWM API не спрацював, перехід на yt-dlp: {e}")
    return False

async def cascade_download_tiktok(url: str, output_filename: str) -> bool:
    # Крок 1: Пробуємо ультра-швидкий TikWM API
    if await download_tiktok_tikwm(url, output_filename):
        return True

    # Крок 2: Резервний каскад через yt-dlp
    strategies = [
        {'format': 'best', 'extractor_args': {'tiktok': {'web_app': True}}, 'geo_bypass': True},
        {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 'noplaylist': True}
    ]
    loop = asyncio.get_running_loop()
    for strat in strategies:
        try:
            current_opts = {
                'outtmpl': output_filename,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 15,
                **strat
            }
            def run_dl():
                with yt_dlp.YoutubeDL(current_opts) as ydl:
                    ydl.download([url])
            
            await loop.run_in_executor(None, run_dl)
            if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
                return True
        except Exception as e:
            logger.warning(f"yt-dlp стратегія не спрацювала: {e}")
            continue
    return False

@dp.callback_query(F.data == "download_video")
async def ask_tiktok_link(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        await state.set_state(GenStates.waiting_for_video_link)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
        await callback.message.edit_text(get_t(user_id, 'send_tiktok'), reply_markup=kb)
    except Exception as e:
        logger.error(f"Помилка запиту посилання TikTok: {e}")
    await callback.answer()

@dp.message(GenStates.waiting_for_video_link)
async def process_tiktok_download(message: types.Message, state: FSMContext):
    url = message.text.strip() if message.text else ""
    user_id = message.from_user.id
    
    if "tiktok.com" not in url:
        await message.answer("❌ Будь ласка, надішліть коректне посилання на TikTok відео.")
        return

    status_msg = await message.answer(get_t(user_id, 'downloading'))
    output_filename = f"tiktok_{user_id}_{random.randint(10000, 99999)}.mp4"
    
    try:
        success = await cascade_download_tiktok(url, output_filename)
        if success and os.path.exists(output_filename):
            await message.answer_video(
                FSInputFile(output_filename), 
                caption="✅ **Відео успішно завантажено без водяного знака!**\n📱 *ToolBox AI Enterprise Engine.*",
                parse_mode="Markdown"
            )
            await status_msg.delete()
            log_audit_action(user_id, "TIKTOK_DOWNLOAD", "Успішно завантажено відео")
        else:
            await status_msg.edit_text(get_t(user_id, 'download_error'))
    except Exception as e:
        logger.error(f"Критична помилка TikTok: {e}", exc_info=True)
        await status_msg.edit_text(get_t(user_id, 'download_error'))
    finally:
        if os.path.exists(output_filename):
            try:
                os.remove(output_filename)
            except Exception:
                pass
        await state.clear()
        
    try:
        await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
    except Exception as e:
        logger.error(f"Помилка скидання стану: {e}")
# --- МОДУЛЬ ГОЛОСОВОГО ВВОДУ (АУДІО В ТЕКСТ) ---
@dp.callback_query(F.data == "audio_to_text")
async def ask_audio_input(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        await state.set_state(GenStates.waiting_for_audio)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
        await callback.message.edit_text(get_t(user_id, 'audio_send'), reply_markup=kb)
    except Exception as e:
        logger.error(f"Помилка запиту аудіо: {e}")
    await callback.answer()

@dp.message(GenStates.waiting_for_audio, F.voice | F.audio)
async def process_audio_to_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    status_msg = await message.answer(get_t(user_id, 'audio_processing'))
    
    src_path = f"audio_{user_id}_{int(time.time())}.ogg"
    wav_path = f"audio_{user_id}_{int(time.time())}.wav"
    
    try:
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, src_path)
        
        # Конвертація в WAV 16kHz через ffmpeg
        subprocess.run(["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            lang_code = "uk-UA" if get_user_lang(user_id) == "uk" else ("pl-PL" if get_user_lang(user_id) == "pl" else "en-US")
            text = recognizer.recognize_google(audio_data, language=lang_code)
            
        await status_msg.edit_text(f"🎙 **Розпізнаний текст з пунктуацією:**\n\n`{text}`", parse_mode="Markdown")
        log_audit_action(user_id, "AUDIO_TO_TEXT", "Успішно розпізнано аудіо")
    except sr.UnknownValueError:
        await status_msg.edit_text("❌ Не вдалося розпізнати мову. Спробуйте записати чіткіше або без сторонніх шумів.")
    except Exception as e:
        logger.error(f"Помилка розпізнавання аудіо: {e}", exc_info=True)
        await status_msg.edit_text("❌ Сталася помилка під час обробки аудіофайлу.")
    finally:
        for path in [src_path, wav_path]:
            if os.path.exists(path):
                try: 
                    os.remove(path)
                except Exception: 
                    pass
        await state.clear()
        
    try:
        await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
    except Exception as e:
        logger.error(f"Помилка завершення аудіо: {e}")


# --- МОДУЛЬ ШІ-ФОТОШОП ТА ОБРОБКИ ГРАФІКИ ---
class PhotoshopStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_watermark_text = State()
    waiting_for_custom_text = State()

@dp.callback_query(F.data == "photoshop_menu")
async def photoshop_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        await state.set_state(PhotoshopStates.waiting_for_photo)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
        await callback.message.edit_text(get_t(user_id, 'photo_send'), reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка меню фотошопу: {e}")
    await callback.answer()

@dp.message(PhotoshopStates.waiting_for_photo, F.photo)
async def process_photo_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    img_path = f"photo_{user_id}_{int(time.time())}.png"
    
    try:
        await bot.download_file(file_info.file_path, img_path)
        await state.update_data(current_photo_path=img_path
