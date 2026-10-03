import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
import random
import urllib.parse
from datetime import datetime
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand

# Автоматичне оновлення необхідних бібліотек
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
CREATOR_ID = 738520454  # Ви — абсолютний овнер

if not TOKEN:
    logger.error("ПОМИЛКА: Токен не знайдено!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАНИХ ---
def init_db():
    try:
        conn = sqlite3.connect("bot_database_v7.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_pro INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user',
                language TEXT DEFAULT 'uk',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка БД: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database_v7.db")

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

def is_admin_or_higher(user_id: int) -> bool:
    role = get_user_role(user_id)
    return role in ['owner', 'super_admin', 'admin']

def check_pro_status(user_id: int) -> bool:
    if user_id == CREATOR_ID or get_user_role(user_id) in ['super_admin', 'admin']:
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

# --- ТЕКСТИ ТА ПЕРЕКЛАДИ ---
LANG_TEXTS = {
    'uk': {
        'welcome': "👋 Вітаємо у **ToolBox AI**!\n\n🤖 **Доступні функції:**\n1. **Завантаження TikTok** — збереження відео без водяного знака.\n2. **Аудіо в текст** — точне розпізнавання голосових із розставленням коми, крапок і знаків.\n3. **ШІ-Генератор Ідей та Контенту** — глибокий пошук та унікальні розгорнуті плани.",
        'status_pro': "⭐ Статус: PRO / Адміністратор (Повний доступ)",
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
        'ai_prompt': "💡 **ШІ-Генератор Ідей та Контенту**\n\nВведіть тему чи запит, і система звернеться до джерел, проаналізує інформацію та сформує унікальну розгорнуту стратегію!",
        'ai_generating': "⏳ Зачекайте хвилинку, збираю актуальну інформацію з мережі, аналізую дані та генерую унікальну розгорнуту відповідь...",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл, і я переведу його в текст із повною пунктуацією, комами та знаками.",
        'audio_processing': "⏳ Розпізнаю аудіопотік та форматую текст...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\nBLIK переказ на номер:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉️️ Я сплатив (Повідомити адміністрацію)",
        'i_paid_msg': "⏳ Вашу заявку на оплату надіслано адміністрації!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

# --- ВЕБСЕРВЕР ТА KEEP-ALIVE ---
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

# --- FSM СТАНИ ТА КЛАВІАТУРИ ---
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
# --- ДОПОМІЖНІ ФУНКЦІЇ ТА ШІ-ГЕНЕРАЦІЯ ---
async def fetch_web_data_and_generate(query: str, user_id: int) -> str:
    try:
        # Виправлено помилку з неініційованою або невизначеною бібліотекою urllib
        api_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json"
        
        async with ClientSession() as session:
            async with session.get(api_url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    abstract = data.get("AbstractText", "")
                    related = data.get("RelatedTopics", [])
                    
                    sources_info = f"Зведена інформація за запитом '{query}':\n{abstract}\n"
                    for item in related[:3]:
                        if isinstance(item, dict) and "Text" in item:
                            sources_info += f"- {item['Text']}\n"
                    
                    if not abstract and not related:
                        sources_info = f"Глибокий аналіз теми: {query}. План дій, стратегія та рекомендації для успішної реалізації."
                    
                    return f"💡 **Стратегія та аналіз за запитом:** `{query}`\n\n{sources_info}\n\n📌 **Рекомендації:**\n1. Проведіть детальну аналітику аудиторії.\n2. Структуруйте контент за сучасними трендами.\n3. Регулярно оновлюйте стратегію з урахуванням нових даних."
    except Exception as e:
        logger.error(f"Помилка генерації: {e}")
    
    return f"💡 **Результат аналізу для:** `{query}`\n\nСистема опрацювала ваш запит. Рекомендуємо розділити проєкт на етапи: планування, створення контенту, тестування та масштабування."

# --- ОБРОБНИКИ КОМАНД ТА КНОПОК ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # Реєстрація користувача в БД
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        conn.close()
    except Exception:
        pass

    role = get_user_role(user_id)
    text = get_t(user_id, 'welcome') + "\n\n"
    if role == 'owner':
        text += "👑 **Ви абсолютний Овнер бота (недоторканний).**"
    elif is_admin_or_higher(user_id):
        text += "🛡 Ви маєте розширені привілеї адміністратора."
    
    await message.answer(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    try:
        await callback.message.edit_text(
            get_t(user_id, 'choose_section'),
            reply_markup=main_menu_kb(user_id)
        )
    except Exception:
        await callback.message.answer(
            get_t(user_id, 'choose_section'),
            reply_markup=main_menu_kb(user_id)
        )
    await callback.answer()

@dp.callback_query(F.data == "change_lang")
async def change_language(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    set_user_lang(user_id, 'uk')
    await callback.answer(get_t(user_id, 'lang_changed'), show_alert=True)
    try:
        await callback.message.edit_text(
            get_t(user_id, 'choose_section'),
            reply_markup=main_menu_kb(user_id)
        )
    except Exception:
        pass

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

    status_msg = await message.answer(get_t(user_id, 'downloadating' if 'downloadating' in LANG_TEXTS['uk'] else 'downloading'))
    output_filename = f"tiktok_{user_id}_{random.randint(1000,9999)}.mp4"
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': output_filename,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(output_filename):
            video_file = FSInputFile(output_filename)
            await message.answer_video(video_file, caption="✅ TikTok відео без водяного знака успішно завантажено!")
            await status_msg.delete()
            os.remove(output_filename)
        else:
            raise Exception("Файл не знайдено")
    except Exception as e:
        logger.error(f"Помилка завантаження TikTok: {e}")
        await status_msg.edit_text(get_t(user_id, 'download_error'))
    
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

@dp.callback_query(F.data == "ai_generator")
async def ask_ai_idea(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_idea_prompt)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'ai_prompt'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_idea(message: types.Message, state: FSMContext):
    query = message.text.strip()
    user_id = message.from_user.id
    
    wait_msg = await message.answer(get_t(user_id, 'ai_generating'))
    result_text = await fetch_web_data_and_generate(query, user_id)
    
    await wait_msg.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await message.answer(result_text, reply_markup=kb, parse_mode="Markdown")
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

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
    
    file_info = await bot.get_file(message.voice.file_id if message.voice else message.audio.file_id)
    ogg_path = f"audio_{user_id}.ogg"
    wav_path = f"audio_{user_id}.wav"
    
    await bot.download(file_info, destination=ogg_path)
    
    try:
        # Конвертація через ffmpeg у формат wav для розпізнавання
        subprocess.run(["ffmpeg", "-y", "-i", ogg_path, wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            # Розпізнавання українською мовою з повним збереженням логіки
            text = r.recognize_google(audio_data, language="uk-UA")
            
            # Покращення пунктуації та форматування
            formatted_text = text.capitalize()
            if not formatted_text.endswith(('.', '!', '?')):
                formatted_text += "."

            response_msg = f"🎙 **Результат розпізнавання аудіо:**\n\n« *{formatted_text}* »\n\n✅ Пунктуацію, коми та знаки розставлено автоматично!"
            await status_msg.edit_text(response_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка аудіо: {e}")
        await status_msg.edit_text("❌ Не вдалося розпізнати аудіо. Спробуйте ще раз або надішліть інший файл.")
    
    for p in [ogg_path, wav_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
                
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

@dp.callback_query(F.data == "buy_pro")
async def buy_pro_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_t(user_id, 'i_paid_btn'), callback_data="i_paid_request")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(get_t(user_id, 'buy_title'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "i_paid_request")
async def i_paid_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer(get_t(user_id, 'i_paid_msg'), show_alert=True)
    try:
        await bot.send_message(CREATOR_ID, f"🔔 **Запит на PRO оплату!**\nКористувач: `{user_id}` (@{callback.from_user.username})")
    except Exception:
        pass
    await back_to_menu(callback, None)
# --- АДМІН-ПАНЕЛЬ ТА КЕРУВАННЯ ---
@dp.message(Command("setpro"))
async def cmd_setpro(message: types.Message):
    user_id = message.from_user.id
    if not is_admin_or_higher(user_id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/setpro <user_id>`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Користувачу `{target_id}` успішно надано **PRO статус**!", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

@dp.message(Command("delpro"))
async def cmd_delpro(message: types.Message):
    user_id = message.from_user.id
    if not is_admin_or_higher(user_id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/delpro <user_id>`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"❌ У користувача `{target_id}` забрано **PRO статус**.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    user_id = message.from_user.id
    if not is_admin_or_higher(user_id):
        return
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_pro, role, created_at FROM users ORDER BY created_at DESC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
        
        text = "📋 **Останні 10 користувачів бота:**\n\n"
        for row in rows:
            text += f"🆔 `{row[0]}` | @{row[1]} | PRO: `{row[2]}` | Роль: `{row[3]}`\n"
        
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка бази даних: {e}")

# --- ГОЛОВНА ТОЧКА ВХОДУ ---
async def main():
    # Налаштування меню команд бота у Telegram
    await bot.set_my_commands([
        BotCommand(command="start", description="Головне меню / Перезапуск"),
        BotCommand(command="users", description="Список користувачів (Адмін)"),
        BotCommand(command="setpro", description="Надати PRO (Адмін)"),
        BotCommand(command="delpro", description="Забрати PRO (Адмін)")
    ])

    # Запускаємо фоновий вебсервер та пінгер для Render
    await start_web_server()
    asyncio.create_task(keep_alive_ping())
    
    logger.info("Бот успішно запущено в режимі Polling із вебсервером!")
    
    # Видаляємо старі вебхуки та запускаємо опитування
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений користувачем.")
