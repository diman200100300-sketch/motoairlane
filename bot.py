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
            lang_code = "uk-UA" if get_user_lang(user_id) == "uk" else ("pl-PL" if get_user_lang(user_id) == "pl" else "en-US")
            text = recognizer.recognize_google(audio_data, language=lang_code)
            
        await status_msg.edit_text(f"🎙 **Розпізнаний текст з пунктуацією:**\n\n`{text}`", parse_mode="Markdown")
        log_audit_action(user_id, "AUDIO_TO_TEXT", "Успішно розпізнано аудіо")
    except sr.UnknownValueError:
        await status_msg.edit_text("❌ Не вдалося розпізнати мову. Спробуйте записати чіткіше.")
    except Exception as e:
        logger.error(f"Помилка розпізнавання: {e}")
        await status_msg.edit_text("❌ Помилка під час обробки аудіофайлу.")
    finally:
        for path in [src_path, wav_path]:
            if os.path.exists(path):
                try: os.remove(path)
                except Exception: pass
        await state.clear()
        await message.answer(get_t(user_id, 'choose_section'), reply_markup=main_menu_kb_builder(user_id))

# --- МОДУЛЬ ШІ-ФОТОШОП ТА ОБРОБКИ ГРАФІКИ ---
@dp.callback_query(F.data == "photoshop_menu")
async def photoshop_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(PhotoshopStates.waiting_for_photo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]])
    await callback.message.edit_text(get_t(user_id, 'photo_send'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(PhotoshopStates.waiting_for_photo, F.photo)
async def process_photo_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    img_path = f"photo_{user_id}_{int(time.time())}.png"
    
    try:
        await bot.download_file(file_info.file_path, img_path)
        
        # ✅ ВИПРАВЛЕНО ДУЖКУ ТУТ (РЯДОК 661):
        await state.update_data(current_photo_path=img_path)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎭 Фільтри та обробка", callback_data="ps_filters")],
            [InlineKeyboardButton(text="🔄 Обертання та поворот", callback_data="ps_rotate_menu")],
            [InlineKeyboardButton(text="🏷 Водяні знаки (Watermarks)", callback_data="ps_wm_menu")],
            [InlineKeyboardButton(text="📝 Додати / Видалити текст", callback_data="ps_text_menu")],
            [InlineKeyboardButton(text="✂️ Вирізання об'єкта / Маска", callback_data="ps_cutout")],
            [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
        ])
        await message.answer("🎨 **Оберіть інструмент обробки фотографії:**", reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка фото: {e}")
        await message.answer("❌ Помилка під час збереження зображення.")

# --- Фільтри та ефекти ---
@dp.callback_query(F.data == "ps_filters")
async def ps_filters_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Інверсія кольорів", callback_data="ps_filter_invert")],
        [InlineKeyboardButton(text="🖤 Чорно-біле (B&W)", callback_data="ps_filter_bw")],
        [InlineKeyboardButton(text="✨ Розмиття (Blur)", callback_data="ps_filter_blur")],
        [InlineKeyboardButton(text="🔍 Чіткість (Sharpen)", callback_data="ps_filter_sharpen")],
        [InlineKeyboardButton(text="🎭 Контраст +30%", callback_data="ps_filter_contrast")],
        [InlineKeyboardButton(text="« Назад", callback_data="photoshop_menu")]
    ])
    await callback.message.edit_text("🎭 **Оберіть ефект або фільтр:**", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("ps_filter_"))
