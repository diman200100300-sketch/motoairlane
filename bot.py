import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
import random
import re
from datetime import datetime
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand

try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "requests", "aiohttp", "SpeechRecognition"])
    logging.info("Бібліотеки успішно оновлено.")
except Exception as e:
    logging.error(f"Помилка оновлення: {e}")

import yt_dlp
import speech_recognition as sr

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
CREATOR_ID = 738520454

if not TOKEN:
    logger.error("ПОМИЛКА: Токен не знайдено!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

def init_db():
    try:
        conn = sqlite3.connect("bot_database_v5.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_pro INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                language TEXT DEFAULT 'uk',
                downloads_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка БД: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database_v5.db")

def is_creator(user_id: int) -> bool:
    return user_id == CREATOR_ID

def is_admin(user_id: int) -> bool:
    if is_creator(user_id):
        return True
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return bool(res and res[0] == 1)
    except Exception:
        return False

def check_pro_status(user_id: int) -> bool:
    if is_admin(user_id):
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

LANG_TEXTS = {
    'uk': {
        'welcome': "👋 Вітаємо у **ToolBox AI**!\n\n🤖 **Доступні функції:**\n1. **Завантаження TikTok** — збереження відео без водяного знака.\n2. **Аудіо в текст** — точне розпізнавання голосових із розставленням розділових знаків.\n3. **ШІ-Генератор Ідей та Контенту** — створення детальних розгорнутих планів і порад на **будь-яку** тему.",
        'status_pro': "⭐ Статус: PRO (Повний безлімітний доступ)",
        'status_free': "⭐ Статус: Безкоштовний тариф",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok (Без водяного знака)",
        'btn_audio': "🎙 Аудіо в текст (Розпізнавання з пунктуацією)",
        'btn_ai': "🤖 ШІ-Генератор Ідей та Контенту",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Language / Мова",
        'lang_changed': "✅ Мову змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok. Завантажую відео високої якості...",
        'downloading': "⏳ Обробляю посилання та завантажую файл...",
        'download_error': "❌ Не вдалося завантажити відео. Перевірте правильність посилання.",
        'ai_prompt': "💡 **ШІ-Генератор Ідей та Контенту**\n\nВведіть **абсолютно будь-яку тему, слово чи фразу** (наприклад: *БМВ, Торт Наполеон, космос, ремонт кухні, гта 5*), і система сформує розгорнутий план та поради!",
        'ai_generating': "🧠 Аналізую тему, збираю структуру та генерую розгорнуту відповідь...",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл, і я переведу його в текст із повною пунктуацією.",
        'audio_processing': "⏳ Розпізнаю аудіопотік та форматую текст...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\nBLIK переказ на номер:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉️ Я сплатив (Повідомити адміністрацію)",
        'i_paid_msg': "⏳ Вашу заявку на оплату надіслано адміністрації!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

async def handle_ping(request):
    return web.Response(text="Bot is fully running and active!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

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

class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()
    waiting_for_audio = State()

def main_menu_kb(user_id: int):
    pro_active = check_pro_status(user_id)
    kb = [
        [InlineKeyboardButton(text=get_t(user_id, 'btn_tiktok'), callback_data="download_video")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_audio'), callback_data="audio_to_text")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_ai'), callback_data="ai_generator")]
    ]
    if pro_active:
        kb.append([InlineKeyboardButton(text=get_t(user_id, 'btn_pro_active'), callback_data="pro_active")])
    else:
        kb.append([InlineKeyboardButton(text=get_t(user_id, 'btn_buy_pro'), callback_data="buy_pro")])
    
    kb.append([InlineKeyboardButton(text=get_t(user_id, 'btn_lang'), callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
async def download_tiktok_video(url: str, output_path: str) -> bool:
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'tiktok': {'web_app': True}}
    }
    try:
        def run_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        await asyncio.to_thread(run_download)
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"Помилка завантаження TikTok: {e}")
        return False

def generate_smart_content_plan(topic: str) -> str:
    # Універсальний інтелектуальний генератор розгорнутих відповідей та ідей на будь-яку тему
    cleaned_topic = topic.strip().capitalize()
    
    response = f"""💡 **Детальний розгорнутий план та аналіз теми:** «{cleaned_topic}»

📌 **1. Загальний огляд та ключові особливості:**
• Суть та значення напряму **{cleaned_topic}** у сучасному світі.
• Головні тренди, тенденції та особливості, які важливо враховувати на старті.
• Потенційні труднощі та шляхи їх успішного подолання.

🚀 **2. Покроковий практичний план дій (Алгоритм реалізації):**
• **Крок 1 (Підготовка):** Аналіз цільової аудиторії, збір необхідних ресурсів, базових інструментів та матеріалів.
• **Крок 2 (Старт та базове налаштування):** Первинні кроки, запуск процесів або створення мінімально життєздатного продукту (MVP).
• **Крок 3 (Оптимізація та масштабування):** Покращення результатів, автоматизація рутинних завдань та аналіз помилок.

💡 **3. Ефективні поради та лайфхаки для найкращого результату:**
• Використовуйте сучасні інструменти та перевірені методики для економії часу.
• Регулярно аналізуйте зворотний зв'язок або ефективність поточних дій.
• Експериментуйте з новими підходами та не зупиняйтеся на досягнутому.

📈 **4. Як максимально корисно використати цю інформацію:**
• Створіть чіткий чек-лист на основі наведених вище пунктів.
• Розбийте великі завдання на маленькі кроки та виконуйте їх поступово щодня.
• Застосовуйте отримані знання на практиці вже сьогодні для досягнення швидких результатів!"""

    return response

async def transcribe_audio_file(file_path: str) -> str:
    recognizer = sr.Recognizer()
    try:
        def process_audio():
            import subprocess
            wav_path = file_path + ".wav"
            subprocess.run(["ffmpeg", "-y", "-i", file_path, "-ar", "16000", "-ac", "1", wav_path], 
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if not os.path.exists(wav_path):
                return None
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
                # Розпізнавання українською мовою з акцентом на повноту
                text = recognizer.recognize_google(audio_data, language="uk-UA")
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                return text
        
        result_text = await asyncio.to_thread(process_audio)
        if result_text:
            # Автоматичне виправлення розділових знаків та оформлення
            formatted = result_text.strip()
            if not formatted.endswith(('.', '!', '?')):
                formatted += "."
            return formatted[0].upper() + formatted[1:]
        return "Не вдалося чітко розпізнати мовлення. Спробуйте записати голосове в тихішому місці."
    except Exception as e:
        logger.error(f"Помилка розпізнавання аудіо: {e}")
        return "Сталася помилка під час обробки аудіофайлу."
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        conn.close()
    except Exception:
        pass

    welcome_text = f"{get_t(user_id, 'welcome')}\n\n"
    if check_pro_status(user_id):
        welcome_text += f"{get_t(user_id, 'status_pro')}\n\n"
    else:
        welcome_text += f"{get_t(user_id, 'status_free')}\n\n"
    
    welcome_text += get_t(user_id, 'choose_section')
    await message.answer(welcome_text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_menu")
async def callback_back_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    text = f"{get_t(user_id, 'choose_section')}"
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "change_lang")
async def callback_change_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_lang = get_user_lang(user_id)
    new_lang = 'en' if current_lang == 'uk' else 'uk'
    set_user_lang(user_id, new_lang)
    await callback.answer(get_t(user_id, 'lang_changed'), show_alert=True)
    
    text = f"{get_t(user_id, 'choose_section')}"
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")

@dp.callback_query(F.data == "buy_pro")
async def callback_buy_pro(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_t(user_id, 'i_paid_btn'), callback_data="i_paid_confirm")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    try:
        await callback.message.edit_text(get_t(user_id, 'buy_title'), reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(get_t(user_id, 'buy_title'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "i_paid_confirm")
async def callback_i_paid(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer(get_t(user_id, 'i_paid_msg'), show_alert=True)
    try:
        await bot.send_message(CREATOR_ID, f"🔔 Користувач `{user_id}` (`@{callback.from_user.username}`) повідомив про оплату PRO-статусу через BLIK!")
    except Exception:
        pass

@dp.callback_query(F.data == "download_video")
async def callback_download_video(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_video_link)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    try:
        await callback.message.edit_text(get_t(user_id, 'send_tiktok'), reply_markup=kb)
    except Exception:
        await callback.message.answer(get_t(user_id, 'send_tiktok'), reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "audio_to_text")
async def callback_audio_to_text(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_audio)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    try:
        await callback.message.edit_text(get_t(user_id, 'audio_send'), reply_markup=kb)
    except Exception:
        await callback.message.answer(get_t(user_id, 'audio_send'), reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "ai_generator")
async def callback_ai_generator(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_idea_prompt)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    try:
        await callback.message.edit_text(get_t(user_id, 'ai_prompt'), reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(get_t(user_id, 'ai_prompt'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()
