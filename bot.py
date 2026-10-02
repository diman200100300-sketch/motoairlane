import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from openai import OpenAI

# Автоматичне оновлення бібліотеки yt-dlp для стабільного обходу захисту платформ
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
    logging.info("Бібліотеку yt-dlp успішно оновлено до актуальної версії.")
except Exception as e:
    logging.error(f"Помилка автоматичного оновлення yt-dlp: {e}")

import yt_dlp

# Детальне налаштування системи логування для відстеження подій у боті
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфігураційні змінні (замініть на ваші актуальні дані перед запуском)
TOKEN = "ТВОЙ_TELEGRAM_BOT_TOKEN"
OPENAI_API_KEY = "ТВОЙ_OPENAI_API_KEY"
ADMIN_IDS = [123456789]  # Впишіть сюди свій головний Telegram ID

# Ініціалізація основних клієнтів бота та OpenAI
bot = Bot(token=TOKEN)
dp = Dispatcher()
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# РОБОТА З БАЗОЮ ДАНИХ (SQLite)
# =====================================================================
def init_db():
    try:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_pro INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                language TEXT DEFAULT 'uk',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Базу даних успішно ініціалізовано.")
    except Exception as e:
        logger.error(f"Помилка при ініціалізації бази даних: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database.db")

def is_user_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return bool(res and res[0] == 1)
    except Exception as e:
        logger.error(f"Помилка перевірки прав адміна: {e}")
        return False

def check_pro_status(user_id: int) -> bool:
    if is_user_admin(user_id):
        return True
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_pro FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return bool(res and res[0] == 1)
    except Exception as e:
        logger.error(f"Помилка перевірки PRO статусу: {e}")
        return False

def get_user_lang(user_id: int) -> str:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 'uk'
    except Exception as e:
        logger.error(f"Помилка отримання мови користувача: {e}")
        return 'uk'

