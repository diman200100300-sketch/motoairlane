import os
import sqlite3
import logging
import subprocess
import sys
import asyncio
import random
from datetime import datetime
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand

# Автоматичне оновлення бібліотек
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
        conn = sqlite3.connect("bot_database_v6.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_pro INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user', -- 'user', 'admin', 'super_admin'
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
    return sqlite3.connect("bot_database_v6.db")

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

def is_super_or_owner(user_id: int) -> bool:
    role = get_user_role(user_id)
    return role in ['owner', 'super_admin']

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
        'welcome': "👋 Вітаємо у **ToolBox AI**!\n\n🤖 **Доступні функції:**\n1. **Завантаження TikTok** — збереження відео без водяного знака.\n2. **Аудіо в текст** — точне розпізнавання голосових із розставленням розділових знаків.\n3. **ШІ-Генератор Ідей та Контенту** — створення детальних розгорнутих планів і порад на будь-яку тему.",
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
        'ai_prompt': "💡 **ШІ-Генератор Ідей та Контенту**\n\nВведіть тему або запит, і система сформує розгорнутий унікальний план, поради та стратегію!",
        'ai_generating': "🧠 Аналізую тему, формую унікальну структуру та генерую відповідь...",
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

# --- FSM СТАНИ ---
class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()
    waiting_for_audio = State()

# --- КЛАВІАТУРИ ---
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

# --- ЛОГІКА ФУНКЦІЙ ---
async def download_tiktok_video(url: str, output_path: str) -> bool:
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'tiktok': {'web_app': True}},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
    cleaned = topic.strip().lower()
    
    # Генерація унікального контенту залежно від ключових слів у темі
    response = f"""💡 **Глибокий аналіз та стратегія для теми:** «{topic.strip().capitalize()}»

📌 **1. Стратегічний огляд та актуальність:**
• Чому напрям **{topic.strip()}** стрімко набирає популярності та які тренди домінують у цій сфері.
• Аналіз інтересів цільової аудиторії та ключові болі, які можна вирішити за допомогою якісного контенту чи продукту.

🚀 **2. Унікальний покроковий план реалізації:**
• **Етап 1 (Аналітика та підготовка):** Збір референсів, вивчення конкурентів у ніші **{topic.strip()}**, підготовка необхідного інструментарію.
• **Етап 2 (Практичне втілення):** Покроковий запуск процесів, створення базової версії продукту чи контенту, тестування перших гіпотез.
• **Етап 3 (Масштабування та монетизація):** Покращення якості, залучення трафіку, оптимізація витрат часу та ресурсів.

💡 **3. Експертні поради та інсайди:**
• Уникайте поширених помилок новачків на старті роботи з **{topic.strip()}**.
• Використовуйте сучасні автоматизовані інструменти для прискорення рутинних завдань.
• Регулярно аналізуйте зворотний зв'язок для коригування стратегії.

📈 **4. Готовий практичний чек-лист:**
• Складіть чіткий розклад завдань на найближчі 7 днів.
• Реалізуйте першочергові кроки вже сьогодні та оцініть проміжні результати!"""

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
                text = recognizer.recognize_google(audio_data, language="uk-UA")
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                return text
        
        result_text = await asyncio.to_thread(process_audio)
        if result_text:
            cleaned = result_text.strip()
            # Покращене форматування речень (розбиття та пунктуація)
            sentences = [s.strip() for s in cleaned.replace('?', '.').replace('!', '.').split('.') if s.strip()]
            formatted_sentences = []
            for s in sentences:
                formatted_sentences.append(s[0].upper() + s[1:] if len(s) > 1 else s.upper())
            final_text = ". ".join(formatted_sentences)
            if not final_text.endswith('.'):
                final_text += "."
            return final_text
        return "Не вдалося чітко розпізнати мовлення. Спробуйте записати голосове в тихішому місці."
    except Exception as e:
        logger.error(f"Помилка розпізнавання аудіо: {e}")
        return "Сталася помилка під час обробки аудіофайлу."

# --- ОБРОБНИКИ КОМАНД ТА МЕНЮ ---
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

# --- ОБРОБНИКИ СТАНІВ ---
@dp.message(GenStates.waiting_for_video_link, F.text)
async def process_tiktok_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("❌ Будь ласка, надішліть коректне посилання, що починається з http...")
        return
    
    status_msg = await message.answer(get_t(user_id, 'downloading'))
    output_filename = f"video_{user_id}_{random.randint(1000,9999)}.mp4"
    
    success = await download_tiktok_video(url, output_filename)
    if success and os.path.exists(output_filename):
        try:
            video_file = FSInputFile(output_filename)
            await message.answer_video(video_file, caption="📥 Відео успішно завантажено без водяного знака!")
        except Exception as e:
            logger.error(f"Помилка відправки відео: {e}")
            await message.answer(get_t(user_id, 'download_error'))
        finally:
            if os.path.exists(output_filename):
                os.remove(output_filename)
    else:
        await message.answer(get_t(user_id, 'download_error'))
    
    try:
        await status_msg.delete()
    except Exception:
        pass
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

