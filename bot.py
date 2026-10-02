import asyncio
import logging
import json
import os
import datetime
import threading
import random
import re
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
import yt_dlp
import aiohttp
import speech_recognition as sr
from pydub import AudioSegment
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    FSInputFile
)

# --- ВЕБСЕРВЕР ТА SELF-PING ДЛЯ RENDER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is active and running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
        
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

def self_ping_loop():
    port = int(os.environ.get("PORT", 10000))
    url = f"http://127.0.0.1:{port}"
    while True:
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=5)
        except Exception:
            pass
        import time
        time.sleep(300)

threading.Thread(target=self_ping_loop, daemon=True).start()
# ---------------------------------------------

TOKEN = os.environ.get("BOT_TOKEN", "8412527814:AAHANlmU-OFE2hqOZshsPcKFBKwU5As7RzI")  
ADMIN_ID = 738520454

bot = Bot(token=TOKEN)
dp = Dispatcher()

PRO_FILE = "pro_users.json"
LIMITS_FILE = "user_limits.json"
LANG_FILE = "user_languages.json"
ai_waiting_users = set()

def load_json_file(filename, default_val):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Помилка завантаження {filename}: {e}")
            return default_val
    return default_val

def save_json_file(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка збереження {filename}: {e}")

pro_users = load_json_file(PRO_FILE, [])

def save_pro_users(users):
    save_json_file(PRO_FILE, users)

# --- СЛОВНИК МУЛЬТИМОВНОСТІ ---
LANGS = {
    "uk": {
        "start_msg": "Привіт! Я твій надійний помічник для завантаження відео, транскрипції голосу та генерації унікальних ідей.",
        "status_free": "⭐ Статус: **Безкоштовний**",
        "status_pro": "⭐ Статус: **PRO (Безліміт)**",
        "choose_section": "Оберіть розділ нижче:",
        "control_menu": "Меню керування:",
        "btn_ai": "💡 Генератор ідей",
        "btn_profile": "⭐ Мій профіль",
        "btn_buy": "💎 Купити PRO — 19 zł/міс",
        "btn_lang": "🌐 Мова / Język / Lang",
        "menu_video": "🎥 Завантажити відео (TikTok)",
        "menu_audio": "🎙 Аудіо інструменти (В текст)",
        "menu_ai_desc": "🤖 ШІ Генератор ідей",
        "buy_pro_inline": "⭐ Купити PRO (19 zł)",
        "pro_active_inline": "✅ PRO Активно",
        "back": "« Назад",
        "profile_text": "👤 Ваш ID: `{user_id}`\nСтатус: **{status}**\n\n📊 **Ліміти на сьогодні:**\n• Генератор ідей: Використано {ai_used}/6\n• Завантаження відео: Використано {vid_used}/7\n• Голосові в текст: Використано {voice_used}/4",
        "profile_pro_text": "👤 Ваш ID: `{user_id}`\nСтатус: **{status}**",
        "buy_title": "💎 **Отримання PRO**\nЦіна: **19 zł/місяць**\nОплата через **BLIK** на номер:\n`+48 733 985 396`\n\nПісля переказу натисніть кнопку нижче:",
        "paid_btn": "📩 Я сплатив",
        "paid_sent": "Заявку надіслано адміністратору!",
        "pro_activated_notif": "🎉 Вашу оплату підтверджено! PRO активовано.",
        "video_menu_text": "🎥 **Завантаження відео**\n\nНадішліть посилання на відео з **TikTok**, і я завантажу його без водяного знака!\n\n📌 *Безкоштовно:* до 7 разів на день.",
        "video_limit_err": "❌ Вичерпано безкоштовний ліміт завантаження відео на сьогодні (7/7).\nОформіть PRO!",
        "video_loading": "⏳ Завантажую відео з TikTok...",
        "video_link_err": "❌ Не вдалося отримати пряме посилання на відео. TikTok заблокував запит або відео видалено.",
        "video_html_err": "❌ Помилка: Сервер повернув HTML-сторінку замість медіафайлу.",
        "video_too_big": "❌ Відео занадто велике (понад 50 МБ).",
        "video_success_cap": "✅ Ось ваше відео без водяного знака!",
        "video_download_err": "❌ Помилка при завантаженні файлу.",
        "audio_menu_text": "🎙 **Аудіо інструменти (Перетворення в текст)**\n\nНадішліть голосове повідомлення, і я переведу його у текст з автоматичною пунктуацією та абзацами!\n\n⏱ **Ліміти тривалості:**\n• Безкоштовний: до **2 хвилин** (до 4 разів на день)\n• PRO: до **15 хвилин** (безлімітно щодня)",
        "audio_too_long": "❌ Файл занадто довгий! Максимальна тривалість — {limit_text}.",
        "audio_limit_err": "❌ Вичерпано безкоштовний ліміт транскрипції на сьогодні (4/4).",
        "audio_recognizing": "⏳ Розпізнаю аудіо та розставляю розділові знаки...",
        "audio_success": "📝 **Розпізнаний текст:**\n\n_{recognized_text}_",
        "audio_unknown_err": "❌ Не вдалося розпізнати мову в цьому аудіо.",
        "audio_proc_err": "❌ Сталася помилка при обробці аудіофайлу.",
        "ai_limit_err": "⭐ **Ви вичерпали 6 безкоштовних генерацій ідей на сьогодні.**\n\nПридбайте PRO для безліміту!",
        "ai_prompt_text": "💡 **Креативний ШІ Генератор ідей**\n\nНапишіть **будь-яку тему, слово чи фразу**, і я згенерую **3 унікальні практичні концепції** спеціально для вашого відео!",
        "ai_generating": "🧠 Генерую унікальні ідеї та сценарії для «{text}»...",
        "ai_exhausted": "❌ Вичерпано безкоштовний ліміт генерації ідей на сьогодні (6/6).",
        "lang_select_title": "🌐 Оберіть мову / Wybierz język / Choose language:",
        "lang_changed": "✅ Мову успішно змінено на Українську!",
        "ready_next": "Готово! Що робимо далі?",
        "fallback": "Скористайтеся меню нижче або натисніть /start для вибору розділу."
    },
    "pl": {
        "start_msg": "Cześć! Jestem Twoim pomocnikiem do pobierania wideo, transkrypcji z interpunkcją oraz generowania unikalnych pomysłów.",
        "status_free": "⭐ Status: **Darmowy**",
        "status_pro": "⭐ Status: **PRO (Bez limitu)**",
        "choose_section": "Wybierz sekcję poniżej:",
        "control_menu": "Menu sterowania:",
        "btn_ai": "💡 Generator pomysłów",
        "btn_profile": "⭐ Mój profil",
        "btn_buy": "💎 Kup PRO — 19 zł/mies.",
        "btn_lang": "🌐 Język / Мова / Lang",
        "menu_video": "🎥 Pobierz wideo (TikTok)",
        "menu_audio": "🎙 Narzędzia audio (Na tekst)",
        "menu_ai_desc": "🤖 Generator pomysłów AI",
        "buy_pro_inline": "⭐ Kup PRO (19 zł)",
        "pro_active_inline": "✅ PRO Aktywne",
        "back": "« Wstecz",
        "profile_text": "👤 Twój ID: `{user_id}`\nStatus: **{status}**\n\n📊 **Dzisiejsze limity:**\n• Generator pomysłów: Wykorzystano {ai_used}/6\n• Pobieranie wideo: Wykorzystano {vid_used}/7\n• Głos na tekst: Wykorzystano {voice_used}/4",
        "profile_pro_text": "👤 Twój ID: `{user_id}`\nStatus: **{status}**",
        "buy_title": "💎 **Uzyskanie PRO**\nCena: **19 zł/miesiąc**\nPłatność przez **BLIK** na numer:\n`+48 733 985 396`",
        "paid_btn": "📩 Zapłaciłem",
        "paid_sent": "Zgłoszenie zostało wysłane do administratora!",
        "pro_activated_notif": "🎉 Twoja płatność została potwierdzona! PRO aktywowane.",
        "video_menu_text": "🎥 **Pobieranie wideo**\n\nWyślij link do wideo z **TikTok**.",
        "video_limit_err": "❌ Wyczerpano darmowy limit pobierania wideo na dziś.",
        "video_loading": "⏳ Pobieram wideo...",
        "video_link_err": "❌ Nie udało się uzyskać bezpośredniego linku.",
        "video_html_err": "❌ Błąd: Serwer zwrócił stronę HTML.",
        "video_too_big": "❌ Wideo jest za duże.",
        "video_success_cap": "✅ Oto Twoje wideo bez znaku wodnego!",
        "video_download_err": "❌ Błąd podczas pobierania pliku.",
        "audio_menu_text": "🎙 **Narzędzia audio**\n\nWyślij wiadomość głosową.",
        "audio_too_long": "❌ Plik jest za długi!",
        "audio_limit_err": "❌ Wyczerpano darmowy limit.",
        "audio_recognizing": "⏳ Rozpoznaję audio z interpunkcją...",
        "audio_success": "📝 **Rozpoznany tekst:**\n\n_{recognized_text}_",
        "audio_unknown_err": "❌ Nie udało się rozpoznać mowy.",
        "audio_proc_err": "❌ Wystąpił błąd przetwarzania.",
        "ai_limit_err": "⭐ **Wyczerpano darmowe generacje na dziś.**",
        "ai_prompt_text": "💡 **Generator pomysłów AI**\n\nNapisz dowolny temat, a dam Ci 3 unikalne koncepcje:",
        "ai_generating": "🧠 Tworzę unikalne pomysły...",
        "ai_exhausted": "❌ Wyczerpano limit na dziś.",
        "lang_select_title": "🌐 Wybierz język:",
        "lang_changed": "✅ Język zmieniony na Polski!",
        "ready_next": "Gotowe! Co robimy dalej?",
        "fallback": "Skorzystaj z menu poniżej."
    },
    "en": {
        "start_msg": "Hello! I am your assistant for video downloading, punctuated speech transcription, and unique idea generation.",
        "status_free": "⭐ Status: **Free**",
        "status_pro": "⭐ Status: **PRO (Unlimited)**",
        "choose_section": "Choose a section below:",
        "control_menu": "Control menu:",
        "btn_ai": "💡 Idea Generator",
        "btn_profile": "⭐ My Profile",
        "btn_buy": "💎 Buy PRO — 19 zł/mo",
        "btn_lang": "🌐 Language / Мова / Język",
        "menu_video": "🎥 Download video (TikTok)",
        "menu_audio": "🎙 Audio tools (To text)",
        "menu_ai_desc": "🤖 AI Idea Generator",
        "buy_pro_inline": "⭐ Buy PRO (19 zł)",
        "pro_active_inline": "✅ PRO Active",
        "back": "« Back",
        "profile_text": "👤 Your ID: `{user_id}`\nStatus: **{status}**\n\n📊 **Today's limits:**\n• Idea Generator: Used {ai_used}/6\n• Video downloads: Used {vid_used}/7\n• Voice to text: Used {voice_used}/4",
        "profile_pro_text": "👤 Your ID: `{user_id}`\nStatus: **{status}**",
        "buy_title": "💎 **Get PRO**\nPrice: **19 zł/month**\nPayment via **BLIK** to number:\n`+48 733 985 396`",
        "paid_btn": "📩 I have paid",
        "paid_sent": "Application sent to administrator!",
        "pro_activated_notif": "🎉 Your payment has been confirmed! PRO is active.",
        "video_menu_text": "🎥 **Video Downloader**\n\nSend a link to a **TikTok** video.",
        "video_limit_err": "❌ Free video download limit reached.",
        "video_loading": "⏳ Downloading video...",
        "video_link_err": "❌ Failed to get direct video link.",
        "video_html_err": "❌ Error: HTML returned.",
        "video_too_big": "❌ Video is too large.",
        "video_success_cap": "✅ Here is your video!",
        "video_download_err": "❌ Error downloading file.",
        "audio_menu_text": "🎙 **Audio Tools**\n\nSend a voice message.",
        "audio_too_long": "❌ File is too long!",
        "audio_limit_err": "❌ Free limit reached.",
        "audio_recognizing": "⏳ Recognizing audio...",
        "audio_success": "📝 **Recognized text:**\n\n_{recognized_text}_",
        "audio_unknown_err": "❌ Could not recognize speech.",
        "audio_proc_err": "❌ Error processing audio.",
        "ai_limit_err": "⭐ **Exhausted free generations.**",
        "ai_prompt_text": "💡 **AI Idea Generator**\n\nType any topic to get 3 unique concepts:",
        "ai_generating": "🧠 Creating concepts...",
        "ai_exhausted": "❌ Limit reached.",
        "lang_select_title": "🌐 Choose language:",
        "lang_changed": "✅ Language changed to English!",
        "ready_next": "Done! What's next?",
        "fallback": "Use the menu below."
    }
}

def get_user_lang(user_id: int) -> str:
    langs_data = load_json_file(LANG_FILE, {})
    return langs_data.get(str(user_id), "uk")

def set_user_lang(user_id: int, lang: str):
    langs_data = load_json_file(LANG_FILE, {})
    langs_data[str(user_id)] = lang
    save_json_file(LANG_FILE, langs_data)

def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_user_lang(user_id)
    text_template = LANGS.get(lang, LANGS["uk"]).get(key, LANGS["uk"].get(key, key))
    if kwargs:
        try:
            return text_template.format(**kwargs)
        except:
            return text_template
    return text_template

def get_today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def check_and_update_limit(user_id: int, action_type: str, max_limit: int) -> bool:
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    if is_pro:
        return True

    data = load_json_file(LIMITS_FILE, {})
    today = get_today_str()
    str_uid = str(user_id)

    if str_uid not in data or data[str_uid].get("date") != today:
        data[str_uid] = {"date": today, "ai": 0, "video": 0, "voice": 0}

    current_count = data[str_uid].get(action_type, 0)
    if current_count >= max_limit:
        return False

    data[str_uid][action_type] = current_count + 1
    save_json_file(LIMITS_FILE, data)
    return True

def get_reply_menu(user_id: int):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(user_id, "btn_ai"))],
            [KeyboardButton(text=t(user_id, "btn_profile")), KeyboardButton(text=t(user_id, "btn_lang"))],
            [KeyboardButton(text=t(user_id, "btn_buy"))]
        ],
        resize_keyboard=True
    )

