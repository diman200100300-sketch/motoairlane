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
        conn = sqlite3.connect("bot_database_v3.db")
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
    return sqlite3.connect("bot_database_v3.db")

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
        'welcome': "👋 Вітаємо у **ToolBox AI**!\n\n🤖 **Що робить цей бот:**\n1. **Завантаження TikTok** — зберігає будь-які відео у високій якості без водяного знака.\n2. **Аудіо в текст** — розпізнає голосові повідомлення та розставляє коми, крапки і знаки питання.\n3. **Генератор контенту** — створює унікальні сценарії та ідеї під ваші теми (ігри, машини, поїзди тощо).\n\nОберіть необхідний розділ нижче:",
        'status_pro': "⭐ Статус: PRO (Повний безлімітний доступ)",
        'status_free': "⭐ Статус: Безкоштовний тариф",
        'choose_section': "Оберіть необхідний розділ у головному меню нижче:",
        'btn_tiktok': "📥 Завантажити TikTok (Без водяного знака)",
        'btn_audio': "🎙 Аудіо в текст (Розпізнавання з пунктуацією)",
        'btn_ai': "🤖 Інтелектуальний ШІ-Генератор Ідей",
        'btn_pro_active': "✅ PRO Активно",
        'btn_buy_pro': "💎 Купити PRO — 19 zł/міс",
        'btn_lang': "🌐 Language / Мова",
        'lang_changed': "✅ Мову змінено на українську!",
        'send_tiktok': "📥 Надішліть посилання на TikTok. Запускаю потужний каскад обходу блокувань!",
        'downloading': "⏳ Завантажую відео без водяного знака...",
        'download_error': "❌ Не вдалося завантажити відео через усі доступні методи. Спробуйте інше посилання.",
        'ai_prompt': "💡 **Інтелектуальний ШІ-Генератор Контенту**\n\nВведіть вашу тему (наприклад: *GTA 5, машини, поїзди, риболовля, Rust*), і система сформує детальний унікальний план!",
        'ai_generating': "🧠 Аналізую тему, формую глибокі сценарії та унікальні ідеї...",
        'back': "« Назад до головного меню",
        'audio_send': "🎙 Надішліть голосове повідомлення або аудіофайл, і я переведу його в текст із розставленими комами, крапками та знаками питання.",
        'audio_processing': "⏳ Розпізнаю аудіопотік та форматую пунктуацію...",
        'buy_title': "💎 **Отримання PRO статусу**\nЦіна: 19 zł/місяць\nBLIK переказ на номер:\n`+48 733 985 396`\n\nПісля оплати натисніть кнопку нижче.",
        'i_paid_btn': "✉️ Я сплатив (Повідомити адміністрацію)",
        'i_paid_msg': "⏳ Вашу заявку на оплату надіслано адміністрації!"
    },
    'en': {
        'welcome': "👋 Welcome to **ToolBox AI**!\n\n🤖 **What this bot does:** Download TikTok without watermark, convert audio to text, and generate smart content ideas.",
        'status_pro': "⭐ Status: PRO",
        'status_free': "⭐ Status: Free Tier",
        'choose_section': "Choose section:",
        'btn_tiktok': "📥 Download TikTok (No Watermark)",
        'btn_audio': "🎙 Audio to Text",
        'btn_ai': "🤖 Smart AI Idea Generator",
        'btn_pro_active': "✅ PRO Active",
        'btn_buy_pro': "💎 Buy PRO — 19 zł/mo",
        'btn_lang': "🌐 Language",
        'lang_changed': "✅ Language changed to English!",
        'send_tiktok': "📥 Send TikTok link.",
        'downloading': "⏳ Downloading video...",
        'download_error': "❌ Failed to download video.",
        'ai_prompt': "💡 **AI Generator**\n\nEnter your topic.",
        'ai_generating': "🧠 Processing unique analysis...",
        'back': "« Back",
        'audio_send': "🎙 Send audio file.",
        'audio_processing': "⏳ Processing audio...",
        'buy_title': "💎 **Get PRO**\nBLIK: `+48 733 985 396`",
        'i_paid_btn': "✉ I have paid",
        'i_paid_msg': "⏳ Request sent!"
    },
    'pl': {
        'welcome': "👋 Witaj w **ToolBox AI**!\n\n🤖 **Co robi ten bot:** Pobieranie TikTok bez znaku wodnego, audio na tekst, generator pomysłów.",
        'status_pro': "⭐ Status: PRO",
        'status_free': "⭐ Status: Darmowy",
        'choose_section': "Wybierz sekcję:",
        'btn_tiktok': "📥 Pobierz TikTok",
        'btn_audio': "🎙 Audio na tekst",
        'btn_ai': "🤖 Inteligentny Generator AI",
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
        'i_paid_btn': "✉ Zapłaciłem",
        'i_paid_msg': "⏳ Wysłano zgłoszenie!"
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
    logger.info(f"Вебсервер запущено на порті {port}")

async def keep_alive_ping():
    await asyncio.sleep(15)
    while True:
        try:
            if RENDER_EXTERNAL_URL:
                async with ClientSession() as session:
                    async with session.get(RENDER_EXTERNAL_URL, timeout=10) as resp:
                        logger.info(f"Keep-Alive пінг успішний, статус: {resp.status}")
        except Exception as e:
            logger.debug(f"Keep-Alive помилка: {e}")
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
async def download_tiktok_unwatermarked(url: str, output_filename: str) -> bool:
    headers_mobile = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.tiktok.com/'
    }

    # Метод 1: TikWM API HD
    try:
        async with ClientSession() as session:
            async with session.get(f"https://tikwm.com/api/?url={url}&hd=1", headers=headers_mobile, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vid_url = data.get("data", {}).get("hdplay") or data.get("data", {}).get("play")
                    if vid_url:
                        async with session.get(vid_url, headers=headers_mobile, timeout=15) as v_resp:
                            if v_resp.status == 200:
                                with open(output_filename, "wb") as f:
                                    f.write(await v_resp.read())
                                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 20000:
                                    return True
    except Exception:
        pass

    # Метод 2: TikWM звичайний ендпоінт
    try:
        async with ClientSession() as session:
            async with session.post("https://tikwm.com/api/", data={'url': url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}, headers=headers_mobile, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vid_url = data.get("data", {}).get("play")
                    if vid_url:
                        async with session.get(vid_url, headers=headers_mobile, timeout=15) as v_resp:
                            if v_resp.status == 200:
                                with open(output_filename, "wb") as f:
                                    f.write(await v_resp.read())
                                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 20000:
                                    return True
    except Exception:
        pass

    # Метод 3: SSSTik.io парсер
    try:
        async with ClientSession() as session:
            async with session.post("https://ssstik.io/abc?url=dl", data={'id': url, 'locale': 'uk', 'tt': 'bGJlZHBh'}, headers=headers_mobile, timeout=10) as resp:
                if resp.status == 200:
                    html_content = await resp.text()
                    match = re.search(r'href="(https://[^"]+dl[^\"]+)"', html_content)
                    if match:
                        dl_link = match.group(1).replace('&amp;', '&')
                        async with session.get(dl_link, headers=headers_mobile, timeout=15) as d_resp:
                            if d_resp.status == 200:
                                with open(output_filename, "wb") as f:
                                    f.write(await d_resp.read())
                                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 20000:
                                    return True
    except Exception:
        pass

    # Метод 4: SnapTik альтернативний парсинг
    try:
        async with ClientSession() as session:
            async with session.get(f"https://snaptik.app/abc.php?url={url}", headers=headers_mobile, timeout=10) as resp:
                if resp.status == 200:
                    html_content = await resp.text()
                    match = re.search(r'href="(https://[^"]+snaptik[^"]+)"', html_content)
                    if match:
                        dl_link = match.group(1).replace('&amp;', '&')
                        async with session.get(dl_link, headers=headers_mobile, timeout=15) as d_resp:
                            if d_resp.status == 200:
                                with open(output_filename, "wb") as f:
                                    f.write(await d_resp.read())
                                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 20000:
                                    return True
    except Exception:
        pass

    # Метод 5: yt-dlp як резервний двигун
    try:
        ydl_opts = {
            'outtmpl': output_filename,
            'noplaylist': True,
            'quiet': True,
            'geo_bypass': True,
            'http_headers': headers_mobile
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 20000:
            return True
    except Exception:
        pass

    return False
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
    
    welcome_text = get_t(user_id, 'welcome')
    pro_active = check_pro_status(user_id)
    status_text = get_t(user_id, 'status_pro') if pro_active else get_t(user_id, 'status_free')
    
    await message.answer(
        f"{welcome_text}\n\n{status_text}",
        reply_markup=main_menu_kb(user_id),
        parse_mode="Markdown"
    )

# Автоматичне реагування на перше повідомлення або очищену історію
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_any_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    current_state = await state.get_state()
    if current_state is not None:
        return  # Якщо користувач у стані очікування посилання чи промпту — не перебиваємо
        
    welcome_text = get_t(user_id, 'welcome')
    pro_active = check_pro_status(user_id)
    status_text = get_t(user_id, 'status_pro') if pro_active else get_t(user_id, 'status_free')
    
    await message.answer(
        f"🤖 Вітаю! Я помітив, що історія була очищена або ви почали спілкування наново.\n\n{welcome_text}\n\n{status_text}",
        reply_markup=main_menu_kb(user_id),
        parse_mode="Markdown"
    )

@dp.message(Command("add_admin"))
async def cmd_add_admin(message: types.Message):
    if not is_creator(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Адміністратора додано: `{target_id}`", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

@dp.message(Command("give_pro"))
async def cmd_give_pro(message: types.Message):
    if not is_admin(message.from_user.id):
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
        await message.answer(f"💎 PRO активовано для `{target_id}`!", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

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
    if not ("tiktok.com" in url or "vm.tiktok.com" in url or "vt.tiktok.com" in url):
        await message.answer("⚠️ Надішліть дійсне посилання на TikTok.")
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
        subprocess.run(["ffmpeg", "-y", "-i", ogg_file, wav_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        recognized_text = ""
        if os.path.exists(wav_file):
            r = sr.Recognizer()
            with sr.AudioFile(wav_file) as source:
                audio_data = r.record(source)
                try:
                    recognized_text = r.recognize_google(audio_data, language="uk-UA")
                except Exception:
                    try:
                        recognized_text = r.recognize_google(audio_data, language="ru-RU")
                    except Exception:
                        recognized_text = "Не вдалося розпізнати чіткі слова."

        formatted_text = recognized_text
        if recognized_text and "Не вдалося" not in recognized_text:
            text_clean = recognized_text.strip()
            
            # Покращене розставлення ком, вступних слів та пауз
            replacements = {
                " привіти ": " Привіт, ",
                " привіт ": " Привіт, ",
                " здрастуйте ": " Здрастуйте, ",
                " добрий день ": " Добрий день, ",
                " скажи мені ": " Скажи мені, ",
                " будь ласка ": ", будь ласка, ",
                " слухай ": " Слухай, ",
                " до речі ": ", до речі, ",
                " наприклад ": ", наприклад, ",
                " знаєш ": ", знаєш, ",
                " коротше ": ", коротше кажучи, ",
                " ну а ": ". Ну а ",
                " а потім ": ". А потім ",
                " тому що ": ", тому що ",
                " якщо ": ", якщо ",
                " коли ": ", коли ",
                " але ": ", але ",
                " а от ": ". А от ",
                " скажи ": " Скажи, ",
                " скажіть ": " Скажіть, "
            }
            
            for k, v in replacements.items():
                text_clean = text_clean.replace(k, v)
                
            formatted_text = text_clean[0].upper() + text_clean[1:] if len(text_clean) > 1 else text_clean
            
            q_words = ("що ", "як ", "де ", "коли ", "чому ", "куди ", "звідки ", "скільки ", "чий ", "чи ", "тебе ", "який ", "яка ")
            is_question = formatted_text.lower().startswith(q_words) or any(q in formatted_text.lower() for q in ["як справи", "скільки тобі", "тебе звати", "що робиш", "як ти", "добрий день", "років"])
            
            if is_question:
                if not formatted_text.endswith("?"):
                    formatted_text += "?"
            else:
                if not formatted_text.endswith((".", "!", "?")):
                    formatted_text += "."

        response_text = (
            f"🎙 **Результат розпізнавання аудіо:**\n\n"
            f"❝ *{formatted_text}* ❞\n\n"
            f"✅ Пунктуацію, коми та знаки питання розставлено автоматично!"
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

# ІНТЕЛЕКТУАЛЬНИЙ КОНТЕКСТНИЙ ШІ-ГЕНЕРАТОР (АНАЛІЗУЄ ТЕМИ ІГОР, МАШИН ТОЩО БЕЗ ПОВТОРЕНЬ)
@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_idea_megablock(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith("/"):
        await state.clear()
        if message.text == "/start":
            await cmd_start(message)
        return
        
    topic = message.text.strip()
    topic_lower = topic.lower()
    wait_msg = await message.answer(get_t(user_id, 'ai_generating'))
    
    await asyncio.sleep(1.2)
    
    seed_val = abs(hash(topic) + datetime.now().microsecond + random.randint(1, 99999))
    
    # Контекстний аналіз теми для унікальності відповідей
    if any(w in topic_lower for w in ["gta", "гра", "ігри", "rust", "гта", "майнкрафт", "pubg"]):
        niche_type = "ігровий проєкт / геймінг"
        hook_pool = [
            f"«Як вижити та заробити перші мільйони в {topic} за 1 годину без читів?»",
            f"«Секретний трюк у {topic}, про який мовчать топ-стрімери та гравці.»",
            f"«Що буде, якщо зіграти в {topic} за найжорсткішими правилами? Експеримент!»",
            f"«Найбільша помилка новачків у {topic}, через яку ви втрачаєте весь прогрес.»"
        ]
        strategy_pool = [
            f"Зробіть огляд прихованої механіки або найкращого фарму в {topic}, показавши цифри.",
            f"Побудуйте сценарій у форматі челенджу: чи зможете ви пройти найскладнішу місію в {topic}?",
            f"Порівняйте старий та новий патч у {topic}, виділивши головні зміни для гравців."
        ]
    elif any(w in topic_lower for w in ["машин", "авто", "bmw", "ауді", "Hyundai", " ix35", "тюнінг", "драйв"]):
        niche_type = "автомобільна тематика / авто"
        hook_pool = [
            f"«Вся правда про {topic}: чи варто купувати і які приховані проблеми існують?»",
            f"«Як покращити {topic} своїми руками за копійки: лайфхак від майстра.»",
            f"«Найнадійніші та найгірші деталі у {topic}, про які не кажуть на СТО.»",
            f"«Тест-драйв {topic} у реальних умовах: результати шокують.»"
        ]
        strategy_pool = [
            f"Зробіть детальний розбір характеристик, слабких місць та переваг {topic}.",
            f"Порівняйте витрати на обслуговування {topic} з конкурентами у цьому ж класі.",
            f"Покажіть покроковий процес тюнингу або усунення поширеної несправності для {topic}."
        ]
    else:
        niche_type = "універсальний контент / експертна тема"
        hook_pool = [
            f"«Цей метод у сфері {topic} повністю переверне ваше розуміння процесу.»",
            f"«Головний секрет успіху в {topic}, який приховують професіонали.»",
            f"«Як досягти максимального результату в {topic} найшвидшим шляхом?»"
        ]
        strategy_pool = [
            f"Розкрийте тему {topic} через практичний кейс з покроковою інструкцією.",
            f"Проведіть порівняльний аналіз найкращих інструментів та підходів до {topic}."
        ]

    sel_hook = hook_pool[seed_val % len(hook_pool)]
    sel_strat = strategy_pool[(seed_val // 2) % len(strategy_pool)]
    
    sound_variants = [
        "Динамічний бас-біт із різкими акцентами на ключових кадрах монтажу.",
        "Енергійна фонова музика для утримання уваги глядача від першої секунди.",
        "Кінематографічний атмосферний саундтрек із наростанням на кульмінації."
    ]
    sel_sound = sound_variants[seed_val % len(sound_variants)]

    block1 = (
        f"🎯 **БЛОК №1: Глибокий ШІ-Аналіз запиту ({topic})**\n"
        f"• Ніша: `{niche_type}`\n"
        f"• Цільова аудиторія: Шукає практичні інсайди, чесні огляди та користь без 'води'.\n"
        f"• Головний психологічний тригер: Ексклюзивність інформації, вирішення болі."
    )
    
    block2 = (
        f"🎬 **БЛОК №2: Вірусний Сценарій та Гачок**\n"
        f"• **Гачок (0-3 сек):** {sel_hook}\n"
        f"• **Стратегія подачі:** {sel_strat}\n"
        f"• **Заклик до дії (CTA):** Попросіть глядачів написати свою думку в коментарях та підписатися."
    )
    
    block3 = (
        f"🎨 **БЛОК №3: Візуал та Аудіооформлення**\n"
        f"• Аудіосупровід: {sel_sound}\n"
        f"• Монтаж: Динамічна зміна планів кожні 2 секунди, великі контрастні субтитри."
    )
    
    block4 = (
        f"🚀 **БЛОК №4: SEO-Оптимізація та Хештеги**\n"
        f"• Рекомендовані теги: `#тренди #{topic.replace(' ', '')} #топконтент #ексклюзив #деталі`\n"
        f"• Оптимальний час публікації: 12:00–14:00 або 18:00–20:00."
    )

    full_response = (
        f"🤖 **ІНТЕЛЕКТУАЛЬНИЙ ПЛАН ТА СЦЕНАРІЙ (ШІ)**\n\n"
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

@dp.callback_query(F.data == "i_paid")
async def cb_i_paid(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or "Без юзернейму"
    await callback.message.answer(get_t(user_id, 'i_paid_msg'))
    
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
    logger.info("Витримана пауза 3 секунди для уникнення конфліктів...")
    await asyncio.sleep(3)
    
    asyncio.create_task(start_web_server())
    asyncio.create_task(keep_alive_ping())
    
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Головне меню / Запустити бота")
        ])
        await bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"Помилка скидання вебхука: {e}")
        
    logger.info("Бот успішно запущено та розпочато опитування (polling)!")
    await dp.start_polling(bot, handle_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Роботу бота завершено.")
