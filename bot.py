import os
import sys
import time
import logging
import asyncio
import sqlite3
import subprocess
from datetime import datetime
import aiohttp
from aiohttp import web
import speech_recognition as sr
from PIL import Image, ImageOps, ImageFilter, ImageEnhance, ImageDraw, ImageFont

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand

# --- НАЛАШТУВАННЯ ТА ЗМІННІ ОТОЧЕННЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CREATOR_ID = int(os.getenv("CREATOR_ID", "0"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger("ToolBoxAI")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАНИХ (SQLITE) ---
DB_NAME = "database.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            lang TEXT DEFAULT 'uk',
            role TEXT DEFAULT 'user',
            is_pro INTEGER DEFAULT 0,
            requests_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending',
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

init_db()

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
def get_user_lang(user_id: int) -> str:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else "uk"
    except Exception:
        return "uk"

def get_user_role(user_id: int) -> str:
    if user_id == CREATOR_ID:
        return "owner"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else "user"
    except Exception:
        return "user"

def check_pro_status(user_id: int) -> bool:
    if user_id == CREATOR_ID:
        return True
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_pro FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return bool(row[0]) if row else False
    except Exception:
        return False

def log_audit_action(user_id: int, action_type: str, details: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO audit_logs (user_id, action_type, details) VALUES (?, ?, ?)", (user_id, action_type, details))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка логування: {e}")

# --- ТЕКСТИ ТА МОВНІ КЛЮЧІ ---
TEXTS = {
    'uk': {
        'welcome': "👋 **Ласкаво просимо до ToolBox AI Enterprise!**\n\nОберіть потрібний інструмент з меню нижче:",
        'back': "« Назад",
        'choose_section': "Оберіть розділ:",
        'buy_title': "💎 **Оформлення PRO Підписки**\n\n• Безлімітні запити ШІ\n• Завантаження відео без водяних знаків\n• Обробка аудіо та Фотошоп\n\n**Ціна:** 19 PLN / місяць\n**Оплата через BLIK:** Надішліть код або переказ.",
        'i_paid_btn': "✅ Я оплатив (BLIK)",
        'i_paid_msg': "⌛ **Заявку прийнято!** Адміністратор перевірить транзакцію найближчим часом.",
        'tiktok_prompt': "📥 **Надішліть посилання на відео з TikTok:**",
        'tiktok_processing': "⏳ Завантажую відео без водяного знака...",
        'ai_idea_prompt': "💡 **Введіть тему або нішу для генерації ідей:**",
        'ai_idea_processing': "🤖 ШІ ґенерує ідеї...",
        'audio_send': "🎙 **Надішліть голосове повідомлення або аудіофайл:**",
        'audio_processing': "⏳ Розпізнаю аудіо в текст...",
        'photo_send': "🖼 **Надішліть фотографію для обробки:**"
    }
}

def get_t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return TEXTS.get(lang, TEXTS['uk']).get(key, TEXTS['uk'].get(key, ''))

# --- СТАНИ FSM ---
class GenStates(StatesGroup):
    waiting_for_tiktok = State()
    waiting_for_ai_idea = State()
    waiting_for_audio = State()
    waiting_for_target_user_id = State()
    waiting_for_main_admin_target = State()

class PhotoshopStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_watermark_text = State()
    waiting_for_custom_text = State()