def get_inline_menu(user_id: int, is_pro: bool):
    keyboard = [
        [InlineKeyboardButton(text=t(user_id, "menu_video"), callback_data="menu_video")],
        [InlineKeyboardButton(text=t(user_id, "menu_audio"), callback_data="menu_audio")],
        [InlineKeyboardButton(text=t(user_id, "menu_ai_desc"), callback_data="menu_ai")],
    ]
    if not is_pro:
        keyboard.append([InlineKeyboardButton(text=t(user_id, "buy_pro_inline"), callback_data="buy_pro")])
    else:
        keyboard.append([InlineKeyboardButton(text=t(user_id, "pro_active_inline"), callback_data="pro_info")])
        
    keyboard.append([InlineKeyboardButton(text="🌐 Language / Мова / Język", callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_main_menu(message: types.Message, text_prefix=""):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status_text = t(user_id, "status_pro") if is_pro else t(user_id, "status_free")
    
    prefix = f"{text_prefix}\n\n" if text_prefix else ""
    text = f"{prefix}{status_text}\n\n{t(user_id, 'choose_section')}"
    
    await message.answer(text, reply_markup=get_reply_menu(user_id), parse_mode="Markdown")
    await message.answer(t(user_id, "control_menu"), reply_markup=get_inline_menu(user_id, is_pro))

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    ai_waiting_users.discard(message.from_user.id)
    await send_main_menu(message, t(message.from_user.id, "start_msg"))

@dp.message(F.text.in_({"💡 Генератор ідей", "💡 Generator pomysłów", "💡 Idea Generator"}))
async def btn_ai(message: types.Message):
    await show_ai(message)

@dp.message(F.text.in_({"⭐ Мій профіль", "⭐ Mój profil", "⭐ My Profile"}))
async def btn_prof(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status = "PRO (Unlimited)" if is_pro else "Free / Безкоштовний"
    
    data = load_json_file(LIMITS_FILE, {})
    u_limits = data.get(str(user_id), {}) if not is_pro else {}
    
    ai_used = u_limits.get("ai", 0) if not is_pro else 0
    vid_used = u_limits.get("video", 0) if not is_pro else 0
    voice_used = u_limits.get("voice", 0) if not is_pro else 0
    
    if not is_pro:
        profile_msg = t(user_id, "profile_text", user_id=user_id, status=status, ai_used=ai_used, vid_used=vid_used, voice_used=voice_used)
    else:
        profile_msg = t(user_id, "profile_pro_text", user_id=user_id, status=status)

    await message.answer(profile_msg, parse_mode="Markdown")
    await send_main_menu(message)

@dp.message(F.text.in_({"🌐 Мова / Język / Lang", "🌐 Język / Мова / Lang", "🌐 Language / Мова / Język"}))
async def btn_lang_text(message: types.Message):
    await show_language_menu(message)

async def show_language_menu(target):
    user_id = target.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_uk")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="lang_pl")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]
    ])
    text = t(user_id, "lang_select_title")
    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "change_lang")
async def cb_change_lang(callback: types.CallbackQuery):
    await show_language_menu(callback)

@dp.callback_query(F.data.startswith("lang_"))
async def cb_set_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang_code = callback.data.split("_")[1]
    set_user_lang(user_id, lang_code)
    
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    await callback.message.edit_text(t(user_id, "lang_changed"), reply_markup=get_inline_menu(user_id, is_pro))
    await callback.message.answer(t(user_id, "ready_next"), reply_markup=get_reply_menu(user_id))
    await callback.answer()

@dp.message(F.text.startswith(("💎 Купити PRO", "💎 Kup PRO", "💎 Buy PRO")))
async def btn_buy_text(message: types.Message):
    await send_buy(message)

async def send_buy(target):
    user_id = target.from_user.id
    text = t(user_id, "buy_title")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "paid_btn"), callback_data="paid_confirm")],
        [InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]
    ])
    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "buy_pro")