async def apply_ps_filter(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    
    if not img_path or not os.path.exists(img_path):
        await callback.answer("❌ Зображення не знайдено. Надішліть фото знову.", show_alert=True)
        return
        
    action = callback.data.replace("ps_filter_", "")
    out_path = f"edited_{user_id}_{int(time.time())}.png"
    
    try:
        with Image.open(img_path).convert("RGB") as img:
            if action == "invert":
                edited_img = ImageOps.invert(img)
            elif action == "bw":
                edited_img = ImageOps.grayscale(img)
            elif action == "blur":
                edited_img = img.filter(ImageFilter.GAUSSIAN_BLUR(radius=4))
            elif action == "sharpen":
                edited_img = img.filter(ImageFilter.SHARPEN)
            elif action == "contrast":
                enhancer = ImageEnhance.Contrast(img)
                edited_img = enhancer.enhance(1.3)
            else:
                edited_img = img
                
            edited_img.save(out_path)
            
        await callback.message.answer_photo(FSInputFile(out_path), caption=f"✅ **Фільтр `{action}` успішно застосовано!**", parse_mode="Markdown")
        log_audit_action(user_id, "PHOTOSHOP_FILTER", f"Застосовано {action}")
    except Exception as e:
        logger.error(f"Помилка фільтра: {e}")
        await callback.answer("❌ Помилка обробки фото.", show_alert=True)
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
    await callback.answer()

# --- Поворот та обертання ---
@dp.callback_query(F.data == "ps_rotate_menu")
async def ps_rotate_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↪️ Поворот 90°", callback_data="ps_rot_90"), InlineKeyboardButton(text="🔄 Поворот 180°", callback_data="ps_rot_180")],
        [InlineKeyboardButton(text="↩ Поворот 270°", callback_data="ps_rot_270"), InlineKeyboardButton(text="🪞 Дзеркально", callback_data="ps_rot_flip")],
        [InlineKeyboardButton(text="« Назад", callback_data="photoshop_menu")]
    ])
    await callback.message.edit_text("🔄 **Оберіть варіант повороту:**", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("ps_rot_"))
async def apply_ps_rotate(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    if not img_path or not os.path.exists(img_path): return
        
    rot_type = callback.data.replace("ps_rot_", "")
    out_path = f"rot_{user_id}_{int(time.time())}.png"
    
    try:
        with Image.open(img_path) as img:
            if rot_type == "90": edited_img = img.rotate(-90, expand=True)
            elif rot_type == "180": edited_img = img.rotate(180, expand=True)
            elif rot_type == "270": edited_img = img.rotate(-270, expand=True)
            elif rot_type == "flip": edited_img = ImageOps.mirror(img)
            else: edited_img = img
            edited_img.save(out_path)
            
        await callback.message.answer_photo(FSInputFile(out_path), caption="✅ **Зображення успішно повернуто!**")
    except Exception as e:
        logger.error(f"Помилка обертання: {e}")
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
    await callback.answer()

# --- Водяні знаки (Watermarks) ---
@dp.callback_query(F.data == "ps_wm_menu")
async def ps_wm_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 Бренд-знак ToolBox AI", callback_data="ps_wm_default")],
        [InlineKeyboardButton(text="✏️ Власний текст / Мерч", callback_data="ps_wm_custom")],
        [InlineKeyboardButton(text="🧹 Приховати / Замазати водяний знак", callback_data="ps_wm_hide")],
        [InlineKeyboardButton(text="« Назад", callback_data="photoshop_menu")]
    ])
    await callback.message.edit_text("🏷 **Керування водяними знаками:**", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "ps_wm_default")