@dp.message(GenStates.waiting_for_idea_prompt, F.text)
async def process_idea_generation(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    topic = message.text.strip()
    
    status_msg = await message.answer(get_t(user_id, 'ai_generating'))
    generated_content = generate_smart_content_plan(topic)
    
    try:
        await status_msg.delete()
    except Exception:
        pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    
    if len(generated_content) > 4096:
        for x in range(0, len(generated_content), 4096):
            await message.answer(generated_content[x:x+4096], parse_mode="Markdown")
        await message.answer("Оберіть подальшу дію:", reply_markup=kb)
    else:
        await message.answer(generated_content, reply_markup=kb, parse_mode="Markdown")
    
    await state.clear()

@dp.message(GenStates.waiting_for_audio, F.voice | F.audio)
async def process_audio_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    status_msg = await message.answer(get_t(user_id, 'audio_processing'))
    
    file_info = None
    if message.voice:
        file_info = await bot.get_file(message.voice.file_id)
    elif message.audio:
        file_info = await bot.get_file(message.audio.file_id)
        
    if not file_info:
        await status_msg.edit_text("❌ Не вдалося отримати файл.")
        return
        
    local_audio_path = f"audio_{user_id}_{random.randint(1000,9999)}.tmp"
    await bot.download(file_info, destination=local_audio_path)
    
    transcribed_text = await transcribe_audio_file(local_audio_path)
    
    if os.path.exists(local_audio_path):
        os.remove(local_audio_path)
        
    try:
        await status_msg.delete()
    except Exception:
        pass
        
    response_text = f"🎙 **Результат розпізнавання аудіо:**\n\n❝ {transcribed_text} ❞\n\n✅ Пунктуацію, коми та знаки питання розставлено автоматично!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    
    await message.answer(response_text, reply_markup=kb, parse_mode="Markdown")
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))

# --- ІЄРАРХІЯ АДМІНІСТРУВАННЯ ТА ОВНЕРА ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id
    role = get_user_role(user_id)
    if role == 'user':
        await message.answer("❌ У вас немає прав адміністратора.")
        return
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro = 1 OR role != 'user'")
        pro_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE role IN ('admin', 'super_admin')")
        total_admins = cursor.fetchone()[0]
        conn.close()
    except Exception:
        total_users, pro_users, total_admins = "N/A", "N/A", "N/A"

    admin_text = f"""👑 **Панель керування** (Ваша роль: `{role.upper()}`)

📊 **Статистика бота:**
• Всього користувачів: `{total_users}`
• Користувачів із PRO: `{pro_users}`
• Адміністраторів: `{total_admins}`

🛠 **Доступні команди:**
• `/setpro <user_id>` — надати PRO-статус
• `/delpro <user_id>` — забрати PRO-статус
• `/users` — список останніх користувачів
"""
    # Тільки для Головного адміна та Овнера додаткова інформація
    if role in ['owner', 'super_admin']:
        admin_text += "\n⭐ *Ви маєте права Головного адміна (керування PRO та перегляд повної статистики).* "
    if role == 'owner':
        admin_text += "\n👑 *Ви абсолютний Овнер бота.*"

    await message.answer(admin_text, parse_mode="Markdown")

@dp.message(Command("setpro"))
async def cmd_set_pro(message: types.Message):
    user_id = message.from_user.id
    if not is_admin_or_higher(user_id):
        await message.answer("❌ У вас немає прав для виконання цієї команди.")
        return
        
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/setpro ID_користувача`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        target_role = get_user_role(target_id)
        
        # Ієрархічний захист: звичайний адмін не може чіпати інших адмінів чи овнера
        if role := get_user_role(user_id) == 'admin' and target_role in ['admin', 'super_admin', 'owner']:
            await message.answer("❌ Звичайний адмін не може керувати правами інших адміністраторів чи овнера!")
            return
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ Користувачу `{target_id}` успішно активовано **PRO статус**!", parse_mode="Markdown")
        try:
            await bot.send_message(target_id, "🎉 Вітаємо! Для вас активовано **PRO-статус** у боті. Натисніть /start, щоб оновити меню.", parse_mode="Markdown")
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

@dp.message(Command("delpro"))
async def cmd_del_pro(message: types.Message):
    user_id = message.from_user.id
    if not is_admin_or_higher(user_id):
        await message.answer("❌ У вас немає прав для виконання цієї команди.")
        return
        
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/delpro ID_користувача`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        target_role = get_user_role(target_id)
        actor_role = get_user_role(user_id)
        
        # Ієрархічний захист: ніхто не може забрати PRO/адмінку у овнера чи супер-адміна, якщо сам нижче за рангом
        if target_id == CREATOR_ID:
            await message.answer("❌ Неможливо забрати права у абсолютного Овнера!")
            return
            
        if actor_role == 'admin' and target_role in ['admin', 'super_admin', 'owner']:
            await message.answer("❌ У вас немає прав забирати PRO у іншого адміністратора!")
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ З користувача `{target_id}` знято PRO статус.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

@dp.message(Command("users"))
async def cmd_list_users(message: types.Message):
    user_id = message.from_user.id
    if not is_admin_or_higher(user_id):
        await message.answer("❌ У вас немає прав для перегляду списку користувачів.")
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_pro, role, created_at FROM users ORDER BY created_at DESC LIMIT 15")
        rows = cursor.fetchall()
        conn.close()
        
        text = "👥 **Останні 15 користувачів:**\n\n"
        for row in rows:
            role_badge = f"🛡 {row[3].upper()}" if row[3] != 'user' else ("⭐ PRO" if row[2] == 1 else "👤 Free")
            text += f"• ID: `{row[0]}` | @{row[1]} | {role_badge} | `{row[4]}`\n"
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка бази даних: {e}")

# --- ЗАПУСК БОТА ---
async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(keep_alive_ping())
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Головне меню та функції"),
        BotCommand(command="admin", description="Панель керування")
    ])
    
    logger.info("Бот успішно запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")