def set_user_lang(user_id: int, lang: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка оновлення мови користувача: {e}")

# =====================================================================
# СЛОВНИКИ МУЛЬТИВМОВНОСТІ (ПОВНА ЛОКАЛІЗАЦІЯ)
# =====================================================================
LANG_TEXTS = {
    'uk': {
        'status_pro': "⭐ Статус: PRO (Безліміт)",
        'status_free': "⭐ Статус: Безкоштовний",
        'choose_section': "Оберіть розділ нижче:",
        'main_menu_title': "Головне меню керування:",
        'btn_tiktok': "📥 Завантажити відео (TikTok)",
        'btn_audio': "🎙 Аудіо інструменти (В текст)",
        'btn_ai': "🤖 ШІ Генератор ідей (Глибокий аналіз)",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Language / Мова / Język",
        'lang_changed': "✅ Мову успішно змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok, і я завантажу його за кілька секунд.",
        'downloading': "⏳ Обробка та завантаження відео...",
        'download_error': "❌ Не вдалося завантажити відео. Спробуйте інше посилання.",
        'ai_prompt': "💡 **Глибокий ШІ Генератор ідей**\n\nНапишіть будь-яку тему, нішу чи об'єкт. ШІ проведе глибокий аналіз та видасть унікальні розгорнуті варіанти для створення контенту або відео без повторів!",
        'ai_generating': "🧠 Проводжу глибокий аналіз та генерую унікальні варіанти контенту...",
        'back': "« Назад",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл, і я переведу його в текст.",
        'audio_processing': "⏳ Розпізнаю аудіо через ШІ...",
        'buy_title': "💎 **Отримання PRO**\nЦіна: 19 zł/місяць\nОплата через BLIK на номер:\n`+48 733 985 396`",
        'i_paid_btn': "✉️ Я сплатив",
        'i_paid_msg': "⏳ Ваша оплата перевіряється адміністратором. Після підтвердження статус PRO буде активовано автоматично!"
    },
    'en': {
        'status_pro': "⭐ Status: PRO (Unlimited)",
        'status_free': "⭐ Status: Free",
        'choose_section': "Choose a section below:",
        'main_menu_title': "Main control menu:",
        'btn_tiktok': "📥 Download video (TikTok)",
        'btn_audio': "🎙 Audio tools (To text)",
        'btn_ai': "🤖 AI Idea Generator (Deep analysis)",
        'btn_pro_active': "✅ PRO Active",
        'btn_buy_pro': "💎 Buy PRO — 19 zł/mo",
        'btn_lang': "🌐 Language / Мова / Język",
        'lang_changed': "✅ Language successfully changed to English!",
        'send_tiktok': "📥 Send a TikTok link, and I will download it in a few seconds.",
        'downloading': "⏳ Processing and downloading video...",
        'download_error': "❌ Failed to download the video. Please try another link.",
        'ai_prompt': "💡 **Deep AI Idea Generator**\n\nWrite any topic, niche, or object. AI will conduct a deep analysis and provide unique detailed options for content or video creation without repeats!",
        'ai_generating': "🧠 Conducting deep analysis and generating unique content options...",
        'back': "« Back",
        'audio_send': "🎙 Send a voice message or audio file, and I will convert it to text.",
        'audio_processing': "⏳ Transcribing audio via AI...",
        'buy_title': "💎 **Get PRO**\nPrice: 19 zł/month\nPayment via BLIK to number:\n`+48 733 985 396`",
        'i_paid_btn': "✉️ I have paid",
        'i_paid_msg': "⏳ Your payment is being verified by the admin. Once confirmed, PRO status will be activated automatically!"
    },
    'pl': {
        'status_pro': "⭐ Status: PRO (Bez limitu)",
        'status_free': "⭐ Status: Darmowy",
        'choose_section': "Wybierz sekcję poniżej:",
        'main_menu_title': "Główne menu sterowania:",
        'btn_tiktok': "📥 Pobierz wideo (TikTok)",
        'btn_audio': "🎙 Narzędzia audio (Na tekst)",
        'btn_ai': "🤖 Generator pomysłów AI (Głęboka analiza)",
        'btn_pro_active': "✅ PRO Aktywne",
        'btn_buy_pro': "💎 Kup PRO — 19 zł/mies.",
        'btn_lang': "🌐 Language / Мова / Język",
        'lang_changed': "✅ Język został pomyślnie zmieniony na polski!",
        'send_tiktok': "📥 Wyślij link do TikTok, a pobiorę go w kilka sekund.",
        'downloading': "⏳ Przetwarzanie i pobieranie wideo...",
        'download_error': "❌ Nie udało się pobrać wideo. Spróbuj innego linku.",
        'ai_prompt': "💡 **Głęboki Generator Pomysłów AI**\n\nNapisz dowolny temat, niszę lub obiekt. AI przeprowadzi głęboką analizę i wyda unikalne, szczegółowe opcje tworzenia treści lub wideo bez powtórzeń!",
        'ai_generating': "🧠 Przeprowadzam głęboką analizę i generuję unikalne opcje treści...",
        'back': "« Wstecz",
        'audio_send': "🎙 Wyślij wiadomość głosową lub plik audio, a przekonwertuję ją na tekst.",
        'audio_processing': "⏳ Przetwarzanie audio przez AI...",
        'buy_title': "💎 **Uzyskaj PRO**\nCena: 19 zł/miesiąc\nPłatność przez BLIK na numer:\n`+48 733 985 396`",
        'i_paid_btn': "✉️ Zapłaciłem",
        'i_paid_msg': "⏳ Twoja płatność jest weryfikowana przez administratora. Po potwierdzeniu status PRO zostanie aktywowany automatycznie!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

# =====================================================================
# ВЕБСЕРВЕР ДЛЯ ПІДТРИМКИ АКТИВНОСТІ НА РЕНДЕРІ (KEEP-ALIVE)
# =====================================================================
async def handle_ping(request):
    return web.Response(text="Bot is running and fully operational!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Вебсервер успішно запущено на порту {port}")
# Визначення станів конечного автомата (FSM)
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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute(
                "INSERT INTO users (user_id, username, is_pro, is_admin, language) VALUES (?, ?, 0, 0, 'uk')",
                (user_id, username)
            )
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка збереження користувача в БД: {e}")
    
    pro_active = check_pro_status(user_id)
    status_text = get_t(user_id, 'status_pro') if pro_active else get_t(user_id, 'status_free')
    
    await message.answer(
        f"{status_text}\n\n{get_t(user_id, 'choose_section')}",
        reply_markup=main_menu_kb(user_id)
    )

# Команда для призначення адміністратора (помічника), який зможе видавати PRO
@dp.message(Command("give_admin"))
async def cmd_give_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Невірний формат. Використовуйте: `/give_admin <user_id>`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Користувачу з ID `{target_id}` успішно надано права адміністратора (може видавати PRO).", parse_mode="Markdown")
        logger.info(f"Адмін {message.from_user.id} призначив нового адміна: {target_id}")
    except Exception as e:
        await message.answer(f"❌ Помилка виконання команди: {e}")

# Команда для видачі PRO (доступна головному адміну та призначеним адмінам)
@dp.message(Command("give_pro"))
async def cmd_give_pro(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ Ця команда доступна лише адміністраторам системи.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Невірний формат. Використовуйте: `/give_pro <user_id>`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"💎 Статус PRO успішно активовано для користувача з ID `{target_id}`!", parse_mode="Markdown")
        logger.info(f"Адміністратор {message.from_user.id} видав PRO для {target_id}")
        
        try:
            await bot.send_message(target_id, "🎉 Вітаємо! Ваш статус PRO успішно активовано адміністратором!")
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ Помилка активації PRO: {e}")
@dp.callback_query(F.data == "download_video")
async def cb_download_video(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]])
    await callback.message.edit_text(get_t(user_id, 'send_tiktok'), reply_markup=kb)
    await state.set_state(GenStates.waiting_for_video_link)
    await callback.answer()

@dp.message(GenStates.waiting_for_video_link)
async def process_video_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith("/"):
        await state.clear()
        if message.text == "/start":
            await cmd_start(message)
        return
        
    url = message.text.strip()
    processing_msg = await message.answer(get_t(user_id, 'downloading'))
    
    output_filename = f"video_{user_id}.mp4"
    ydl_opts = {
        'outtmpl': output_filename,
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True
    }
    
    success = False
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        success = True
    except Exception as e:
        logger.error(f"Помилка завантаження через yt-dlp: {e}")
        success = False
        
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
    except Exception:
        pass
    
    if success and os.path.exists(output_filename):
        try:
            video_file = FSInputFile(output_filename)
            await message.answer_video(video=video_file)
        except Exception as err:
            logger.error(f"Помилка відправки відео файлу в Telegram: {err}")
            await message.answer(get_t(user_id, 'download_error'))
        finally:
            if os.path.exists(output_filename):
                try:
                    os.remove(output_filename)
                except Exception:
                    pass
    else:
        await message.answer(get_t(user_id, 'download_error'))
        
    await state.clear()
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await message.answer(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))