async def cb_buy(callback: types.CallbackQuery):
    await send_buy(callback)

@dp.callback_query(F.data == "paid_confirm")
async def cb_paid(callback: types.CallbackQuery):
    user = callback.from_user
    user_link = f"@{user.username}" if user.username else f"ID: {user.id}"
    
    if ADMIN_ID:
        try:
            admin_text = f"🔔 **Заявка на PRO!**\nКористувач: {user_link} (`{user.id}`)\nАктивуйте командою:\n`/givepro {user.id}`"
            await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Помилка відправки адміну: {e}")
            
    await callback.answer(t(user.id, "paid_sent"), show_alert=True)

@dp.callback_query(F.data == "back_home")
async def cb_home(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    ai_waiting_users.discard(user_id)
    await callback.message.edit_text(t(user_id, "control_menu"), reply_markup=get_inline_menu(user_id, is_pro))
    await callback.answer()

@dp.callback_query(F.data == "pro_info")
async def cb_pro_info(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer(t(user_id, "pro_active_inline"), show_alert=True)

@dp.message(Command("givepro"))
async def cmd_give(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Приклад: `/givepro ID`", parse_mode="Markdown")
        return
    try:
        tid = int(args[1])
        if tid not in pro_users:
            pro_users.append(tid)
            save_pro_users(pro_users)
        await message.answer(f"✅ Користувачу `{tid}` успішно активовано та збережено PRO!")
        await bot.send_message(tid, t(tid, "pro_activated_notif"))
    except Exception as e:
        await message.answer(f"Помилка в ID: {e}")

@dp.callback_query(F.data == "menu_video")
async def cb_vid(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    text = t(user_id, "video_menu_text")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

async def get_tiktok_direct_url(video_url: str) -> str:
    """ПОКРАЩЕНА КАСКАДНА СИСТЕМА ЗАВАНТАЖЕННЯ TIKTOK БЕЗ ПОМИЛОК"""
    if "vm.tiktok.com" in video_url or "vt.tiktok.com" in video_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(video_url, allow_redirects=True, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15'
                }) as resp:
                    video_url = str(resp.url)
        except Exception as e:
            logging.error(f"Помилка редіректу посилання: {e}")

    # ЕТАП 1: TikWM API з мобільними заголовками
    api_url = f"https://www.tikwm.com/api/?url={video_url}&hd=1"
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.tikwm.com/'
            }
            async with session.get(api_url, timeout=8, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        info = data.get("data", {})
                        direct = info.get("hdplay") or info.get("play")
                        if direct:
                            return direct
    except Exception as e:
        logging.error(f"Етап 1 (TikWM) помилка: {e}")

    # ЕТАП 2: Cobalt API
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"url": video_url, "vQuality": "720"}
            headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            async with session.post("https://co.wuk.sh/api/json", json=payload, headers=headers, timeout=8) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("status") in ["redirect", "stream"]:
                        return res.get("url")
    except Exception as e:
        logging.error(f"Етап 2 (Cobalt) помилка: {e}")

    # ЕТАП 3: SnapSave / Tiksave API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://tikcdn.io/api/ajax/search?q={video_url}", timeout=8, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    if "data" in res_json and isinstance(res_json["data"], str):
                        return res_json["data"]
    except Exception as e:
        logging.error(f"Етап 3 помилка: {e}")

    # ЕТАП 4: yt-dlp (Важка артилерія з обходом блокувань)
    def extract_ytdlp():
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url')
            except Exception as e:
                logging.error(f"Етап 4 (yt-dlp) помилка: {e}")
                return None

    try:
        loop = asyncio.get_running_loop()
        ytdlp_res = await loop.run_in_executor(None, extract_ytdlp)
        if ytdlp_res:
            return ytdlp_res
    except Exception as e:
        logging.error(f"Executor yt-dlp помилка: {e}")

    return None

@dp.message(F.text.startswith("http"))
async def down_media(message: types.Message):
    user_id = message.from_user.id
    
    if not check_and_update_limit(user_id, "video", 7):
        await message.answer(t(user_id, "video_limit_err"))
        await send_main_menu(message)
        return

    raw_url = message.text.strip()
    status = await message.answer(t(user_id, "video_loading"))
    
    try:
        video_link = await get_tiktok_direct_url(raw_url)
    except Exception as e:
        logging.error(f"Помилка отримання посилання: {e}")
        video_link = None
    
    if not video_link:
        try:
            await status.edit_text(t(user_id, "video_link_err"))
        except:
            await message.answer(t(user_id, "video_link_err"))
        await send_main_menu(message)
        return

    temp_path = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_link, timeout=30, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                if resp.status == 200:
                    if "text/html" in resp.headers.get("Content-Type", ""):
                        await status.edit_text(t(user_id, "video_html_err"))
                        await send_main_menu(message)
                        return

                    video_bytes = await resp.read()
                    if len(video_bytes) > 50 * 1024 * 1024:
                        await status.edit_text(t(user_id, "video_too_big"))
                        await send_main_menu(message)
                        return

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
                        temp_video.write(video_bytes)
                        temp_path = temp_video.name
                    
                    await message.answer_video(FSInputFile(temp_path), caption=t(user_id, "video_success_cap"))
                else:
                    await status.edit_text(t(user_id, "video_download_err"))
                    
        await status.delete()
        await send_main_menu(message, t(user_id, "ready_next"))
    except Exception as e:
        logging.error(f"Помилка надсилання відео: {e}")
        try:
            await status.edit_text(t(user_id, "video_download_err"))
        except:
            pass
        await send_main_menu(message)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

@dp.callback_query(F.data == "menu_audio")
async def cb_aud(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    text = t(user_id, "audio_menu_text")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

def format_text_with_punctuation(raw_text: str) -> str:
    """ПОКРАЩЕНА АВТОМАТИЧНА ПУНКТУАЦІЯ ТА РОЗБИТТЯ НА РЕЧЕННЯ"""
    if not raw_text:
        return ""
    
    cleaned = raw_text.strip()
    
    # Питальні слова на початку або всередині
    question_words = ["як ", "що ", "де ", "чому ", "коли ", "чи ", "хто ", "яка ", "який ", "яке ", "які ", "скільки "]
    
    # Розбиваємо за ключовими комами/сполучниками для читабельності
    conjunctions = [" а ", " але ", " бо ", " тому що ", " якщо ", " коли ", " щоб ", " і ", " та "]
    for conj in conjunctions:
        # Ставимо кому перед сполучниками, якщо їх немає
        cleaned = re.sub(r'(\S)' + conj, r'\1,' + conj, cleaned)

    # Розбиваємо текст на слова для побудови речень
    words = cleaned.split()
    sentences = []
    current_sentence = []
    
    for word in words:
        current_sentence.append(word)
        # Якщо речення набрало 8-10 слів або закінчується питальним словом
        if len(current_sentence) >= 8:
            sentence_str = " ".join(current_sentence)
            # Перевіряємо чи є питальне слово на початку
            is_quest = any(sentence_str.lower().startswith(qw) for qw in question_words)
            ending = "?" if is_quest else "."
            if not sentence_str.endswith((".", "!", "?")):
                sentence_str += ending
            sentences.append(sentence_str)
            current_sentence = []
            
    if current_sentence:
        sentence_str = " ".join(current_sentence)
        is_quest = any(sentence_str.lower().startswith(qw) for qw in question_words)
        ending = "?" if is_quest else "."
        if not sentence_str.endswith((".", "!", "?")):
            sentence_str += ending
        sentences.append(sentence_str)
        
    # Формуємо абзаци з великої літери
    paragraphs = []
    for i in range(0, len(sentences), 2):
        paragraph = " ".join(sentences[i:i+2])
        # Робимо першу літеру великою після крапки/питального знака
        paragraph = re.sub(r'([.?!]\s+)([a-zа-яєіїґ])', lambda m: m.group(1) + m.group(2).upper(), paragraph)
        paragraphs.append(paragraph)
        
    # Перша літера всього тексту теж велика
    if paragraphs:
        paragraphs[0] = paragraphs[0][0].upper() + paragraphs[0][1:]
        
    return "\n\n".join(paragraphs)

@dp.message(F.voice | F.audio)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    max_duration = 900 if is_pro else 120 
    duration = message.voice.duration if message.voice else (message.audio.duration or 0)
    
    if duration > max_duration:
        limit_text = "15 minutes" if is_pro else "2 minutes"
        await message.answer(t(user_id, "audio_too_long", limit_text=limit_text))
        await send_main_menu(message)
        return

    if not check_and_update_limit(user_id, "voice", 4):
        await message.answer(t(user_id, "audio_limit_err"))
        await send_main_menu(message)
        return

    status_msg = await message.answer(t(user_id, "audio_recognizing"))
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file_info = await bot.get_file(file_id)
    
    ogg_path = tempfile.mktemp(suffix=".ogg")
    wav_path = tempfile.mktemp(suffix=".wav")

    try:
        await bot.download_file(file_info.file_path, ogg_path)

        def convert_and_recognize():
            sound = AudioSegment.from_file(ogg_path)
            sound.export(wav_path, format="wav")
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                u_lang = get_user_lang(user_id)
                sr_lang = "uk-UA" if u_lang == "uk" else ("pl-PL" if u_lang == "pl" else "en-US")
                raw = r.recognize_google(audio_data, language=sr_lang)
                return format_text_with_punctuation(raw)

        loop = asyncio.get_running_loop()
        recognized_text = await loop.run_in_executor(None, convert_and_recognize)

        await status_msg.edit_text(t(user_id, "audio_success", recognized_text=recognized_text), parse_mode="Markdown")
        await send_main_menu(message, t(user_id, "ready_next"))

    except sr.UnknownValueError:
        await status_msg.edit_text(t(user_id, "audio_unknown_err"))
        await send_main_menu(message)
    except Exception as e:
        logging.error(f"Помилка розпізнавання: {e}")
        await status_msg.edit_text(t(user_id, "audio_proc_err"))
        await send_main_menu(message)
    finally:
        for p in [ogg_path, wav_path]:
            try:
                if os.path.exists(p): os.remove(p)
            except:
                pass

@dp.callback_query(F.data == "menu_ai")
async def cb_ai_menu(callback: types.CallbackQuery):
    await show_ai(callback)

async def show_ai(target):
    user_id = target.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    if not is_pro:
        data = load_json_file(LIMITS_FILE, {})
        u_limits = data.get(str(user_id), {})
        if u_limits.get("ai", 0) >= 6:
            text = t(user_id, "ai_limit_err")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(user_id, "buy_pro_inline"), callback_data="buy_pro")],
                [InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]
            ])
            if isinstance(target, types.CallbackQuery):
                await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
                await target.answer()
            else:
                await target.answer(text, reply_markup=kb, parse_mode="Markdown")
            return

    ai_waiting_users.add(user_id)
    text = t(user_id, "ai_prompt_text")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]])
    
    if isinstance(target, types.CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except:
            await target.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.message(F.text)
async def handle_text_messages(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id in ai_waiting_users:
        if not check_and_update_limit(user_id, "ai", 6):
            ai_waiting_users.discard(user_id)
            await message.answer(t(user_id, "ai_exhausted"))
            await send_main_menu(message)
            return
            
        wait_msg = await message.answer(t(user_id, "ai_generating", text=text))
        await asyncio.sleep(1)
        
        u_lang = get_user_lang(user_id)
        
        formats_uk = [
            ("POV-огляд (З першої особи)", "Зніміть відео від першої особи, ніби глядач сам взаємодіє з цим.", "Покажіть дрібні деталі зблизька, які зазвичай ніхто не помічає."),
            ("Екстремальний стрес-тест", "Перевірте тему на витривалість, міцність або максимальні навантаження.", "Зробіть несподівану дію вже на 5-й секунді відео."),
            ("Топ-3 приховані фішки", "Розкрийте секретні нюанси та лайфхаки, про які мовчать інші оглядачі.", "Використайте динамічний монтаж під швидкий трендовий біт."),
            ("Чесний розбір без цензури", "Розкажіть всю правду, плюси та мінуси, з якими стикаються на практиці.", "Почніть з інтригуючого або суперечливого твердження."),
            ("Побудова з нуля / Покроковий гайд", "Покажіть процес створення або налаштування від А до Я за короткий час.", "Змонтуйте відео у форматі швидкого таймлапсу з анімацією.")
        ]
        
        formats_pl = [
            ("Przegląd POV (Z pierwszej osoby)", "Nagraj wideo z perspektywy pierwszej osoby.", "Pokaż bliskie detale, na które nikt nie zwraca uwagi."),
            ("Test obciążeniowy", "Przetestuj temat pod kątem wytrzymałości i granic możliwości.", "Zrób niespodziewany ruch na 5. sekundzie wideo."),
            ("Top 3 ukryte funkcje", "Odkryj mało znane niuanse i triki.", "Użyj dynamicznego montażu pod szybki bit.")
        ]

        formats_en = [
            ("POV Review (First-person view)", "Shoot a video from a first-person perspective.", "Show close-up details that people usually miss."),
            ("Stress Test / Experiment", "Test the subject for durability and limits.", "Make an unexpected move in the first 5 seconds."),
            ("Top 3 Hidden Features", "Reveal secret nuances and life hacks.", "Use fast dynamic editing.")
        ]

        pool = formats_uk if u_lang == "uk" else (formats_pl if u_lang == "pl" else formats_en)
        selected_formats = random.sample(pool, min(3, len(pool)))
        
        hooks = [
            f"«Ніхто вам про це не розкаже щодо {text}...»",
            f"«Чому всі помиляються, коли говорять про {text}?»",
            f"«Ось що буде, якщо спробувати {text} на максималках...»",
            f"«Головний секрет успіху з {text}, який приховують...»",
            f"«Це єдине відео про {text}, яке вам дійсно потрібно побачити.»"
        ]
        
        ctas = [
            "Напишіть у коментарях вашу думку!",
            "Збережіть відео, щоб не втратити ідею.",
            "Підпишіться, у наступній частині буде продовження!"
        ]

        if u_lang == "uk":
            header = f"🔥 **3 Унікальні концепції для відео на тему:** _{text}_\n"
            lbl_var = "Варіант"
            lbl_format = "📌 Формат:"
            lbl_action = "🛠 Дія у кадрі:"
            lbl_secret = "💡 Порада:"
            lbl_hook = "🪝 Хук:"
            lbl_cta = "🎬 CTA:"
        elif u_lang == "pl":
            header = f"🔥 **3 Unikalne koncepcje wideo na temat:** _{text}_\n"
            lbl_var = "Wariant"
            lbl_format = "📌 Format:"
            lbl_action = "🛠 Działanie:"
            lbl_secret = "💡 Wskazówka:"
            lbl_hook = "🪝 Hak:"
            lbl_cta = "🎬 CTA:"
        else:
            header = f"🔥 **3 Unique video concepts for:** _{text}_\n"
            lbl_var = "Option"
            lbl_format = "📌 Format:"
            lbl_action = "🛠 Action:"
            lbl_secret = "💡 Tip:"
            lbl_hook = "🪝 Hook:"
            lbl_cta = "🎬 CTA:"

        response_blocks = [header]
        
        for idx, fmt in enumerate(selected_formats, 1):
            h = random.choice(hooks)
            c = random.choice(ctas)
            block = (
                f"\n--- <b>{lbl_var} #{idx}</b> ---\n"
                f"{lbl_format} {fmt[0]}\n"
                f"{lbl_action} {fmt[1]}\n"
                f"{lbl_secret} {fmt[2]}\n"
                f"{lbl_hook} {h}\n"
                f"{lbl_cta} {c}\n"
            )
            response_blocks.append(block)
            
        clean_tag = text.replace(' ', '').replace('!', '').replace('?', '').lower()
        response_blocks.append(f"\n🏷 `#тренди #{clean_tag} #viral #foryou #рек`")
        
        final_response = "".join(response_blocks)
        
        try:
            await wait_msg.edit_text(final_response, parse_mode="Markdown")
        except:
            await message.answer(final_response, parse_mode="Markdown")

        ai_waiting_users.discard(user_id)
        await send_main_menu(message, t(user_id, "ready_next"))
        return

    await message.answer(t(user_id, "fallback"))
    await send_main_menu(message)

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот оновлено: покращено пунктуацію голосу, завантаження TikTok та прибрано зайвий текст!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
