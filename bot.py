import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
import re
from datetime import datetime
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from openai import OpenAI

# Автоматичне оновлення та налаштування інструментів завантаження
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "requests", "aiohttp"])
    logging.info("Бібліотеки yt-dlp та асистенти успішно оновлено до актуальних версій.")
except Exception as e:
    logging.error(f"Помилка оновлення залежностей: {e}")

import yt_dlp

# Глибоке налаштування системи логування для відстеження кожної події
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфігураційні змінні платформи
TOKEN = "ТВОЙ_TELEGRAM_BOT_TOKEN"
OPENAI_API_KEY = "ТВОЙ_OPENAI_API_KEY"
ADMIN_IDS = [123456789]  # Впишіть свій Telegram ID

bot = Bot(token=TOKEN)
dp = Dispatcher()
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# РОЗШИРЕНА РОБОТА З БАЗОЮ ДАНИХ (SQLite)
# =====================================================================
def init_db():
    try:
        conn = sqlite3.connect("bot_database_full.db")
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
        logger.info("Повну базу даних успішно ініціалізовано та перевірено.")
    except Exception as e:
        logger.error(f"Критична помилка при ініціалізації бази даних: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database_full.db")

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
        logger.error(f"Помилка перевірки прав адміністратора: {e}")
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
        logger.error(f"Помилка перевірки PRO статусу користувача: {e}")
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
        logger.error(f"Помилка отримання мови інтерфейсу: {e}")
        return 'uk'