# Аудіо інструменти (транскрипція через Whisper)
@dp.callback_query(F.data == "audio_to_text")
async def cb_audio_to_text(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]])
    await callback.message.edit_text(get_t(user_id, 'audio_send'), reply_markup=kb)
    await state.set_state(GenStates.waiting_for_audio)
    await callback.answer()

@dp.message(GenStates.waiting_for_audio, F.voice | F.audio)
async def process_audio_file(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    processing_msg = await message.answer(get_t(user_id, 'audio_processing'))
    
    audio_file_name = f"audio_{user_id}.ogg"
    try:
        file_info = await bot.get_file(message.voice.file_id if message.voice else message.audio.file_id)
        await bot.download_file(file_info.file_path, audio_file_name)
        
        with open(audio_file_name, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        recognized_text = transcript.text
        await message.answer(f"📝 **Розпізнаний текст:**\n\n{recognized_text}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка розпізнавання аудіо: {e}")
        await message.answer(f"❌ Помилка розпізнавання аудіо: {e}")
    finally:
        if os.path.exists(audio_file_name):
            try:
                os.remove(audio_file_name)
            except Exception:
                pass
            
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
    except Exception:
        pass

    await state.clear()
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await message.answer(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))

# Зміна мови інтерфейсу
@dp.callback_query(F.data == "change_lang")
async def cb_change_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="set_lang_pl")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]
    ])
    await callback.message.edit_text("🌐 Оберіть мову / Choose language / Wybierz język:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[2]
    set_user_lang(user_id, lang)
    await callback.message.answer(get_t(user_id, 'lang_changed'))
    
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await callback.message.edit_text(
        f"{status_text}\n\n{get_t(user_id, 'choose_section')}",
        reply_markup=main_menu_kb(user_id)
    )
    await callback.answer()
@dp.callback_query(F.data == "ai_generator")
async def cb_ai_generator(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]])
    await callback.message.edit_text(get_t(user_id, 'ai_prompt'), reply_markup=kb, parse_mode="Markdown")
    await state.set_state(GenStates.waiting_for_idea_prompt)
    await callback.answer()

