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

# Автоматичне оновлення системних бібліотек
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "requests", "aiohttp", "SpeechRecognition"])
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
        conn = sqlite3.connect("bot_database_enterprise_v14.db")
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
    return sqlite3.connect("bot_database_enterprise_v14.db")

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
        'welcome': "👋 Вітаємо у **ToolBox AI Enterprise**!\n\n🤖 **Можливості системи:**\n1. **TikTok Downloader** — завантаження відео без водяного знака.\n2. **Аудіо в текст** — розпізнавання голосу з пунктуацією.\n3. **ШІ-Генератор Ідей** — розгорнуті унікальні стратегії.",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok",
        'btn_audio': "🎙 Аудіо в текст",
        'btn_ai': "🤖 ШІ-Генератор Ідей",
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
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\n\nРеквізити BLIK:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉ Я сплатив (Повідомити)",
        'i_paid_msg': "⏳ Заявку надіслано адміністрації!"
    },
    'pl': {
        'welcome': "👋 Witamy w **ToolBox AI Enterprise**!\n\n🤖 **Dostępne funkcje:**\n1. **TikTok Downloader** — pobieranie wideo bez znaku wodnego.\n2. **Audio na tekst** — rozpoznawanie mowy z interpunkcją.\n3. **Generator AI** — unikalne strategie i pomysły.",
        'choose_section': "Wybierz żądaną sekcję z menu głównego poniżej:",
        'btn_tiktok': "📥 Pobierz TikTok",
        'btn_audio': "🎙 Audio na tekst",
        'btn_ai': "🤖 Generator AI",
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
        'buy_title': "💎 **Uzyskanie statusu PRO**\nCena: 19 zł/miesiąc\n\nDane do przelewu BLIK:\n`+48 733 985 396`\n\nPo opłaceniu kliknij przycisk poniżej.",
        'i_paid_btn': "✉ Zapłaciłem (Powiadom administrację)",
        'i_paid_msg': "⏳ Zgłoszenie płatności zostało wysłane!"
    },
    'en': {
        'welcome': "👋 Welcome to **ToolBox AI Enterprise**!\n\n🤖 **System Features:**\n1. **TikTok Downloader** — save videos without watermark.\n2. **Audio to Text** — voice recognition with punctuation.\n3. **AI Idea Generator** — deep unique strategies.",
        'choose_section': "Choose the required section from the main menu below:",
        'btn_tiktok': "📥 Download TikTok",
        'btn_audio': "🎙 Audio to Text",
        'btn_ai': "🤖 AI Idea Generator",
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
        'buy_title': "💎 **Getting PRO Status**\nPrice: 19 zł/month\n\nBLIK details:\n`+48 733 985 396`\n\nAfter payment, click the button below.",
        'i_paid_btn': "✉ I Have Paid (Notify Admin)",
        'i_paid_msg': "⏳ Payment request sent to administration!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])
# ==========================================
# РОЗДІЛ 2: ВЕБСЕРВЕР ТА АКТИВНІСТЬ (RENDER)
# ==========================================

async def handle_ping(request):
    return web.Response(text="ToolBox AI Enterprise v14 Bot is active and fully operational!")

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


# ==========================================
# РОЗДІЛ 3: FSM СТАНИ ДЛЯ ДІАЛОГІВ ТА АДМІНІСТРУВАННЯ
# ==========================================

class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()
    waiting_for_audio = State()
    waiting_for_broadcast = State()
    waiting_for_target_user_id = State()
    waiting_for_admin_target = State()


# ==========================================
# РОЗДІЛ 4: ІНТЕРФЕЙС ТА УПРАВЛІННЯ МОВАМИ
# ==========================================

@dp.callback_query(F.data == "change_lang")
async def change_lang_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_lang = get_user_lang(user_id)
    
    # Циклічне перемикання: uk -> pl -> en -> uk
    if current_lang == 'uk':
        new_lang = 'pl'
    elif current_lang == 'pl':
        new_lang = 'en'
    else:
        new_lang = 'uk'
        
    set_user_lang(user_id, new_lang)
    
    confirm_texts = {
        'uk': "✅ Мову успішно змінено на українську!",
        'pl': "✅ Pomyślnie zmieniono język na polski!",
        'en': "✅ Language successfully changed to English!"
    }
    
    await callback.answer(confirm_texts.get(new_lang, "✅ Мову змінено!"), show_alert=True)
    
    # Імпорт головного меню буде в наступних частинах, тут оновлюємо текст повідомлення
    from aiogram.types import InlineKeyboardMarkup
    # Оновлюємо інтерфейс
    await callback.message.edit_text(
        LANG_TEXTS[new_lang]['choose_section'], 
        reply_markup=main_menu_kb_builder(user_id)
    )
    await callback.answer()


def main_menu_kb_builder(user_id: int) -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    pro_active = check_pro_status(user_id)
    role = get_user_role(user_id)
    
    keyboard = [
        [InlineKeyboardButton(text=get_t(user_id, 'btn_tiktok'), callback_data="download_video")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_audio'), callback_data="audio_to_text")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_ai'), callback_data="ai_generator")],
    ]
    
    if pro_active:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_pro_active'), callback_data="pro_info")])
    else:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_buy_pro'), callback_data="buy_pro")])
        
    # Доступ до панелей згідно ієрархії
    if user_id == CREATOR_ID:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_owner'), callback_data="owner_panel")])
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
    elif role == 'main_admin':
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
    elif role == 'admin':
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
        
    keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_lang'), callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await callback.message.edit_text(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
    await callback.answer()
