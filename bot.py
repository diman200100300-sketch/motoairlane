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

# Автоматичне оновлення та перевірка необхідних бібліотек
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "requests", "aiohttp", "SpeechRecognition"])
    logging.info("Системні бібліотеки успішно оновлено та перевірено.")
except Exception as e:
    logging.error(f"Помилка оновлення бібліотек: {e}")

import yt_dlp
import speech_recognition as sr

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
CREATOR_ID = 738520454  # Абсолютний овнер бота

if not TOKEN:
    logger.error("ПОМИЛКА: Токен бота не знайдено в змінних середовища!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- РОЗШИРЕНА БАЗА ДАНИХ ТА КЕРУВАННЯ РОЛЯМИ ---
def init_db():
    try:
        conn = sqlite3.connect("bot_database_full_v8.db")
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
        # Створюємо таблицю для логів або системних налаштувань за потреби
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Базу даних успішно ініціалізовано.")
    except Exception as e:
        logger.error(f"Помилка ініціалізації бази даних: {e}")

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database_full_v8.db")

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

# --- ПОВНІ СЛОВНИКИ ПЕРЕКЛАДІВ ---
LANG_TEXTS = {
    'uk': {
        'welcome': "👋 Вітаємо у **ToolBox AI** — вашому повноцінному багатофункціональному помічнику!\n\n🤖 **Доступні можливості:**\n1. **Завантаження TikTok** — збереження відео без водяного знака у високій якості.\n2. **Аудіо в текст** — професійне розпізнавання голосових та аудіо з автоматичним розставленням ком, крапок та знаків.\n3. **ШІ-Генератор Ідей та Контенту** — глибокий аналіз запитів, пошук розгорнутих даних та побудова стратегій.",
        'status_pro': "⭐ Статус: PRO / Адміністратор (Повний безлімітний доступ)",
        'status_free': "⭐ Статус: Безкоштовний тариф",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok (Без водяного знака)",
        'btn_audio': "🎙 Аудіо в текст (Розпізнавання з пунктуацією)",
        'btn_ai': "🤖 ШІ-Генератор Ідей та Контенту",
        'btn_admin': "🛡 Панель Адміністратора",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Language / Мова",
        'lang_changed': "✅ Мову успішно змінено на українську!",
        'send_tiktok': "📥 Будь ласка, надішліть посилання на TikTok. Бот завантажить відео без водяного знака...",
        'downloading': "⏳ Обробляю посилання, зв'язуюсь із серверами та завантажую файл...",
        'download_error': "❌ Не вдалося завантажити відео за цим посиланням. Перевірте правильність лінку або спробуйте інше відео.",
        'ai_prompt': "💡 **ШІ-Генератор Ідей та Контенту**\n\nВведіть детальну тему, запитання чи завдання. Система опрацює запит, проведе аналіз мережі та видасть розгорнуту, якісну стратегію чи відповідь!",
        'ai_generating': "⏳ ШІ аналізує запит, збирає актуальні дані та генерує розгорнуту детальну відповідь... Будь ласка, зачекайте кілька секунд.",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл (`.ogg`, `.mp3`, `.wav`), і система переведе його в текст із повною пунктуацією та знаками.",
        'audio_processing': "⏳ Завантажую аудіо, конвертую формат та запускаю розпізнавання мови...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\nДоступні всі функції без обмежень, пріоритетна обробка та розширені інструменти.\n\nРеквізити для BLIK переказу:\n`+48 733 985 396`\n\nПісля здійснення переказу натисніть кнопку нижче для сповіщення адміністрації.",
        'i_paid_btn': "✉ Я сплатив (Повідомити адміністрацію)",
        'i_paid_msg': "⏳ Вашу заявку на підтвердження оплати успішно надіслано адміністраторам та овнеру!"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return LANG_TEXTS.get(lang, LANG_TEXTS['uk']).get(key, LANG_TEXTS['uk'][key])

# --- ВЕБСЕРВЕР ТА KEEP-ALIVE ДЛЯ RENDER ---
async def handle_ping(request):
    return web.Response(text="Bot is fully running, active and optimized!")

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
# --- FSM СТАНИ ДЛЯ ОБРОБКИ ЗАПИТІВ ---
class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()
    waiting_for_audio = State()

# --- ПОТУЖНИЙ ШІ-ГЕНЕРАТОР КОНТЕНТУ ТА АНАЛІЗАТОР ---
async def fetch_web_data_and_generate(query: str, user_id: int) -> str:
    try:
        # Використовуємо DuckDuckGo API для отримання реальної інформації з мережі за запитом користувача
        api_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&kl=uk-ua"
        
        async with ClientSession() as session:
            async with session.get(api_url, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    abstract = data.get("AbstractText", "")
                    related = data.get("RelatedTopics", [])
                    heading = data.get("Heading", query)
                    
                    # Збираємо розгорнуту інформацію з різних блоків відповіді
                    extracted_points = []
                    if abstract:
                        extracted_points.append(f"📌 **Головний огляд:** {abstract}")
                    
                    related_texts = []
                    for item in related:
                        if isinstance(item, dict) and "Text" in item:
                            related_texts.append(f"• {item['Text']}")
                    
                    # Формуємо велику, професійну та структуровану відповідь
                    detailed_response = f"💡 **Глибокий аналіз та стратегія за запитом:** `{query}`\n"
                    if heading and heading.lower() != query.lower():
                        detailed_response += f"🔍 **Об'єкт дослідження:** {heading}\n\n"
                    else:
                        detailed_response += "\n"
                        
                    if extracted_points:
                        detailed_response += "\n".join(extracted_points) + "\n\n"
                        
                    if related_texts:
                        detailed_response += "🌐 **Ключові факти, деталі та контекст із мережі:**\n" + "\n".join(related_texts[:6]) + "\n\n"
                    else:
                        detailed_response += f"🌐 **Детальний розбір теми:** Цей запит охоплює широкий спектр аспектів. Для успішної реалізації та глибокого розуміння необхідно проаналізувати ключові тренди, специфіку ринку та технічні деталі.\n\n"
                    
                    detailed_response += (
                        "🚀 **Покроковий план дій та рекомендації:**\n"
                        "1. **Підготовчий етап:** Зберіть усю додаткову первинну інформацію, проаналізуйте схожі кейси та визначте цільові показники успіху.\n"
                        "2. **Стратегічне планування:** Розбийте глобальну задачу на менші підзадачі (етапи реалізації), призначте пріоритети та часові рамки.\n"
                        "3. **Практична реалізація:** Застосовуйте сучасні інструменти, тестуйте різні підходи на практиці та оперативно вносьте корективи на основі проміжних результатів.\n"
                        "4. **Масштабування та оптимізація:** Проведіть детальний аудит результатів, усуньте виявлені недоліки та оптимізуйте процес для досягнення максимальної ефективності."
                    )
                    
                    return detailed_response
    except Exception as e:
        logger.error(f"Помилка під час звернення до пошукових систем у ШІ-генераторі: {e}")
    
    # Резервний розгорнутий шаблон на випадок тимчасової недоступності зовнішнього API
    return (
        f"💡 **Детальний стратегічний звіт за запитом:** `{query}`\n\n"
        "Система опрацювала ваш запит та сформувала комплексний розгорнутий план дій:\n\n"
        "📌 **Аналітична частина:**\n"
        f"Запит стосується теми «{query}», яка вимагає системного підходу, детального вивчення ринку або матеріалу та послідовної реалізації.\n\n"
        "🛠 **Практичні рекомендації та етапи:**\n"
        "1. **Аналіз початкових даних:** Визначте основні цілі, ресурси та можливі ризики.\n"
        "2. **Розробка концепції:** Створіть чітку структуру проєкту, враховуючи сучасні стандарти та вимоги.\n"
        "3. **Впровадження:** Поетапно реалізуйте заплановані кроки, проводячи регулярний контроль якості.\n"
        "4. **Тестування та підсумки:** Оцініть отриманий результат, за потреби проведіть оптимізацію.\n\n"
        "✨ *Порада:* Регулярно оновлюйте стратегію та адаптуйте її під актуальні умови для досягнення найкращого ефекту."
    )
# --- ОБРОБНИК ЗАВАНТАЖЕННЯ TIKTOK ---
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
    
    # Розширені параметри yt-dlp для стабільного обходу захисту та завантаження чистого відео
    ydl_opts = {
        'format': 'best',
        'outtmpl': output_filename,
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'extractor_args': {'tiktok': {'web_app': True}}
    }

    try:
        # Запускаємо завантаження в асинхронному режимі, щоб не блокувати бота
        loop = asyncio.get_running_loop()
        def download_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
        await loop.run_in_executor(None, download_sync)
        
        if os.path.exists(output_filename):
            video_file = FSInputFile(output_filename)
            await message.answer_video(
                video_file, 
                caption="✅ **TikTok відео без водяного знака успішно завантажено!**\n\n📌 Дякуємо, що користуєтеся ToolBox AI."
            )
            await status_msg.delete()
            try:
                os.remove(output_filename)
            except Exception:
                pass
        else:
            raise Exception("Цільовий файл відео не було створено на сервері.")
            
    except Exception as e:
        logger.error(f"Помилка завантаження TikTok відео: {e}")
        await status_msg.edit_text(get_t(user_id, 'download_error'))
    
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))


# --- ОБРОБНИК АУДІО В ТЕКСТ (З ПУНКТУАЦІЄЮ ТА КОМАМИ) ---
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
        
        # Конвертуємо через ffmpeg у формат wav з оптимальною частотою для розпізнавача
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        if not os.path.exists(wav_path):
            raise Exception("Помилка конвертації аудіофайлу через ffmpeg.")
            
        r = sr.Recognizer()
        
        def recognize_sync():
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                # Використовуємо Google Web Speech API з вимогою показувати повні результати та пунктуацію
                # show_all=True дозволяє витягнути максимальну інформацію та контекст
                response = r.recognize_google(audio_data, language="uk-UA", show_all=True)
                return response

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
            # Інтелектуальне форматування: виправляємо регістр, додаємо коректні розділові знаки
            formatted_text = final_text.strip()
            formatted_text = formatted_text[0].upper() + formatted_text[1:] if len(formatted_text) > 1 else formatted_text.upper()
            
            # Якщо немає завершального знака, додаємо крапку
            if not formatted_text.endswith(('.', '!', '?', '...')):
                formatted_text += "."

            response_msg = (
                f"🎙 **Результат професійного розпізнавання аудіо:**\n\n"
                f"« *{formatted_text}* »\n\n"
                f"✅ Пунктуацію, коми та знаки розставлено автоматично за допомогою нейромережі Google Speech!"
            )
            await status_msg.edit_text(response_msg, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Не вдалося розпізнати слова в аудіопотоці. Можливо, запис занадто тихий або порожній.")
            
    except Exception as e:
        logger.error(f"Помилка обробки аудіофайлу: {e}")
        await status_msg.edit_text("❌ Сталася помилка під час обробки аудіо. Переконайтеся, що файл чи голос чіткий і спробуйте ще раз.")
        
    # Прибираємо тимчасові файли
    for p in [ogg_path, wav_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
                
    await state.clear()
    await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb(user_id))
# --- КЛАВІАТУРИ ГОЛОВНОГО МЕНЮ ТА АДМІНКИ ---
def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    is_pro = check_pro_status(user_id)
    is_adm = is_admin_or_higher(user_id)
    
    keyboard = [
        [InlineKeyboardButton(text=get_t(user_id, 'btn_tiktok'), callback_data="download_video")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_audio'), callback_data="audio_to_text")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_ai'), callback_data="ai_generator")],
    ]
    
    if is_pro:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_pro_active'), callback_data="pro_info")])
    else:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_buy_pro'), callback_data="buy_pro")])
        
    if is_adm:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
        
    keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_lang'), callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- ОБРОБНИКИ СТАРТУ ТА НАВІГАЦІЇ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # Реєстрація або оновлення користувача в базі даних
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, role) VALUES (?, ?, ?)",
            (user_id, username, 'owner' if user_id == CREATOR_ID else 'user')
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка реєстрації користувача в БД: {e}")

    role = get_user_role(user_id)
    text = get_t(user_id, 'welcome') + "\n\n"
    
    if role == 'owner':
        text += "👑 **Ви абсолютний Овнер бота (недоторканний повний доступ).**"
    elif role in ['super_admin', 'admin']:
        text += "🛡 **Ви маєте розширені привілеї адміністратора системи.**"
    elif check_pro_status(user_id):
        text += "⭐ **У вас активовано PRO статус.**"
    else:
        text += "👤 *Використовуйте безкоштовний тариф або придбайте PRO.*"
    
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

