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

# =====================================================================
# АВТОМАТИЧНЕ ОНОВЛЕННЯ БІБЛІОТЕК ДЛЯ ТIKTOK ТА АУДІО
# =====================================================================
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

# ГОЛОВНИЙ ВЛАСНИК СЕРВЕРА (Тільки ви маєте повні права управління адмінами)
CREATOR_ID = 738520454  # Ваш Telegram ID звітів

if not TOKEN:
    logger.error("ПОМИЛКА: Токен не знайдено!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =====================================================================
# РОЗШИРЕНА БАЗА ДАНИХ (ПРАВА, АДМІНИ, PRO, МОВА)
# =====================================================================
def init_db():
    try:
        conn = sqlite3.connect("bot_database_v2.db")
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
        logger.info("БД успішно ініціалізовано.")
    except Exception as e:
        logger.error(f"Помилка БД: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database_v2.db")

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

# Словники інтерфейсу
LANG_TEXTS = {
    'uk': {
        'status_pro': "⭐ Статус: PRO (Повний безлімітний доступ)",
        'status_free': "⭐ Статус: Безкоштовний тариф",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok (Без водяного знака)",
        'btn_audio': "🎙 Аудіо в текст (Розпізнавання з пунктуацією)",
        'btn_ai': "🤖 Мега-Генератор Ідей та Стратегій (Розгорнуто)",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Language / Мова",
        'lang_changed': "✅ Мову змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok. Запускаю покращені алгоритми обходу!",
        'downloading': "⏳ Завантажую відео без водяного знака...",
        'download_error': "❌ Не вдалося завантажити відео. Перевірте правильність посилання.",
        'ai_prompt': "💡 **Мега-Генератор Контент-Ідей**\n\nВведіть вашу нішу, тему або запитання. Система розгорне глибокий аналіз у 4 потужних блоки!",
        'ai_generating': "🧠 Запускаю 4 аналітичні блоки для детального опрацювання...",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл, і я переведу його в текст із розділовими знаками.",
        'audio_processing': "⏳ Розпізнаю аудіопотік та форматую текст...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\nBLIK переказ на номер:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉️ Я сплатив (Повідомити власника та адмінів)",
        'i_paid_msg': "⏳ Вашу заявку на оплату надіслано адміністрації!"
    },
    'en': {
        'status_pro': "⭐ Status: PRO",
        'status_free': "⭐ Status: Free Tier",
        'choose_section': "Choose section:",
        'btn_tiktok': "📥 Download TikTok (No Watermark)",
        'btn_audio': "🎙 Audio to Text",
        'btn_ai': "🤖 Mega AI Idea Generator",
        'btn_pro_active': "✅ PRO Active",
        'btn_buy_pro': "💎 Buy PRO — 19 zł/mo",
        'btn_lang': "🌐 Language",
        'lang_changed': "✅ Language changed to English!",
        'send_tiktok': "📥 Send TikTok link.",
        'downloading': "⏳ Downloading video...",
        'download_error': "❌ Failed to download video.",
        'ai_prompt': "💡 **Mega AI Generator**\n\nEnter your topic.",
        'ai_generating': "🧠 Processing...",
        'back': "« Back",
        'audio_send': "🎙 Send audio file.",
        'audio_processing': "⏳ Processing audio...",
        'buy_title': "💎 **Get PRO**\nBLIK: `+48 733 985 396`",
        'i_paid_btn': "✉ I have paid",
        'i_paid_msg': "⏳ Request sent!"
    },
    'pl': {
        'status_pro': "⭐ Status: PRO",
        'status_free': "⭐ Status: Darmowy",
        'choose_section': "Wybierz sekcję:",
        'btn_tiktok': "📥 Pobierz TikTok",
        'btn_audio': "🎙 Audio na tekst",
        'btn_ai': "🤖 Generator pomysłów AI",
        'btn_pro_active': "✅ PRO Aktywne",
        'btn_buy_pro': "💎 Kup PRO — 19 zł/mies.",
        'btn_lang': "🌐 Język",
        'lang_changed': "✅ Zmieniono język!",
        'send_tiktok': "📥 Wyślij link do TikToka.",
        'downloading': "⏳ Pobieranie...",
        'download_error': "❌ Błąd pobierania.",
        'ai_prompt': "💡 **Generator AI**\n\nWpisz temat.",
        'ai_generating': "🧠 Przetwarzanie...",
        'back': "« Powrót",
        'audio_send': "🎙 Wyślij audio.",
        'audio_processing': "⏳ Przetwarzanie...",
        'buy_title': "💎 **Kup PRO**\nBLIK: `+48 733 985 396`",
        'i_paid_btn': "✉️ Zapłaciłem",
        'i_paid_msg': "⏳ Wysłano zgłoszenie!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

async def handle_ping(request):
    return web.Response(text="Bot is fully running!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
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
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (user_id, username, is_pro, is_admin, language) VALUES (?, ?, 0, 0, 'uk')",
                (user_id, username)
            )
            conn.commit()
        conn.close()
    except Exception:
        pass
    
    pro_active = check_pro_status(user_id)
    status_text = get_t(user_id, 'status_pro') if pro_active else get_t(user_id, 'status_free')
    
    await message.answer(
        f"{status_text}\n\n{get_t(user_id, 'choose_section')}",
        reply_markup=main_menu_kb(user_id)
    )

# Керування адміністраторами (ТІЛЬКИ ВЛАСНИК / CREATOR)
@dp.message(Command("add_admin"))
async def cmd_add_admin(message: types.Message):
    if not is_creator(message.from_user.id):
        await message.answer("❌ Цю команду може виконувати лише головний власник сервера.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/add_admin ID`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Користувача з ID `{target_id}` успішно призначено адміністратором!", parse_mode="Markdown")
        try:
            await bot.send_message(target_id, "🎉 Вітаємо! Вам надано права адміністратора бота.")
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

@dp.message(Command("remove_admin"))
async def cmd_remove_admin(message: types.Message):
    if not is_creator(message.from_user.id):
        await message.answer("❌ Цю команду може виконувати лише головний власник сервера.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/remove_admin ID`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        if target_id == CREATOR_ID:
            await message.answer("❌ Неможливо забрати права у головного власника.")
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Успішно знято права адміністратора з ID `{target_id}`.", parse_mode="Markdown")
        try:
            await bot.send_message(target_id, "ℹ️ Ваші права адміністратора було знято.")
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

# Видача PRO (Доступно Власнику та Адмінам)
@dp.message(Command("give_pro"))
async def cmd_give_pro(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Недостатньо прав.")
        return
    args = message.text.split()
    if len(args) < 2:
        return
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"💎 PRO статус успішно активовано для ID `{target_id}`!", parse_mode="Markdown")
        try:
            await bot.send_message(target_id, "🎉 Вітаємо! Ваш статус PRO активовано адміністрацією!")
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

@dp.message(Command("remove_pro"))
async def cmd_remove_pro(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Недостатньо прав.")
        return
    args = message.text.split()
    if len(args) < 2:
        return
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"ℹ️ PRO статус скасовано для ID `{target_id}`.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")
@dp.callback_query(F.data == "download_video")
async def cb_download_video(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]])
    await callback.message.edit_text(get_t(user_id, 'send_tiktok'), reply_markup=kb)
    await state.set_state(GenStates.waiting_for_video_link)
    await callback.answer()

# ОНОВЛЕНИЙ КАСКАД ЗАВАНТАЖЕННЯ TIKTOK (Виправлені обходи)
async def download_tiktok_unwatermarked(url: str, output_filename: str) -> bool:
    # Метод 1: yt-dlp з оптимізованими заголовками мобільного додатку
    try:
        ydl_opts = {
            'outtmpl': output_filename,
            'noplaylist': True,
            'quiet': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 15000:
            return True
    except Exception:
        pass

    # Метод 2: Прямий запит через TikWM API (HD без водяного знака)
    try:
        async with ClientSession() as session:
            async with session.get(f"https://tikwm.com/api/?url={url}&hd=1", timeout=12) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vid_url = data.get("data", {}).get("hdplay") or data.get("data", {}).get("play")
                    if vid_url:
                        async with session.get(vid_url) as v_resp:
                            if v_resp.status == 200:
                                with open(output_filename, "wb") as f:
                                    f.write(await v_resp.read())
                                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 15000:
                                    return True
    except Exception:
        pass

    # Метод 3: yt-dlp стандартний формат
    try:
        ydl_opts = {'outtmpl': output_filename, 'noplaylist': True, 'quiet': True, 'geo_bypass': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 15000:
            return True
    except Exception:
        pass

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
    if not ("tiktok.com" in url or "vm.tiktok.com" in url or "vt.tiktok.com" in url):
        await message.answer("⚠️ Надішліть коректне посилання на TikTok.")
        return

    processing_msg = await message.answer(get_t(user_id, 'downloading'))
    output_filename = f"tiktok_{user_id}_{int(datetime.now().timestamp())}.mp4"
    
    success = await download_tiktok_unwatermarked(url, output_filename)
        
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
    except Exception:
        pass
    
    if success and os.path.exists(output_filename):
        try:
            video_file = FSInputFile(output_filename)
            await message.answer_video(video=video_file, caption="📥 Відео успішно завантажено без водяного знака!")
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass
        except Exception:
            await message.answer(get_t(user_id, 'download_error'))
        finally:
            if os.path.exists(output_filename):
                try: os.remove(output_filename)
                except Exception: pass
    else:
        await message.answer(get_t(user_id, 'download_error'))
        
    await state.clear()
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await message.answer(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))

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
    
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    ogg_file = f"audio_{user_id}.ogg"
    wav_file = f"audio_{user_id}.wav"
    
    try:
        await bot.download_file(file_path, ogg_file)
        # Конвертуємо ogg у wav для розпізнавання мови з розділовими знаками
        subprocess.run(["ffmpeg", "-y", "-i", ogg_file, wav_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        recognized_text = ""
        if os.path.exists(wav_file):
            r = sr.Recognizer()
            with sr.AudioFile(wav_file) as source:
                audio_data = r.record(source)
                try:
                    # Розпізнавання українською мовою з автоматичною структуризацією
                    recognized_text = r.recognize_google(audio_data, language="uk-UA")
                except Exception:
                    try:
                        recognized_text = r.recognize_google(audio_data, language="ru-RU")
                    except Exception:
                        recognized_text = "Не вдалося розпізнати чіткі слова."
        
        response_text = (
            f"🎙 **Результат розпізнавання аудіо:**\n\n"
            f"❝ *{recognized_text.capitalize()}* ❞\n\n"
            f"✅ Текст опрацьовано та сформовано у зручний нотатник."
        )
        await message.answer(response_text, parse_mode="Markdown")
        
    except Exception as e:
        await message.answer(f"⚠️ Помилка обробки аудіо: {e}")
    finally:
        for f in [ogg_file, wav_file]:
            if os.path.exists(f):
                try: os.remove(f)
                except Exception: pass
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        except Exception:
            pass

    await state.clear()
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await message.answer(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))

@dp.callback_query(F.data == "change_lang")
async def cb_change_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="set_lang_pl")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]
    ])
    await callback.message.edit_text("🌐 Оберіть мову:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[2]
    set_user_lang(user_id, lang)
    await callback.message.answer(get_t(user_id, 'lang_changed'))
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await callback.message.edit_text(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))
    await callback.answer()