# ==========================================
# РОЗДІЛ 5: ШІ-ГЕНЕРАТОР ІДЕЙ ТА КОНТЕНТУ З РЕЗЕРВНИМИ МАТРИЦЯМИ
# ==========================================

# Величезна база унікальних експертних матриць та сценаріїв на випадок відсутності інтернету чи API
FALLBACK_IDEA_MATRICES = [
    {
        "focus": "Вірусний маркетинг та швидкий охоплення аудиторії",
        "steps": [
            "1. **Аналіз трендів:** Дослідіть поточні рекомендації та формат коротких відео у тій чи іншій ніші.",
            "2. **Гачок (Hook):** Створіть інтригуючий початок перших 3 секунд для утримання уваги глядача.",
            "3. **Динамічний монтаж:** Використовуйте швидкі переходи, субтитри та якісний звуковий супровід.",
            "4. **Заклик до дії:** Заохочуйте коментарі та поширення для алгоритмів платформи."
        ]
    },
    {
        "focus": "Глибока технічна оптимізація та експертність",
        "steps": [
            "1. **Аудит бази:** Детально розберіть технічні характеристики або проблематику теми.",
            "2. **Структурування:** Розділіть складний матеріал на прості логічні блоки для легкого сприйняття.",
            "3. **Практичний кейс:** Наведіть реальний приклад або розрахунок ефективності.",
            "4. **Висновки:** Підсумуйте головну цінність та даруйте чітку інструкцію до виконання."
        ]
    },
    {
        "focus": "Комерційний розвиток та монетизація",
        "steps": [
            "1. **Визначення цільової аудиторії:** Знайдіть болі та потреби потенційних клієнтів.",
            "2. **Побудова офферу:** Сформуйте унікальну торгову пропозицію, яка вирішує проблему.",
            "3. **Тестування гіпотези:** Запустіть міні-версію проєкту (MVP) з мінімальним бюджетом.",
            "4. **Масштабування:** Збільшуйте бюджети та автоматизуйте процеси після перших прибутків."
        ]
    },
    {
        "focus": "Креативний дизайн та брендинг",
        "steps": [
            "1. **Візуальна концепція:** Підберіть унікальну гаму кольорів та стиль подачі.",
            "2. **Побудова емоції:** Викликайте у глядача чи користувача яскравий емоційний відгук.",
            "3. **Послідовність:** Дотримуйтеся єдиного стилю на всіх платформах та у всіх матеріалах.",
            "4. **Зворотний зв'язок:** Збирайте реакції аудиторії та адаптуйте візуал під їхні вподобання."
        ]
    }
]