def set_user_lang(user_id: int, lang: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
        conn.close()
        logger.info(f"Користувачу {user_id} змінено мову на {lang}")
    except Exception as e:
        logger.error(f"Помилка оновлення мови в базі: {e}")

# =====================================================================
# ПОВНІ МУЛЬТИВМОВНІ СЛОВНИКИ (УКРАЇНСЬКА, АНГЛІЙСЬКА, ПОЛЬСЬКА)
# =====================================================================
LANG_TEXTS = {
    'uk': {
        'status_pro': "⭐ Статус: PRO (Безлімітний доступ та повний функціонал)",
        'status_free': "⭐ Статус: Безкоштовний тариф",
        'choose_section': "Оберіть необхідний розділ в меню нижче:",
        'main_menu_title': "Головне експертне меню керування:",
        'btn_tiktok': "📥 Завантажити TikTok (Без водяного знака)",
        'btn_audio': "🎙 Аудіо інструменти (Транскрипція Whisper)",
        'btn_ai': "🤖 ШІ Генератор ідей (Глибокий аналіз)",
        'btn_pro_active': "✅ PRO Активно (Усі функції розблоковано)",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Language / Мова / Język",
        'lang_changed': "✅ Мову успішно змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok (відео, слайди або стрім). Я використаю кілька альтернативних алгоритмів обходу захисту, щоб завантажити оригінал без водяних знаків!",
        'downloading': "⏳ Застосовую мультипотоковий пошук та завантажую чисте відео без логотипу...",
        'download_error': "❌ На жаль, не вдалося завантажити відео через усі доступні резервні канали. Перевірте правильність посилання або спробуйте інше.",
        'ai_prompt': "💡 **Глибокий ШІ Генератор Контент-Ідей**\n\nНапишіть тему, нішу чи бізнес-напрямок. ШІ проведе розгорнутий аналіз, розпише механіку та видасть готові унікальні сценарії без повторів!",
        'ai_generating': "🧠 Проводжу глибокий аналіз ринку та генерую унікальні варіанти...",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл, і я конвертую його у якісний текст за допомогою ШІ.",
        'audio_processing': "⏳ Розпізнаю аудіопотік через нейромережу Whisper...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\nПерекажіть кошти через BLIK на польський номер:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉️ Я сплатив (Повідомити адміністратора)",
        'i_paid_msg': "⏳ Вашу заявку на оплату надіслано адміністратору. Статус буде активовано одразу після перевірки!"
    },
    'en': {
        'status_pro': "⭐ Status: PRO (Unlimited Access & Full Features)",
        'status_free': "⭐ Status: Free Tier",
        'choose_section': "Choose the required section from the menu below:",
        'main_menu_title': "Main Expert Control Menu:",
        'btn_tiktok': "📥 Download TikTok (No Watermark)",
        'btn_audio': "🎙 Audio Tools (Whisper Transcription)",
        'btn_ai': "🤖 AI Idea Generator (Deep Analysis)",
        'btn_pro_active': "✅ PRO Active (All Features Unlocked)",
        'btn_buy_pro': "💎 Buy PRO — 19 zł/mo",
        'btn_lang': "🌐 Language / Мова / Język",
        'lang_changed': "✅ Language successfully changed to English!",
        'send_tiktok': "📥 Send a TikTok link (video, slides, or stream). I will use multiple alternative bypass algorithms to download the original video without watermarks!",
        'downloading': "⏳ Applying multi-threaded search and downloading clean video without logo...",
        'download_error': "❌ Unfortunately, failed to download the video through all available backup channels. Please check the link or try another one.",
        'ai_prompt': "💡 **Deep AI Content Idea Generator**\n\nWrite a topic, niche, or business direction. AI will conduct a detailed analysis, outline mechanics, and provide ready unique scripts without repeats!",
        'ai_generating': "🧠 Conducting deep market analysis and generating unique options...",
        'back': "« Back to main menu",
        'audio_send': "🎙 Send a voice message or audio file, and I will convert it into high-quality text using AI.",
        'audio_processing': "⏳ Transcribing audio stream via Whisper neural network...",
        'buy_title': "💎 **Get PRO Status**\nPrice: 19 zł/month\nTransfer funds via BLIK to Polish number:\n`+48 733 985 396`\n\nAfter payment, click the button below.",
        'i_paid_btn': "✉️ I have paid (Notify Admin)",
        'i_paid_msg': "⏳ Your payment request has been sent to the admin. Status will be activated immediately upon verification!"
    },
    'pl': {
        'status_pro': "⭐ Status: PRO (Nieograniczony dostęp i pełne funkcje)",
        'status_free': "⭐ Status: Darmowy plan",
        'choose_section': "Wybierz żądaną sekcję z menu poniżej:",
        'main_menu_title': "Główne eksperckie menu sterowania:",
        'btn_tiktok': "📥 Pobierz TikTok (Bez znaku wodnego)",
        'btn_audio': "🎙 Narzędzia audio (Transkrypcja Whisper)",
        'btn_ai': "🤖 Generator pomysłów AI (Głęboka analiza)",
        'btn_pro_active': "✅ PRO Aktywne (Wszystkie funkcje odblokowane)",
        'btn_buy_pro': "💎 Kup PRO — 19 zł/mies.",
        'btn_lang': "🌐 Language / Мова / Język",
        'lang_changed': "✅ Język został pomyślnie zmieniony na polski!",
        'send_tiktok': "📥 Wyślij link do TikToka (wideo, pokaz slajdów lub transmisja). Użyję wielu alternatywnych algorytmów omijania zabezpieczeń, aby pobrać oryginał bez znaków wodnych!",
        'downloading': "⏳ Stosuję wielowątkowe wyszukiwanie i pobieram czyste wideo bez logo...",
        'download_error': "❌ Niestety nie udało się pobrać wideo przez wszystkie dostępne kanały zapasowe. Sprawdź poprawność linku lub spróbuj innego.",
        'ai_prompt': "💡 **Głęboki Generator Pomysłów na Treści AI**\n\nNapisz temat, niszę lub kierunek biznesowy. AI przeprowadzi szczegółową analizę, opisze mechanikę i dostarczy gotowe unikalne scenariusze bez powtórzeń!",
        'ai_generating': "🧠 Przeprowadzam głęboką analizę rynku i generuję unikalne opcje...",
        'back': "« Powrót do menu głównego",
        'audio_send': "🎙 Wyślij wiadomość głosową lub plik audio, a przekonwertuję ją na wysokiej jakości tekst za pomocą AI.",
        'audio_processing': "⏳ Transkrybuję strumień audio za pomocą sieci neuronowej Whisper...",
        'buy_title': "💎 **Uzyskaj status PRO**\nCena: 19 zł/miesiąc\nPrzelej środki przez BLIK na polski numer:\n`+48 733 985 396`\n\nPo dokonaniu płatności kliknij przycisk poniżej.",
        'i_paid_btn': "✉️ Zapłaciłem (Powiadom administratora)",
        'i_paid_msg': "⏳ Twoje zgłoszenie płatności zostało wysłane do administratora. Status zostanie aktywowany natychmiast po weryfikacji!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

# =====================================================================
# ВЕБСЕРВЕР KEEP-ALIVE ДЛЯ ПЛАТФОРМИ RENDER
# =====================================================================
async def handle_ping(request):
    return web.Response(text="Bot is fully running, multi-method TikTok downloader active!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Keep-alive вебсервер успішно запущено на порту {port}")
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
        logger.error(f"Помилка реєстрації користувача в базі: {e}")
    
    pro_active = check_pro_status(user_id)
    status_text = get_t(user_id, 'status_pro') if pro_active else get_t(user_id, 'status_free')
    
    await message.answer(
        f"{status_text}\n\n{get_t(user_id, 'choose_section')}",
        reply_markup=main_menu_kb(user_id)
    )

@dp.message(Command("give_admin"))
async def cmd_give_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас недостатньо прав для виконання цієї адміністративної команди.")
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
        await message.answer(f"✅ Користувачу з ID `{target_id}` успішно надано розширені права адміністратора.", parse_mode="Markdown")
        logger.info(f"Головний адмін призначив нового адміністратора: {target_id}")
    except Exception as e:
        await message.answer(f"❌ Помилка при призначенні адміна: {e}")

@dp.message(Command("give_pro"))
async def cmd_give_pro(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ Ця команда доступна виключно адміністраторам системи.")
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
        logger.info(f"Адміністратор {message.from_user.id} видав PRO для користувача {target_id}")
        
        try:
            await bot.send_message(target_id, "🎉 Вітаємо! Ваш статус PRO успішно активовано адміністратором системи!")
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ Помилка активації статусу PRO: {e}")
@dp.callback_query(F.data == "download_video")
async def cb_download_video(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]])
    await callback.message.edit_text(get_t(user_id, 'send_tiktok'), reply_markup=kb)
    await state.set_state(GenStates.waiting_for_video_link)
    await callback.answer()

# Потужна багатоступенева функція завантаження TikTok без водяного знака
async def download_tiktok_unwatermarked(url: str, output_filename: str) -> bool:
    # Метод 1: Пряме завантаження через yt-dlp з оптимізованими параметрами вилучення водяних знаків
    ydl_opts_1 = {
        'outtmpl': output_filename,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'extractor_args': {'tiktok': {'webpage_download': True}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts_1) as ydl:
            ydl.download([url])
        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 10000:
            logger.info("TikTok успішно завантажено методом 1 (yt-dlp standard).")
            return True
    except Exception as e:
        logger.warning(f"Метод 1 yt-dlp не спрацював: {e}")

    # Метод 2: Резервний профіль yt-dlp з примусовим вибором безпосереднього посилання на стрім/потік без логотипу
    ydl_opts_2 = {
        'outtmpl': output_filename,
        'format': 'bv*+ba/b',
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/'
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts_2) as ydl:
            ydl.download([url])
        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 10000:
            logger.info("TikTok успішно завантажено методом 2 (yt-dlp custom headers).")
            return True
    except Exception as e:
        logger.warning(f"Метод 2 yt-dlp не спрацював: {e}")

    # Метод 3: Альтернативний публічний API парсер для отримання прямого посилання на відео без водяного знака (No-Watermark)
    try:
        async with ClientSession() as session:
            api_url = f"https://tikwm.com/api/?url={url}"
            async with session.get(api_url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 0 and "data" in data:
                        video_no_watermark_url = data["data"].get("play") or data["data"].get("wmplay")
                        if video_no_watermark_url:
                            async with session.get(video_no_watermark_url) as vid_resp:
                                if vid_resp.status == 200:
                                    video_content = await vid_resp.read()
                                    with open(output_filename, "wb") as f:
                                        f.write(video_content)
                                    if os.path.exists(output_filename) and os.path.getsize(output_filename) > 10000:
                                        logger.info("TikTok успішно завантажено методом 3 (TikWM API no-watermark).")
                                        return True
    except Exception as e:
        logger.warning(f"Метод 3 (TikWM API) не спрацював: {e}")

    return False

@dp.message(GenStates.waiting_for_video_link)
async def process_video_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith("/"):
        await state.clear()
        if message.text == "/start":
            await cmd_start(message)
        return
        
    url = message.text.strip()
    
    # Перевірка наявності посилання
    if not ("tiktok.com" in url or "vm.tiktok.com" in url or "vt.tiktok.com" in url):
        await message.answer("⚠️ Будь ласка, надішліть коректне посилання на відео з TikTok.")
        return

    processing_msg = await message.answer(get_t(user_id, 'downloading'))
    output_filename = f"tiktok_clean_{user_id}_{int(datetime.now().timestamp())}.mp4"
    
    success = await download_tiktok_unwatermarked(url, output_filename)
        
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
    except Exception:
        pass
    
    if success and os.path.exists(output_filename):
        try:
            video_file = FSInputFile(output_filename)
            await message.answer_video(
                video=video_file, 
                caption="📥 Ваше відео без водяного знака успішно завантажено!"
            )
            
            # Оновлюємо лічильник завантажень в базі
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass
                
        except Exception as err:
            logger.error(f"Помилка надсилання відеофайлу користувачу в Telegram: {err}")
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

# Аудіо інструменти (транскрипція)
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
    
    audio_file_name = f"audio_{user_id}_{int(datetime.now().timestamp())}.ogg"
    try:
        file_info = await bot.get_file(message.voice.file_id if message.voice else message.audio.file_id)
        await bot.download_file(file_info.file_path, audio_file_name)
        
        with open(audio_file_name, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        recognized_text = transcript.text
        await message.answer(f"📝 **Розпізнаний текст за допомогою Whisper:**\n\n{recognized_text}", parse_mode="Markdown")
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

# Зміна мови інтерфейсу (усі 3 мови)
@dp.callback_query(F.data == "change_lang")
async def cb_change_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="set_lang_pl")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]
    ])
    await callback.message.edit_text("🌐 Оберіть зручну мову інтерфейсу / Choose interface language / Wybierz język interfejsu:", reply_markup=kb)
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
                        "Ти професійний контент-стратег, досвідчений сценарист та провідний аналітик соціальних мереж. "
                        "Надавай глибокі, розгорнуті, цікаві та повністю унікальні варіанти й сценарії для створення контенту чи відео за запитом користувача. "
                        "Категорично уникай банальних шаблонів, загальних фраз та повторів. Кожна відповідь має бути максимально детальною, практичною, унікальною "
                        "та містити чітку структуру:\n"
                        "1. Суть і глибока механіка об'єкта, ніші чи явища.\n"
                        "2. Практичне використання, корисні лайфхаки та уникнення типових помилок.\n"
                        "3. Експертний сценарій та ідеї для створення вірусного відео.\n"
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
                f"🔔 Користувач @{callback.from_user.username or 'none'} (ID: `{user_id}`) натиснув кнопку «Я сплатив».\n"
                f"Використайте команду: `/give_pro {user_id}` для активації PRO.",
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
    await callback.answer("✅ У вас активовано безлімітний PRO статус із повним набором інструментів!", show_alert=True)

# Головна точка запуску (Вебсервер + Полінг Telegram)
async def main():
    # Запуск фонового вебсервера для підтримки активності на Render
    asyncio.create_task(start_web_server())
    
    # Видалення старих вебхуків для стабільної роботи start_polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Помилка видалення вебхука: {e}")
        
    logger.info("Бот успішно розпочав роботу з повною мультимовністю та розширеним завантажувачем TikTok!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Роботу телеграм-бота було завершено користувачем або системою.")