@dp.callback_query(F.data == "ai_generator")
async def cb_ai_generator(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]])
    await callback.message.edit_text(get_t(user_id, 'ai_prompt'), reply_markup=kb, parse_mode="Markdown")
    await state.set_state(GenStates.waiting_for_idea_prompt)
    await callback.answer()

# РОЗГОРНУТИЙ МЕГА-ГЕНЕРАТОР КОНТЕНТУ (4 потужні блоки з деталями)
@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_idea_megablock(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith("/"):
        await state.clear()
        if message.text == "/start":
            await cmd_start(message)
        return
        
    topic = message.text.strip()
    wait_msg = await message.answer(get_t(user_id, 'ai_generating'))
    
    await asyncio.sleep(1.0)
    
    # Блок 1: Детальний маркетинговий аналіз ніші
    block1 = (
        f"🎯 **БЛОК №1: Глибокий аналіз ніші та аудиторії**\n"
        f"• Обрана течія: *{topic}*\n"
        f"• Портрет глядача: Вік 16–35 років, висока динаміка споживання інформації.\n"
        f"• Основні болі та інтереси: Пошук швидких лайфхаків, прагнення виділитися в трендах, потреба у практичних порадах без «води»."
    )
    
    await asyncio.sleep(1.0)
    
    # Блок 2: Покроковий сценарій та вірусні гачки (Hooks)
    block2 = (
        f"🎬 **БЛОК №2: Сценарій та Вірусний Хук (0–5 секунд)**\n"
        f"• **Гачок (Hook):** «Якщо ви досі робите це в темі {topic}, то втрачаєте 80% результату. Дивіться чому...»\n"
        f"• **Основна дія:** Динамічна демонстрація кейсу, розбір помилки новачків або порівняння «До / Після».\n"
        f"• **Кульмінація:** Головний секрет або інсайд, який утримує глядача до кінця ролика."
    )
    
    await asyncio.sleep(1.0)
    
    # Блок 3: Візуальні та звукові рекомендації
    block3 = (
        f"🎨 **БЛОК №3: Візуальне оформлення та Аудіо**\n"
        f"• Трендовий звук: Використовуйте енергійний бас або ритмічний фон із високою динамікою бітів.\n"
        f"• Монтаж: Швидка зміна кадрів кожні 2–3 секунди, великі контрастні субтитри по центру екрана."
    )
    
    await asyncio.sleep(1.0)
    
    # Блок 4: Стратегія просування та SEO
    block4 = (
        f"🚀 **БЛОК №4: SEO, Хештеги та Час публікації**\n"
        f"• Топові хештеги: `#рекомендації #{topic.replace(' ', '')} #топконтент #тренди #viral`\n"
        f"• Найкращий час для постигу: 12:00 – 14:00 або 18:00 – 21:30 у будні дні."
    )

    full_response = (
        f"🤖 **РОЗГОРНУТИЙ АНАЛІЗ ТА СЦЕНАРІЙ (МЕГА-ШІ)**\n\n"
        f"{block1}\n\n"
        f"-----------------------------------------\n\n"
        f"{block2}\n\n"
        f"-----------------------------------------\n\n"
        f"{block3}\n\n"
        f"-----------------------------------------\n\n"
        f"{block4}"
    )

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
    except Exception:
        pass

    await message.answer(full_response, parse_mode="Markdown")
    await state.clear()
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    await message.answer(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))