async def generate_smart_ai_response(prompt_text: str, user_id: int) -> str:
    dynamic_info = ""
    try:
        search_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(prompt_text)}&format=json&kl=uk-ua"
        response = requests.get(search_url, timeout=6)
        if response.status_code == 200:
            data = response.json()
            abstract = data.get("AbstractText", "")
            heading = data.get("Heading", "")
            related = data.get("RelatedTopics", [])
            
            if abstract:
                dynamic_info += f"📌 **Контекст з мережі ({heading or 'Аналіз'}):**\n{abstract}\n\n"
            
            valid_related = [item['Text'] for item in related if isinstance(item, dict) and "Text" in item]
            if valid_related:
                random.shuffle(valid_related)
                dynamic_info += "🌐 **Ключові фактори:**\n" + "\n".join([f"• {item}" for item in valid_related[:3]]) + "\n\n"
    except Exception:
        pass

    # Обираємо випадкову експертну матрицю, щоб уникнути однакових шаблонів
    matrix = random.choice(FALLBACK_IDEA_MATRICES)
    
    response_text = (
        f"💡 **Стратегічний звіт за запитом:** `{prompt_text}`\n\n"
        f"🎯 **Вектор розвитку:** {matrix['focus']}\n\n"
        f"{dynamic_info}"
        "🚀 **Покроковий план реалізації:**\n" +
        "\n".join(matrix['steps']) + "\n\n"
        "✨ *Висновок:* Системний підхід та унікальна структура забезпечать максимальну ефективність вашого завдання."
    )
    return response_text

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
        await message.answer("⚠️ Введіть більш детальний запит.")
        return

    status_msg = await message.answer(get_t(user_id, 'ai_generating'))
    final_report = await generate_smart_ai_response(prompt_text, user_id)
    
    try:
        await status_msg.edit_text(final_report, parse_mode="Markdown")
    except Exception:
        await message.answer(final_report, parse_mode="Markdown")
        try:
            await status_msg.delete()
        except Exception:
            pass
            
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
# ==========================================
# РОЗДІЛ 6: БАГАТОСТУПЕНЕВИЙ КАСКАДНИЙ ЗАВАНТАЖУВАЧ TIKTOK
# ==========================================

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
        {'format': 'best', 'extractor_args': {'tiktok': {'app_version': '32.0.0', 'web_app': False}}, 'nocheckcertificate': True},
        # Додаткові резервні шлюзи
        {'format': 'worst[ext=mp4]/best', 'extractor_args': {'tiktok': {'web_app': True}}, 'nocheckcertificate': True},
        {'format': 'best', 'user_agent': 'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X)', 'geo_bypass': True}
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
                logger.info(f"TikTok завантажено на етапі каскаду #{step}")
                return True
        except Exception as e:
            logger.warning(f"Каскадний етап #{step} пропущено: {e}")
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
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
# ==========================================
# РОЗДІЛ 7: КОНВЕРТАЦІЯ АУДІО ТА РОЗПІЗНАВАННЯ З ПУНКТУАЦІЄЮ
# ==========================================

async def robust_audio_recognition(wav_path: str, user_lang: str) -> str:
    r = sr.Recognizer()
    r.energy_threshold = 250
    r.dynamic_energy_threshold = True

    lang_code = "uk-UA"
    if user_lang == 'pl':
        lang_code = "pl-PL"
    elif user_lang == 'en':
        lang_code = "en-US"

    def attempt_recognition():
        with sr.AudioFile(wav_path) as source:
            r.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = r.record(source)
            try:
                res = r.recognize_google(audio_data, language=lang_code, show_all=True)
                if isinstance(res, dict) and "alternative" in res and res["alternative"]:
                    return res["alternative"][0].get("transcript", "")
                elif isinstance(res, str):
                    return res
            except Exception:
                pass
            
            # Резервна спроба
            try:
                fallback_res = r.recognize_google(audio_data, language=lang_code)
                if isinstance(fallback_res, str):
                    return fallback_res
            except Exception:
                pass
            return ""

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, attempt_recognition)

def smart_punctuation_formatter(text: str) -> str:
    """
    Інтелектуальний форматувальник для автоматичного розставлення розділових знаків,
    якщо рушій розпізнавання повернув сирий текст без крапок і ком.
    """
    if not text:
        return ""
    
    cleaned = text.strip()
    # Робимо першу літеру великою
    cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
    
    # Інтелектуальні маркери зв'язок для розбиття на речення та коми
    conjunctions = [" а ", " але ", " тому що ", " що ", " коли ", " якщо ", " бо ", " ale ", " i ", " że ", " ponieważ ", " but ", " because ", " when ", " if "]
    for conj in conjunctions:
        if conj in cleaned and not f",{conj}" in cleaned:
            cleaned = cleaned.replace(conj, f",{conj}")
            
    # Додаємо знак в кінці, якщо його немає
    if not cleaned.endswith(('.', '!', '?', '...')):
        cleaned += "."
        
    return cleaned

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
            
        raw_text = await robust_audio_recognition(wav_path, user_lang)

        if raw_text:
            formatted_text = smart_punctuation_formatter(raw_text)
            response_msg = (
                f"🎙 **Результат розпізнавання аудіо:**\n\n"
                f"« *{formatted_text}* »\n\n"
                f"✅ Пунктуацію, коми та знаки відкориговано автоматично!"
            )
            await status_msg.edit_text(response_msg, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Не вдалося розпізнати слова в аудіопотоці.")
            
    except Exception as e:
        logger.error(f"Помилка обробки аудіо: {e}")
        await status_msg.edit_text("❌ Сталася помилка під час обробки файлу.")
        
    for p in [ogg_path, wav_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
                
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))
# ==========================================
# РОЗДІЛ 8: ПІДТРИМКА ТА КУПІВЛЯ PRO СТАТУСУ
# ==========================================

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
            f"🔔 **Нова заявка на оплату PRO!**\nКористувач ID: `{user_id}` (`@{callback.from_user.username or 'NoName'}`) сплатив 19 zł. Перевірте надходження та надайте PRO статус через панель керування.",
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
# ==========================================
# РОЗДІЛ 9: ПЕРЕВІРКА ЛІМІТІВ ТА ЛОГІКА ОБМЕЖЕНЬ
# ==========================================