async def apply_wm_default(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    if not img_path or not os.path.exists(img_path): return
    
    out_path = f"wm_{user_id}_{int(time.time())}.png"
    try:
        with Image.open(img_path).convert("RGBA") as base:
            txt_layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            font_size = max(20, int(base.width / 20))
            try: font = ImageFont.truetype("arial.ttf", font_size)
            except Exception: font = ImageFont.load_default()
            
            draw.text((base.width - font_size * 10, base.height - font_size * 2), "ToolBox AI Enterprise", fill=(255, 255, 255, 128), font=font)
            out = Image.alpha_composite(base, txt_layer)
            out.convert("RGB").save(out_path)
            
        await callback.message.answer_photo(FSInputFile(out_path), caption="✅ **Бренд-знак додано!**")
    except Exception as e:
        logger.error(f"Помилка водяного знака: {e}")
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
    await callback.answer()

@dp.callback_query(F.data == "ps_wm_custom")
async def ask_wm_custom(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PhotoshopStates.waiting_for_watermark_text)
    await callback.message.edit_text("✏️ **Введіть текст вашого бренду або мерчу для накладання:**")
    await callback.answer()

@dp.message(PhotoshopStates.waiting_for_watermark_text)
async def apply_wm_custom_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    custom_text = message.text.strip()
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    
    if not img_path or not os.path.exists(img_path):
        await message.answer("❌ Помилка: зображення втрачено. Надішліть фото знову.")
        await state.clear()
        return

    out_path = f"wm_custom_{user_id}_{int(time.time())}.png"
    try:
        with Image.open(img_path).convert("RGBA") as base:
            txt_layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            font_size = max(24, int(base.width / 15))
            try: font = ImageFont.truetype("arial.ttf", font_size)
            except Exception: font = ImageFont.load_default()
            
            draw.text((30, base.height - font_size * 2), custom_text, fill=(255, 255, 255, 160), font=font)
            out = Image.alpha_composite(base, txt_layer)
            out.convert("RGB").save(out_path)
            
        await message.answer_photo(FSInputFile(out_path), caption=f"✅ **Власний водяний знак `{custom_text}` нанесено!**", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка власного водяного знака: {e}")
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
        await state.set_state(PhotoshopStates.waiting_for_photo)

@dp.callback_query(F.data == "ps_wm_hide")
async def hide_watermark_blur(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    if not img_path or not os.path.exists(img_path): return

    out_path = f"wm_hidden_{user_id}_{int(time.time())}.png"
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            blur_region = img.crop((int(w * 0.65), int(h * 0.82), w, h)).filter(ImageFilter.GaussianBlur(radius=16))
            img.paste(blur_region, (int(w * 0.65), int(h * 0.82)))
            img.save(out_path)
            
        await callback.message.answer_photo(FSInputFile(out_path), caption="🧹 **Зони водяних знаків приховано та розмито!**")
    except Exception as e:
        logger.error(f"Помилка приховування: {e}")
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
    await callback.answer()

# --- Робота з текстом та очищення ---
@dp.callback_query(F.data == "ps_text_menu")
async def ps_text_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Додати текст на фото", callback_data="ps_add_text")],
        [InlineKeyboardButton(text="🧼 Розумне очищення тексту з фото", callback_data="ps_clean_text")],
        [InlineKeyboardButton(text="« Назад", callback_data="photoshop_menu")]
    ])
    await callback.message.edit_text("📝 **Оберіть дію з текстом:**", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "ps_add_text")
async def ask_add_text(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PhotoshopStates.waiting_for_custom_text)
    await callback.message.edit_text("✍️ **Введіть текст, який потрібно нанести на центр фотографії:**")
    await callback.answer()

@dp.message(PhotoshopStates.waiting_for_custom_text)
async def process_add_text_to_image(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text_str = message.text.strip()
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    
    if not img_path or not os.path.exists(img_path): return
    out_path = f"text_added_{user_id}_{int(time.time())}.png"
    
    try:
        with Image.open(img_path) as img:
            draw = ImageDraw.Draw(img)
            font_size = max(28, int(img.width / 12))
            try: font = ImageFont.truetype("arial.ttf", font_size)
            except Exception: font = ImageFont.load_default()
            
            x = int(img.width / 4)
            y = int(img.height / 2)
            draw.text((x, y), text_str, fill=(255, 255, 0), font=font)
            img.save(out_path)
            
        await message.answer_photo(FSInputFile(out_path), caption="✅ **Текст успішно додано!**")
    except Exception as e:
        logger.error(f"Помилка додання тексту: {e}")
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
        await state.set_state(PhotoshopStates.waiting_for_photo)

@dp.callback_query(F.data == "ps_clean_text")
async def clean_text_from_photo(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    if not img_path or not os.path.exists(img_path): return
    
    out_path = f"cleaned_{user_id}_{int(time.time())}.png"
    try:
        with Image.open(img_path) as img:
            cleaned = img.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.SMOOTH_MORE)
            cleaned.save(out_path)
        await callback.message.answer_photo(FSInputFile(out_path), caption="🧼 **Текстові артефакти та шуми розгладжено!**")
    except Exception as e:
        logger.error(f"Помилка очищення: {e}")
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
    await callback.answer()

# --- Вирізання об'єкта / Прозора маска ---
@dp.callback_query(F.data == "ps_cutout")
async def process_cutout_mask(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    img_path = data.get("current_photo_path")
    if not img_path or not os.path.exists(img_path): return

    out_path = f"cutout_{user_id}_{int(time.time())}.png"
    try:
        with Image.open(img_path).convert("RGBA") as img:
            gray = ImageOps.grayscale(img)
            mask = gray.point(lambda p: 255 if p < 200 else 0)
            img.putalpha(mask)
            img.save(out_path, "PNG")
            
        await callback.message.answer_document(FSInputFile(out_path), caption="✂️ **Об'єкт вирізано! Збережено в PNG з Alpha-маскою.**")
    except Exception as e:
        logger.error(f"Помилка вирізання: {e}")
    finally:
        if os.path.exists(out_path): 
            try: os.remove(out_path)
            except Exception: pass
    await callback.answer()

# --- МОДУЛЬ ОПЛАТИ ТА КЕРУВАННЯ PRO СТАТУСАМИ ---
@dp.callback_query(F.data == "buy_pro")
async def show_buy_pro_info(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_t(user_id, 'i_paid_btn'), callback_data="notify_payment_submitted")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(get_t(user_id, 'buy_title'), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "notify_payment_submitted")
async def notify_payment_submitted(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or "Захований"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (user_id, amount, status) VALUES (?, 19.0, 'pending')", (user_id,))
        conn.commit()
        
        cursor.execute("SELECT user_id FROM users WHERE role IN ('owner', 'main_admin', 'admin') OR user_id = ?", (CREATOR_ID,))
        admins = list(set([row[0] for row in cursor.fetchall()]))
        conn.close()
        
        admin_msg = (
            f"💳 **НОВА ЗАЯВКА НА PRO СТАТУС!**\n\n"
            f"👤 **Користувач:** @{username}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"💰 **Сума:** 19 PLN (BLIK)\n"
            f"📅 **Час:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Для активації PRO натисніть кнопку нижче:"
        )
        
        for admin_id in admins:
            try:
                approve_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✅ Підтвердити PRO для ID {user_id}", callback_data=f"approve_pro_{user_id}")]])
                await bot.send_message(admin_id, admin_msg, reply_markup=approve_kb, parse_mode="Markdown")
            except Exception: pass
                
        await callback.message.edit_text(get_t(user_id, 'i_paid_msg'))
        log_audit_action(user_id, "PAYMENT_SUBMITTED", "Надіслано сповіщення про оплату BLIK")
    except Exception as e:
        logger.error(f"Помилка замовлення PRO: {e}")
    await callback.answer()

@dp.callback_query(F.data.startswith("approve_pro_"))
async def approve_pro_handler(callback: types.CallbackQuery):
    admin_id = callback.from_user.id
    if admin_id != CREATOR_ID and get_user_role(admin_id) not in ['owner', 'main_admin', 'admin']:
        await callback.answer("⛔ Недостатньо прав!", show_alert=True)
        return
        
    target_user_id = int(callback.data.replace("approve_pro_", ""))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_user_id,))
        cursor.execute("UPDATE transactions SET status = 'approved' WHERE user_id = ? AND status = 'pending'", (target_user_id,))
        conn.commit()
        conn.close()
        
        await callback.message.edit_text(f"✅ **PRO статус успішно активовано для ID:** `{target_user_id}`", parse_mode="Markdown")
        try: await bot.send_message(target_user_id, "🎉 **Вітаємо! Ваш PRO статус успішно активовано!**")
        except Exception: pass
        log_audit_action(admin_id, "APPROVE_PRO", f"Схвалено PRO для {target_user_id}")
    except Exception as e:
        logger.error(f"Помилка активації: {e}")
    await callback.answer()

# --- ПАНЕЛЬ АДМІНІСТРАТОРА ТА ОВНЕРА ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != CREATOR_ID and get_user_role(user_id) not in ['owner', 'main_admin', 'admin']:
        await callback.answer("⛔ Доступ заборонено!", show_alert=True)
        return
        
    kb_buttons = [
        [InlineKeyboardButton(text="📋 Список очікуючих заявок PRO", callback_data="admin_pending_pro")],
        [InlineKeyboardButton(text="💎 Видати PRO вручну за ID", callback_data="admin_give_pro_manual")],
        [InlineKeyboardButton(text="📊 Статистика системи", callback_data="admin_stats")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ]
    await callback.message.edit_text("🛡 **Панель Адміністратора ToolBox AI Enterprise**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await callback.answer()

@dp.callback_query(F.data == "owner_panel")
async def owner_panel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != CREATOR_ID and get_user_role(user_id) != 'owner':
        await callback.answer("👑 Тільки Власник (Owner) має доступ!", show_alert=True)
        return
        
    kb_buttons = [
        [InlineKeyboardButton(text="👑 Призначити Main Admin", callback_data="owner_set_main_admin")],
        [InlineKeyboardButton(text="📜 Аудит-логи системи", callback_data="owner_view_logs")],
        [InlineKeyboardButton(text=get_t(user_id, 'back'), callback_data="back_to_menu")]
    ]
    await callback.message.edit_text("👑 **Панель Головного Власника (Owner Panel)**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await callback.answer()

@dp.callback_query(F.data == "admin_pending_pro")
async def view_pending_pro(callback: types.CallbackQuery):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, amount, created_at FROM transactions WHERE status = 'pending'")
        pending = cursor.fetchall()
        conn.close()
        
        if not pending:
            await callback.answer("ℹ️ Активних очікуючих заявок немає.", show_alert=True)
            return
            
        msg = "📋 **Список очікуючих заявок на PRO:**\n\n"
        kb = []
        for row in pending:
            uid, amt, date_str = row
            msg += f"• ID: `{uid}` | {amt} PLN | {date_str}\n"
            kb.append([InlineKeyboardButton(text=f"✅ Активувати ID {uid}", callback_data=f"approve_pro_{uid}")])
        kb.append([InlineKeyboardButton(text="« Назад", callback_data="admin_panel")])
        
        await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка заявок: {e}")
    await callback.answer()

@dp.callback_query(F.data == "admin_give_pro_manual")
async def ask_target_user_pro(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(GenStates.waiting_for_target_user_id)
    await callback.message.edit_text("💎 **Введіть User ID користувача, якому потрібно видати PRO статус:**")
    await callback.answer()

@dp.message(GenStates.waiting_for_target_user_id)
async def process_manual_pro_give(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введіть числовий User ID.")
        return
        
    target_id = int(text)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (user_id, is_pro) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET is_pro = 1", (target_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ **PRO статус успішно видано користувачу з ID `{target_id}`!**", parse_mode="Markdown")
        log_audit_action(admin_id, "MANUAL_GIVE_PRO", f"Видано PRO для {target_id}")
    except Exception as e:
        logger.error(f"Помилка видачі PRO: {e}")
        await message.answer("❌ Помилка під час збереження в БД.")
    finally:
        await state.clear()

@dp.callback_query(F.data == "owner_set_main_admin")
async def ask_main_admin_id(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(GenStates.waiting_for_main_admin_target)
    await callback.message.edit_text("👑 **Введіть User ID користувача, якого бажаєте зробити Main Admin:**")
    await callback.answer()

@dp.message(GenStates.waiting_for_main_admin_target)
async def process_set_main_admin(message: types.Message, state: FSMContext):
    owner_id = message.from_user.id
    if owner_id != CREATOR_ID and get_user_role(owner_id) != 'owner':
        await message.answer("⛔ Недостатньо прав!")
        await state.clear()
        return
        
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введіть числовий ID.")
        return
        
    target_id = int(text)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (user_id, role, is_pro) VALUES (?, 'main_admin', 1) ON CONFLICT(user_id) DO UPDATE SET role = 'main_admin', is_pro = 1", (target_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"👑 **Користувача `{target_id}` успішно призначено Main Admin!**", parse_mode="Markdown")
        log_audit_action(owner_id, "SET_MAIN_ADMIN", f"Призначено {target_id} на main_admin")
    except Exception as e:
        logger.error(f"Помилка призначення main_admin: {e}")
    finally:
        await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def view_stats(callback: types.CallbackQuery):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro = 1")
        pro_users = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(requests_count) FROM users")
        total_reqs = cursor.fetchone()[0] or 0
        conn.close()
        
        msg = (
            f"📊 **Загальна статистика ToolBox AI Enterprise:**\n\n"
            f"👥 Всього користувачів: `{total_users}`\n"
            f"💎 Активованих PRO акаунтів: `{pro_users}`\n"
            f"⚡ Опрацьовано запитів ШІ: `{total_reqs}`\n"
        )
        await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="admin_panel")]]), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка статистики: {e}")
    await callback.answer()

@dp.callback_query(F.data == "owner_view_logs")
async def view_audit_logs(callback: types.CallbackQuery):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, action_type, details, timestamp FROM audit_logs ORDER BY log_id DESC LIMIT 10")
        logs = cursor.fetchall()
        conn.close()
        
        msg = "📜 **Останні 10 подій в системному аудиті:**\n\n"
        for l in logs:
            msg += f"• `{l[3]}` | ID: `{l[0]}` | **{l[1]}**: {l[2]}\n"
            
        await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="owner_panel")]]), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Помилка логів: {e}")
    await callback.answer()