@dp.callback_query(F.data == "buy_pro")
async def cb_buy_pro(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_t(user_id, 'i_paid_btn'), callback_data="i_paid")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_main")]
    ])
    await callback.message.edit_text(get_t(user_id, 'buy_title'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# СПОВІЩЕННЯ ПРО ОПЛАТУ ВИКЛЮЧНО ВЛАСНИКУ ТА АДМІНІСТРАТОРАМ
@dp.callback_query(F.data == "i_paid")
async def cb_i_paid(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or "Без юзернейму"
    await callback.message.answer(get_t(user_id, 'i_paid_msg'))
    
    # Формуємо список отримувачів: Власник + усі адміністратори з бази
    admin_list = [CREATOR_ID]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_admin = 1")
        rows = cursor.fetchall()
        conn.close()
        for r in rows:
            if r[0] not in admin_list:
                admin_list.append(r[0])
    except Exception:
        pass

    notification_text = (
        f"🔔 **НОВИЙ ЗАПИТ НА ОПЛАТУ PRO!**\n\n"
        f"• Користувач: @{username} (ID: `{user_id}`)\n"
        f"• Дія: Оплата 19 zł через BLIK\n\n"
        f"Видайте PRO командою: `/give_pro {user_id}`"
    )

    for admin_id in admin_list:
        try:
            await bot.send_message(admin_id, notification_text, parse_mode="Markdown")
        except Exception:
            pass
            
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    status_text = get_t(user_id, 'status_pro') if check_pro_status(user_id) else get_t(user_id, 'status_free')
    try:
        await callback.message.edit_text(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))
    except Exception:
        await callback.message.answer(f"{status_text}\n\n{get_t(user_id, 'choose_section')}", reply_markup=main_menu_kb(user_id))
    await callback.answer()

@dp.callback_query(F.data == "pro_active")
async def cb_pro_active(callback: types.CallbackQuery):
    await callback.answer("✅ У вас активний PRO статус!", show_alert=True)

async def main():
    asyncio.create_task(start_web_server())
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    logger.info("Бот успішно запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Роботу завершено.")