# --- КЛАВІАТУРИ ---
def main_menu_kb_builder(user_id: int):
    role = get_user_role(user_id)
    is_pro = check_pro_status(user_id)
    
    buttons = [
        [InlineKeyboardButton(text="📥 TikTok Downloader (No WM)", callback_data="tiktok_downloader")],
        [InlineKeyboardButton(text="💡 ШІ Генератор Ідей", callback_data="ai_idea_gen")],
        [InlineKeyboardButton(text="🎙 Аудіо в Текст (SpeechToText)", callback_data="audio_to_text")],
        [InlineKeyboardButton(text="🎨 ШІ-Фотошоп & Графіка", callback_data="photoshop_menu")]
    ]
    
    if not is_pro:
        buttons.append([InlineKeyboardButton(text="💎 Придбати PRO (19 PLN)", callback_data="buy_pro")])
        
    if user_id == CREATOR_ID or role == 'owner':
        buttons.append([InlineKeyboardButton(text="👑 Панель Овнера", callback_data="owner_panel")])
        buttons.append([InlineKeyboardButton(text="🛡 Панель Адміна", callback_data="admin_panel")])
    elif role in ['main_admin', 'admin']:
        buttons.append([InlineKeyboardButton(text="🛡 Панель Адміна", callback_data="admin_panel")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- МОДУЛЬ TIKTOK DOWNLOADER ---
@dp.callback_query(F.data == "tiktok_downloader")
async def tiktok_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_tiktok)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'tiktok_prompt'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(GenStates.waiting_for_tiktok, F.text)
async def process_tiktok_download(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    url = message.text.strip()
    
    if "tiktok.com" not in url:
        await message.answer("❌ Будь ласка, надішліть дійсне посилання на TikTok.")
        return

    status_msg = await message.answer(get_t(user_id, 'tiktok_processing'))
    out_file = f"tiktok_{user_id}_{int(time.time())}.mp4"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://www.tikwm.com/api/", data={"url": url}, timeout=15) as resp:
                res = await resp.json()
                if res.get("code") == 0 and "data" in res and "play" in res["data"]:
                    video_url = "https://www.tikwm.com" + res["data"]["play"] if not res["data"]["play"].startswith("http") else res["data"]["play"]
                    async with session.get(video_url, timeout=30) as v_resp:
                        if v_resp.status == 200:
                            with open(out_file, "wb") as f:
                                f.write(await v_resp.read())

        if not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
            cmd = ["yt-dlp", "-o", out_file, "--max-filesize", "50M", url]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)

        if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
            await status_msg.delete()
            await message.answer_video(FSInputFile(out_file), caption="✅ **Відео завантажено!**", parse_mode="Markdown")
            log_audit_action(user_id, "TIKTOK_DOWNLOAD", url)
        else:
            await status_msg.edit_text("❌ Не вдалося завантажити відео.")
    except Exception as e:
        logger.error(f"Помилка TikTok: {e}")
        await status_msg.edit_text("❌ Помилка завантаження.")
    finally:
        if os.path.exists(out_file):
            try: os.remove(out_file)
            except Exception: pass
        await state.clear()
        await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))

# --- МОДУЛЬ ШІ ГЕНЕРАТОРА ІДЕЙ ---
@dp.callback_query(F.data == "ai_idea_gen")
async def ai_idea_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_ai_idea)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'ai_idea_prompt'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(GenStates.waiting_for_ai_idea, F.text)
async def process_ai_idea(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    prompt = message.text.strip()
    status_msg = await message.answer(get_t(user_id, 'ai_idea_processing'))
    
    try:
        await asyncio.sleep(1)
        response_text = (
            f"🧠 **Генеровані ШІ-ідеї за темою:** `{prompt}`\n\n"
            f"1. 🚀 **Контент-план:** Створити коротке трендове відео з розбором деталі.\n"
            f"2. 📈 **Стратегія:** Провести опитування аудиторії в коментарях.\n"
            f"3. 💡 **Формат:** Візуальний чек-лист чи інфографіка.\n"
            f"4. 🎬 **Порада:** Використати динамічний монтаж і яскравий заголовок."
        )
        await status_msg.edit_text(response_text, parse_mode="Markdown")
        log_audit_action(user_id, "AI_IDEA_GEN", prompt)
    except Exception as e:
        logger.error(f"Помилка ШІ: {e}")
        await status_msg.edit_text("❌ Помилка під час генерації.")
    finally:
        await state.clear()
        await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))

# --- КНОПКА «НАЗАД» ---
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await callback.message.edit_text(get_t(user_id, 'welcome'), reply_markup=main_menu_kb_builder(user_id), parse_mode="Markdown")
    await callback.answer()

# --- МОДУЛЬ АУДІО В ТЕКСТ ---
@dp.callback_query(F.data == "audio_to_text")
async def ask_audio_input(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(GenStates.waiting_for_audio)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'audio_send'), reply_markup=kb)
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
        
        subprocess.run(["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="uk-UA")
            
        await status_msg.edit_text(f"🎙 **Розпізнаний текст:**\n\n`{text}`", parse_mode="Markdown")
        