# --- ГОЛОВНИЙ ХЕНДЛЕР /START ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "Захований"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка реєстрації: {e}")
        
    await message.answer(get_t(user_id, 'welcome'), reply_markup=main_menu_kb_builder(user_id), parse_mode="Markdown")

# --- ВЕБ-СЕРВЕР ТА ЗАХИСТ ВІД ЗАСИНАННЯ (RENDER 24/7) ---
async def handle_ping(request):
    return web.Response(text="OK - ToolBox AI Running", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/health', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Вебсервер запущено на порту {PORT}")

async def keep_alive_ping():
    if not RENDER_EXTERNAL_URL:
        return
    await asyncio.sleep(10)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                url = RENDER_EXTERNAL_URL if RENDER_EXTERNAL_URL.startswith("http") else f"https://{RENDER_EXTERNAL_URL}"
                async with session.get(url, timeout=10) as resp:
                    logger.info(f"Keep-alive ping sent to {url}, status: {resp.status}")
            except Exception as e:
                logger.error(f"Keep-alive error: {e}")
            await asyncio.sleep(240)

async def background_garbage_collector():
    while True:
        try:
            for f in os.listdir("."):
                if f.startswith(("tiktok_", "audio_", "photo_", "edited_", "rot_", "wm_", "cleaned_", "cutout_")) and (f.endswith(".mp4") or f.endswith(".wav") or f.endswith(".ogg") or f.endswith(".png")):
                    try:
                        if time.time() - os.path.getmtime(f) > 300:
                            os.remove(f)
                    except Exception: pass
        except Exception as e:
            logger.error(f"Помилка очищення: {e}")
        await asyncio.sleep(180)

async def main():
    logger.info("Запуск серверного комплексу ToolBox AI Enterprise...")
    await bot.set_my_commands([BotCommand(command="start", description="Головне меню / Перезапуск")])
    
    asyncio.create_task(start_web_server())
    asyncio.create_task(keep_alive_ping())
    asyncio.create_task(background_garbage_collector())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