@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_idea(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith("/"):
        await state.clear()
        if message.text == "/start":
            await cmd_start(message)
        return
        
    prompt_text = message.text.strip()
    wait_msg = await message.answer(get_t(user_id, 'ai_generating'))
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "Ти професійний контент-стратег, досвідчений сценарист та аналітик соціальних мереж. "
                        "Надавай глибокі, розгорнуті, цікаві та повністю унікальні варіанти й сценарії для створення контенту або відео за запитом користувача. "
                        "Категорично уникай банальних шаблонів, загальних фраз та повторів. Кожна відповідь має бути максимально детальною, практичною, унікальною "
                        "та містити чітку структуру:\n"
                        "1. Суть і глибока механіка об'єкта чи явища.\n"
                        "2. Практичне використання, корисні лайфхаки та уникнення типових помилок.\n"
                        "3. Експертний сценарій та ідеї для створення вірусного/експертного відео.\n"
                        "Зроби кожну відповідь насиченою корисною інформацією."
                    )
                },
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.85,
            max_tokens=1100
        )
        result_text = response.choices[0].message.content
    except Exception as e:
        logger.error(f"Помилка генерації OpenAI: {e}")
        result_text = f"❌ Сталася помилка при зверненні до ШІ: {e}"
        
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
    except Exception:
        pass

    await message.answer(result_text, parse_mode="Markdown")
    
    await state.clear()
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await message.answer(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))

# Процес купівлі PRO
@dp.callback_query(F.data == "buy_pro")
async def cb_buy_pro(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_t(user_id, 'i_paid_btn'), callback_data="i_paid")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        get_t(user_id, 'buy_title'),
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "i_paid")
async def cb_i_paid(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.answer(get_t(user_id, 'i_paid_msg'))
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, 
                f"🔔 Користувач @{callback.from_user.username or 'none'} (ID: `{user_id}`) натиснув «Я сплатив».\n"
                f"Використайте команду: `/give_pro {user_id}` для активації.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    try:
        await callback.message.edit_text(
            f"{status_text}\n\n{get_t(user_id, 'choose_section')}",
            reply_markup=main_menu_kb(user_id)
        )
    except Exception:
        await callback.message.answer(
            f"{status_text}\n\n{get_t(user_id, 'choose_section')}",
            reply_markup=main_menu_kb(user_id)
        )
    await callback.answer()

@dp.callback_query(F.data == "pro_active")
async def cb_pro_active(callback: types.CallbackQuery):
    await callback.answer("✅ У вас активовано безлімітний PRO статус!", show_alert=True)

# Головна точка запуску (Вебсервер + Полінг Telegram)
async def main():
    # Запускаємо фоновий вебсервер для платформи Render
    asyncio.create_task(start_web_server())
    
    # Видаляємо вебхуки для стабільного запуску polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Помилка видалення вебхука: {e}")
        
    logger.info("Бот успішно розпочав роботу через start_polling!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Роботу бота було зупинено користувачем або системою.")