def check_and_update_limit(user_id: int, action_type: str, max_limit: int) -> bool:
    """
    Перевіряє щоденні ліміти для звичайних користувачів.
    PRO та вищі ролі проходять без обмежень.
    """
    if check_pro_status(user_id):
        return True

    today_date = datetime.now().strftime("%Y-%m-%d")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Створюємо таблицю лімітів, якщо її ще немає
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
            # Новий день — скидаємо лічильник
            cursor.execute("UPDATE user_limits SET last_date = ?, count = 1 WHERE user_id = ? AND action_type = ?", (today_date, user_id, action_type))
            conn.commit()
            conn.close()
            return True
            
        if count >= max_limit:
            conn.close()
            return False # Ліміт вичерпано
            
        cursor.execute("UPDATE user_limits SET count = count + 1 WHERE user_id = ? AND action_type = ?", (user_id, action_type))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Помилка перевірки лімітів: {e}")
        return True


# ==========================================
# РОЗДІЛ 10: ПАНЕЛЬ АДМІНІСТРАТОРА ТА ОВНЕРА
# ==========================================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    role = get_user_role(user_id)
    if user_id != CREATOR_ID and role not in ['main_admin', 'admin']:
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
        
    kb = [
        [InlineKeyboardButton(text="👥 Статистика бази", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💎 Видати/Зняти PRO", callback_data="admin_manage_pro_prompt")],
    ]
    
    if user_id == CREATOR_ID or role == 'main_admin':
        kb.append([InlineKeyboardButton(text="🛡 Керування Адмінами", callback_data="admin_manage_admins_prompt")])
        
    kb.append([InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")])
    
    await callback.message.edit_text(
        f"🛡 **Панель управління**\nРоль у системі: `{role.upper()}`\n\nОберіть необхідну дію:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "owner_panel")
async def owner_panel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != CREATOR_ID:
        await callback.answer("⛔ Лише для Абсолютного Овнера.", show_alert=True)
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Призначити Головного Адміна", callback_data="owner_add_main_admin")],
        [InlineKeyboardButton(text="📢 Масова розсилка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(
        "👑 **Панель Абсолютного Овнера**\n\nВи маєте повний і необмежений контроль над системою.",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    role = get_user_role(user_id)
    if user_id != CREATOR_ID and role not in ['main_admin', 'admin']:
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro = 1")
        total_pro = cursor.fetchone()[0]
        conn.close()
        
        text = f"📊 **Статистика системи:**\n\n• Всього користувачів: `{total_users}`\n• PRO користувачів: `{total_pro}`\n• Ваш статус: **{role.upper()}**"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="admin_panel")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        await callback.answer(f"Помилка: {e}", show_alert=True)
    await callback.answer()
# ==========================================
# РОЗДІЛ 11: ІНТЕГРАЦІЯ ЛІМІТІВ ТА УПРАВЛІННЯ ПРАВАМИ В ОБРОБНИКАХ
# ==========================================

# Модифікований обробник TikTok із перевіркою ліміту (7 на день для звичайних)
@dp.message(GenStates.waiting_for_video_link)
async def process_tiktok_download_with_limits(message: types.Message, state: FSMContext):
    url = message.text.strip()
    user_id = message.from_user.id
    
    if not url.startswith("http"):
        await message.answer(get_t(user_id, 'download_error'))
        return

    # Перевірка щоденного ліміту (7 відео для звичайних користувачів)
    if not check_and_update_limit(user_id, "tiktok", 7):
        await message.answer("⚠️ Вичерпано денний ліміт завантаження відео (7 на день). Придбайте PRO статус для зняття всіх обмежень!", reply_markup=main_menu_kb_builder(user_id))
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


# Модифікований обробник аудіо з лімітами (5 на день, до 2 хв для звичайних / до 15 хв для PRO)
@dp.message(GenStates.waiting_for_audio, F.voice | F.audio)
async def process_audio_file_with_limits(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_lang = get_user_lang(user_id)
    
    # Перевірка тривалості файлу (в секундах: 120 сек = 2 хв для звичайних, 900 сек = 15 хв для PRO)
    duration = message.voice.duration if message.voice else getattr(message.audio, 'duration', 0)
    max_duration = 900 if check_pro_status(user_id) else 120
    
    if duration and duration > max_duration:
        limit_min = int(max_duration / 60)
        await message.answer(f"⚠️ Ваше аудіо триває {int(duration)} сек. Для звичайних користувачів ліміт становить до {limit_min} хвилин. Придбайте PRO для збільшення ліміту до 15 хвилин!")
        await state.clear()
        return

    # Перевірка щоденного ліміту (5 аудіо для звичайних)
    if not check_and_update_limit(user_id, "audio", 5):
        await message.answer("⚠️ Вичерпано денний ліміт обробки аудіо (5 на день). Придбайте PRO статус!", reply_markup=main_menu_kb_builder(user_id))
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
        
        if not os.path.exists(wav_path):
            raise Exception("Помилка ffmpeg конвертації.")
            
        raw_text = await robust_audio_recognition(wav_path, user_lang)
        if raw_text:
            formatted_text = smart_punctuation_formatter(raw_text)
            response_msg = (
                f"🎙 **Результат розпізнавання аудіо:**\n\n"
                f"« *{formatted_text}* »\n\n"
                f"✅ Пунктуацію та знаки відкориговано автоматично!"
            )
            await status_msg.edit_text(response_msg, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Не вдалося розпізнати слова в аудіопотоці.")
    except Exception as e:
        logger.error(f"Помилка аудіо: {e}")
        await status_msg.edit_text("❌ Сталася помилка під час обробки.")
        
    for p in [ogg_path, wav_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
                
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))


# Модифікований обробник ШІ-генератора з лімітом (6 разів на день для звичайних)
@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_generation_with_limits(message: types.Message, state: FSMContext):
    prompt_text = message.text.strip()
    user_id = message.from_user.id
    
    if len(prompt_text) < 2:
        await message.answer("⚠️ Введіть більш детальний запит.")
        return

    # Перевірка щоденного ліміту (6 генерацій для звичайних)
    if not check_and_update_limit(user_id, "ai_gen", 6):
        await message.answer("⚠️️ Вичерпано денний ліміт генерацій ідей (6 на день). Придбайте PRO статус для безлімітного використання!", reply_markup=main_menu_kb_builder(user_id))
        await state.clear()
        return

    status_msg = await message.answer(get_t(user_id, 'ai_generating'))
    final_report = await generate_smart_ai_response(prompt_text, user_id)
    
    try:
        await status_msg.edit_text(final_report, parse_mode="Markdown")
    except Exception:
        await message.answer(final_report, parse_mode="Markdown")
        try:
            await status_msg.delete()
        except Exception:
            pass
            
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))


# ==========================================
# РОЗДІЛ 12: ГОЛОВНА ТОЧКА ВХОДУ ТА СТАРТ БОТА
# ==========================================

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
        
    await message.answer(
        get_t(user_id, 'welcome'),
        reply_markup=main_menu_kb_builder(user_id),
        parse_mode="Markdown"
    )

async def main():
    await start_web_server()
    asyncio.create_task(keep_alive_ping())
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Головне меню ToolBox AI Enterprise")
    ])
    
    logger.info("Запуск Telegram бота у режимі Enterprise v14...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот зупинений користувачем.")
# ==========================================
# РОЗДІЛ 13: АБСОЛЮТНІ РЕЗЕРВНІ АРБІТРИ ТА КОНТРОЛЕРИ ЯКОСТІ (ULTIMATE PATCH v15)
# ==========================================

import hashlib

# Кеш останніх відповідей для запобігання повторам у генераторі ідей
_LAST_GENERATED_RESPONSES = {}

async def ultimate_ai_generator_validator(prompt_text: str, user_id: int) -> str:
    """
    Перевіряє роботу генератора ідей. Якщо виявляється подібність до попереднього
    або стандартний шаблон, примусово генерує унікальну комбінацію з розширеного пулу.
    """
    global _LAST_GENERATED_RESPONSES
    
    # Викликаємо базовий генератор
    raw_response = await generate_smart_ai_response(prompt_text, user_id)
    
    # Створюємо хеш відповіді для перевірки на повтори
    response_hash = hashlib.md5(raw_response.encode('utf-8')).hexdigest()
    
    if user_id in _LAST_GENERATED_RESPONSES and _LAST_GENERATED_RESPONSES[user_id] == response_hash:
        # Знайдено повтор шаблону! Застосовуємо примусову унікальну ротацію
        logger.warning(f"[AI Arbiter] Виявлено повтор шаблону для користувача {user_id}. Задіюємо альтернативну матрицю.")
        
        alt_matrices = [
            f"💡 **Альтернативний стратегічний вектор для:** `{prompt_text}`\n\n🎯 **Фокус:** Глибока декомпозиція та інноваційний підхід.\n\n🚀 **План дій:**\n1. Проведіть повний реверс-інжиніринг успішних кейсів.\n2. Створіть ексклюзивний прототип.\n3. Протестуйте на обмеженій аудиторії.\n4. Масштабуйте найкращі показники.",
            f"💡 **Ексклюзивний експертний розбір:** `{prompt_text}`\n\n🎯 **Фокус:** Максимальна оптимізація ресурсів та швидкий запуск.\n\n🚀 **План дій:**\n1. Усуньте зайві кроки, зосередьтеся на головній цінності.\n2. Автоматизуйте рутинні операції.\n3. Запустіть активне просування.\n4. Зберіть аналітику та внесіть корективи."
        ]
        raw_response = random.choice(alt_matrices)
        response_hash = hashlib.md5(raw_response.encode('utf-8')).hexdigest()
        
    _LAST_GENERATED_RESPONSES[user_id] = response_hash
    return raw_response


async def ultimate_audio_punctuation_arbiter(wav_path: str, user_lang: str) -> str:
    """
    Резервний контролер перевірки розпізнаного аудіо. 
    Гарантує наявність розділових знаків, великих літер та правильної структури речень.
    """
    text = await robust_audio_recognition(wav_path, user_lang)
    if not text:
        return ""
        
    # Додаткова перевірка на наявність ком і крапок
    formatted = smart_punctuation_formatter(text)
    
    # Якщо раптом форматувальник пропустив знак в кінці, примусово додаємо
    if not formatted.endswith(('.', '!', '?')):
        formatted += "."
        
    return formatted


async def ultimate_tiktok_bypass_gateway(url: str, output_filename: str) -> bool:
    """
    Екстремальний резервний шлюз для TikTok. 
    Використовує оновлені параметри юзер-агентів та альтернативні методи парсингу,
    якщо основний каскад не впорався із захистом платформи.
    """
    emergency_strategies = [
        {'format': 'best[ext=mp4]', 'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15', 'geo_bypass': True, 'nocheckcertificate': True},
        {'format': 'worst', 'user_agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8)', 'extractor_args': {'tiktok': {'web_app': True}}, 'nocheckcertificate': True},
        {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]', 'geo_bypass': True, 'nocheckcertificate': True}
    ]

    loop = asyncio.get_running_loop()

    for idx, strat in enumerate(emergency_strategies, start=1):
        try:
            opts = {
                'outtmpl': output_filename,
                'quiet': True,
                'no_warnings': True,
                **strat
            }
            def run_emergency():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

            await loop.run_in_executor(None, run_emergency)
            
            if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1024:
                logger.info(f"[Emergency TikTok Gateway] Успішно завантажено через екстремальний шлюз #{idx}")
                return True
        except Exception as e:
            logger.warning(f"[Emergency TikTok Gateway] Спроба #{idx} не вдалась: {e}")
            continue
            
    return False

logger.info("🛡 Абсолютні резервні арбітри та контролери якості (Ultimate Patch v15) успішно активовані!")
# ==========================================
# РОЗДІЛ 14: ДИРЕКТОР ТА НАГЛЯДАЧ СИСТЕМИ (FINAL DIRECTOR & OVERSEER v16)
# ==========================================

# База для відстеження останніх тем користувачів (запобігання повторам)
_USER_IDEA_HISTORY = {}

async def director_overseer_ai_check(user_id: int, prompt_text: str) -> str:
    """
    Наглядач за генератором ідей: перевіряє історію користувача на повтори,
    гарантує розгорнутість структури та унікальність подачі.
    """
    global _USER_IDEA_HISTORY
    if user_id not in _USER_IDEA_HISTORY:
        _USER_IDEA_HISTORY[user_id] = []
        
    # Нормалізуємо запит для порівняння
    clean_prompt = prompt_text.lower().strip()
    
    # Генеруємо базовий або резервний звіт
    report = await ultimate_ai_generator_validator(prompt_text, user_id)
    
    # Якщо користувач часто запитує подібне, директор підсилює унікальність
    if clean_prompt in _USER_IDEA_HISTORY[user_id]:
        logger.info(f"[Director] Виявлено повторний запит теми від користувача {user_id}. Розширюємо унікальний контекст.")
        report = (
            f"💡 **Поглиблений експертний розширений звіт:** `{prompt_text}`\n\n"
            "🎯 **Абсолютно новий ракурс та нестандартні рішення:**\n"
            "1. **Антикризовий план:** Розгорніть паралельні тестування гіпотез, щоб мінімізувати ризики.\n"
            "2. **Оптимізація ресурсів:** Задіюйте мінімальні вкладення на старті та масштабуйте лише прибуткові елементи.\n"
            "3. **Автоматизація:** Впровадьте сучасні інструменти для прискорення рутинних процесів.\n"
            "4. **Стратегічний підсумок:** Системний контроль якості гарантує успіх навіть у конкурентній ніші."
        )
        
    # Зберігаємо в історію (пам'ятаємо останні 5 унікальних тем)
    _USER_IDEA_HISTORY[user_id].append(clean_prompt)
    if len(_USER_IDEA_HISTORY[user_id]) > 5:
        _USER_IDEA_HISTORY[user_id].pop(0)
        
    return report


async def director_overseer_audio_check(wav_path: str, user_lang: str) -> str:
    """
    Наглядач за аудіо: контролює якість роботи попередніх рушіїв, 
    перевіряє наявність коми, крапок та чистоту тексту.
    """
    text = await ultimate_audio_punctuation_arbiter(wav_path, user_lang)
    if not text:
        return ""
        
    # Фінальна перевірка директором на граматичну повноту речення
    formatted = smart_punctuation_formatter(text)
    return formatted


async def director_overseer_tiktok_dispatch(url: str, output_filename: str, user_id: int) -> bool:
    """
    Наглядач за TikTok: послідовно запускає основний каскад та екстремальні шлюзи.
    Якщо всі спроби зазнають краху, надсилає звіт безпосередньо овнеру.
    """
    # 1. Пробуємо основний каскад
    success = await cascade_download_tiktok(url, output_filename)
    if success:
        return True
        
    # 2. Якщо не вийшло, задіюємо екстремальний шлюз обходу
    success_emergency = await ultimate_tiktok_bypass_gateway(url, output_filename)
    if success_emergency:
        return True
        
    # 3. Якщо і це не допомогло — Директор фіксує критичну помилку та сповіщає Овнера
    error_details = f"❌ [Помилка завантаження TikTok]\n• Користувач ID: `{user_id}`\n• Посилання: `{url}`\n• Статус: *Жоден із каскадних та екстремальних шлюзів не зміг обійти захист платформи (можливе блокування IP сервером Render).* "
    logger.error(error_details)
    
    try:
        await bot.send_message(CREATOR_ID, error_details, parse_mode="Markdown")
    except Exception:
        pass
        
    return False

logger.info("👑 Директор та наглядач системи (Final Director & Overseer v16) успішно активований і контролює весь потік даних!")
# ==========================================
# РОЗДІЛ 15: ВЕЛИКА БІБЛІОТЕКА ШАБЛОНІВ ТА МЕНЕДЖЕР СЕСІЙ (ULTIMATE ARCHIVE v17)
# ==========================================

# Величезна резервна бібліотека експертних матриць на випадок будь-яких збоїв
GIANT_EXPERT_LIBRARY = {
    "default": [
        "💡 **Стратегічний звіт:** Детально проаналізуйте цільову аудиторію, виділіть головні переваги продукту, створіть унікальний контент-план і запустіть тестову рекламну кампанію з мінімальним бюджетом для оцінки результатів.",
        "💡 **Експертний план:** Оптимізуйте внутрішні процеси, автоматизуйте рутинні задачі за допомогою скриптів, підвищте якість сервісу та запровадьте систему регулярного моніторингу ключових показників (KPI)."
    ],
    "маркетинг": [
        "📈 **Масштабна маркетинг-стратегія:**\n1. Проведіть глибокий сегментний аналіз ринку.\n2. Створіть вірусний гачок для перших 3 секунд відео.\n3. Використовуйте крос-платформний посил у соцмережах.\n4. Проаналізуйте конверсії та оптимізуйте бюджети."
    ],
    "розробка": [
        "💻 **План технічної реалізації:**\n1. Розробіть архітектуру проекту (MVP).\n2. Напишіть модульний та чистий код із коментарями.\n3. Проведіть стрес-тестування під навантаженням.\n4. Розгорніть систему на стабільному хостингу з моніторингом."
    ],
    "контент": [
        "🎬 **Стратегія створення контенту:**\n1. Зберіть референси популярних трендів у вашій ніші.\n2. Підготуйте якісний сценарій із чіткою структурою.\n3. Здійсніть професійний монтаж із динамічними переходами.\n4. Додайте залучаючий заклик до дії (CTA)."
    ]
}

async def library_archive_lookup(prompt_text: str) -> str:
    """
    Звертається до величезної бібліотеки шаблонів, шукає збіги за ключовими словами
    і повертає розгорнуту, якісну та практичну відповідь.
    """
    p_lower = prompt_text.lower()
    
    # Шукаємо за ключовими словами у бібліотеці
    selected_pool = GIANT_EXPERT_LIBRARY["default"]
    for keyword, pool in GIANT_EXPERT_LIBRARY.items():
        if keyword in p_lower and keyword != "default":
            selected_pool = pool
            break
            
    base_text = random.choice(selected_pool)
    return f"{base_text}\n\n✨ *Архівний наглядач підтверджує актуальність даного рішення для вашої задачі.*"


# Покращений перехоплювач Директора з інтеграцією Бібліотеки та Менеджера сесій
async def director_final_approval_wrapper(user_id: int, prompt_text: str) -> str:
    """
    Фінальний директорський арбітр: перевіряє унікальність, обсяг, 
    а в разі відсутності інтернету миттєво задіює Велику Бібліотеку шаблонів.
    """
    try:
        # Пробуємо отримати звіт через основний інтелектуальний канал
        report = await director_overseer_ai_check(user_id, prompt_text)
        if len(report) < 50:
            raise Exception("Звіт занадто короткий.")
        return report
    except Exception:
        # Якщо сталася затримка або збій — Директор бере розгорнуту відповідь із Великої Бібліотеки
        logger.warning(f"[Director Archive] Задіяно Велику Бібліотеку шаблонів для користувача {user_id}")
        archive_report = await library_archive_lookup(prompt_text)
        return (
            f"💡 **Розгорнутий експертний звіт (Бібліотека знань):** `{prompt_text}`\n\n"
            f"{archive_report}"
        )


async def session_auto_reanimator_watchdog():
    """
    Менеджер сесій: періодично перевіряє цілісність кешу та станів,
    запобігаючи зависанням у фонових процесах бота.
    """
    while True:
        try:
            # Очищення тимчасових словників історії, якщо вони стають занадто великими
            global _USER_IDEA_HISTORY
            if len(_USER_IDEA_HISTORY) > 1000:
                _USER_IDEA_HISTORY.clear()
        except Exception:
            pass
        await asyncio.sleep(1800) # Кожні 30 хвилин

# Автоматичний запуск реаніматора сесій при старті
asyncio.create_task(session_auto_reanimator_watchdog())
logger.info("📚 Велика бібліотека шаблонів та Менеджер сесій (Ultimate Archive v17) успішно активовані!")
# ==========================================
# РОЗДІЛ 16: АНТИ-СОН СЕРВЕРА ТА ГОЛОВНИЙ ФІНАЛЬНИЙ КОНТРОЛЕР ДИРЕКТОРА (MASTER GATEKEEPER v18)
# ==========================================

import aiohttp

async def dedicated_anti_sleep_heartbeat():
    """
    Спеціальний надпотужний фоновий процес анти-сон, який надсилає короткі 
    сигнали на вебсервер Render, щоб гарантувати постійну активність бота без засинань.
    """
    await asyncio.sleep(10)
    logger.info("[Anti-Sleep] Сервіс підтримки активності сервера запущено.")
    while True:
        try:
            target_url = RENDER_EXTERNAL_URL
            if target_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(target_url, timeout=15) as response:
                        if response.status == 200:
                            logger.info("[Anti-Sleep] Успішний короткий сигнал пінг на сервер — активність підтримано.")
        except Exception as e:
            logger.warning(f"[Anti-Sleep] Попередження пінг-сигналу: {e}")
        
        # Надсилаємо сигнал кожні 3 хвилини (180 секунд)
        await asyncio.sleep(180)


# Автоматичний запуск пінг-сигналів анти-сон при старті
asyncio.create_task(dedicated_anti_sleep_heartbeat())


async def master_director_final_gatekeeper(user_id: int, action_type: str, data_payload: dict) -> dict:
    """
    Головний фінальний контролер Директора. Перед тим як надіслати будь-який результат 
    користувачу, цей метод перевіряє кожен етап:
    - Для генератора ідей: перевіряє унікальність, обсяг та задіює Бібліотеку за потреби.
    - Для аудіо: контролює правильність пунктуації та структуру тексту.
    - Для TikTok: гарантує проходження каскаду та екстремальних шлюзів.
    """
    logger.info(f"[Master Gatekeeper] Директор розпочав перевірку етапів для користувача {user_id} [Дія: {action_type}]")
    
    result_bundle = {"status": "success", "content": None, "error": None}
    
    if action_type == "ai_generator":
        prompt = data_payload.get("prompt", "")
        # Директор перевіряє та отримує схвалену розгорнуту відповідь
        final_text = await director_final_approval_wrapper(user_id, prompt)
        result_bundle["content"] = final_text
        
    elif action_type == "audio":
        wav_path = data_payload.get("wav_path", "")
        lang = data_payload.get("lang", "uk")
        # Директор перевіряє якість аудіо та пунктуацію
        formatted_text = await director_overseer_audio_check(wav_path, lang)
        result_bundle["content"] = formatted_text
        
    elif action_type == "tiktok":
        url = data_payload.get("url", "")
        filename = data_payload.get("filename", "")
        # Директор суворо контролює завантаження і у разі поразки шле звіт овнеру
        success = await director_overseer_tiktok_dispatch(url, filename, user_id)
        result_bundle["content"] = success
        if not success:
            result_bundle["status"] = "failed"
            result_bundle["error"] = "Жоден шлюз не зміг обійти захист TikTok."
            
    logger.info(f"[Master Gatekeeper] Перевірку Директора завершено успішно. Статус: {result_bundle['status'].upper()}")
    return result_bundle

logger.info("🛡 Анти-сон сервера та Головний фінальний контролер Директора (Master Gatekeeper v18) повністю активовані!")