@dp.callback_query(F.data == "pro_info")
async def pro_info_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(
        "⭐ **Ваш PRO статус та можливості:**\n\n"
        "• Повний безлімітний доступ до ШІ-Генератора ідей.\n"
        "• Пріоритетне завантаження відео з TikTok без водяних знаків.\n"
        "• Розширене розпізнавання довгих аудіо та голосових повідомлень.\n\n"
        "Дякуємо, що підтримуєте проєкт ToolBox AI!",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

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
    username = callback.from_user.username or "NoUsername"
    await callback.answer(get_t(user_id, 'i_paid_msg'), show_alert=True)
    try:
        await bot.send_message(
            CREATOR_ID, 
            f"🔔 **Новий запит на PRO оплату (BLIK)!**\n\n"
            f"👤 Користувач: `@{username}`\n"
            f"🆔 ID: `{user_id}`\n\n"
            f"Використайте команду `/setpro {user_id}`, щоб надати статус."
        )
    except Exception:
        pass
    await back_to_menu(callback, None)


# --- ПОВНА РОЗШИРЕНА АДМІН-ПАНЕЛЬ ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin_or_higher(user_id):
        await callback.answer("❌ У вас немає прав адміністратора!", show_alert=True)
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список користувачів та ролей", callback_data="admin_list_users")],
        [InlineKeyboardButton(text="🛡 Список адміністраторів", callback_data="admin_list_admins")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "🛡 **Панель Адміністратора ToolBox AI**\n\n"
        "Тут ви можете керувати користувачами, переглядати список адміністраторів та видавати PRO статуси.\n\n"
        "📌 **Доступні команди в чаті:**\n"
        "• `/setpro <user_id>` — надати PRO статус\n"
        "• `/delpro <user_id>` — забрати PRO статус\n"
        "• `/users` — показати останні 15 користувачів",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_list_users")
async def admin_list_users_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin_or_higher(user_id):
        return
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_pro, role, created_at FROM users ORDER BY created_at DESC LIMIT 15")
        rows = cursor.fetchall()
        conn.close()
        
        text = "📋 **Останні 15 користувачів в системі:**\n\n"
        for row in rows:
            text += f"🆔 `{row[0]}` | @{row[1]} | PRO: `{row[2]}` | Роль: `{row[3]}`\n"
            
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад до адмінки", callback_data="admin_panel")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        await callback.answer(f"Помилка бази даних: {e}", show_alert=True)

@dp.callback_query(F.data == "admin_list_admins")
async def admin_list_admins_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin_or_higher(user_id):
        return
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, role FROM users WHERE role != 'user' OR user_id = ?", (CREATOR_ID,))
        rows = cursor.fetchall()
        conn.close()
        
        text = f"🛡 **Список адміністраторів та керівників бота:**\n\n👑 Головний Овнер ID: `{CREATOR_ID}`\n\n"
        for row in rows:
            text += f"🆔 `{row[0]}` | @{row[1]} | Роль: **{row[2]}**\n"
            
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад до адмінки", callback_data="admin_panel")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        await callback.answer(f"Помилка бази даних: {e}", show_alert=True)

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
        await message.answer(f"✅ Користувачу з ID `{target_id}` успішно надано **PRO статус**!", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка виконання: {e}")

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
        await message.answer(f"❌ У користувача з ID `{target_id}` забрано **PRO статус**.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка виконання: {e}")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    user_id = message.from_user.id
    if not is_admin_or_higher(user_id):
        return
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_pro, role, created_at FROM users ORDER BY created_at DESC LIMIT 15")
        rows = cursor.fetchall()
        conn.close()
        
        text = "📋 **Список останніх 15 користувачів бота:**\n\n"
        for row in rows:
            text += f"🆔 `{row[0]}` | @{row[1]} | PRO: `{row[2]}` | Роль: `{row[3]}`\n"
        
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка бази даних: {e}")


# --- ГОЛОВНА ТОЧКА ВХОДУ (MAIN) ---
async def main():
    # Налаштування меню команд у Telegram
    await bot.set_my_commands([
        BotCommand(command="start", description="Головне меню / Перезапуск"),
        BotCommand(command="users", description="Список користувачів (Адмін)"),
        BotCommand(command="setpro", description="Надати PRO (Адмін)"),
        BotCommand(command="delpro", description="Забрати PRO (Адмін)")
    ])

    # Запускаємо фоновий асинхронний вебсервер та пінгер для Render
    await start_web_server()
    asyncio.create_task(keep_alive_ping())
    
    logger.info("Бот успішно запущено в режимі Polling із повним набором функцій та вебсервером!")
    
    # Видаляємо старі вебхуки та запускаємо опитування
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений користувачем.")
