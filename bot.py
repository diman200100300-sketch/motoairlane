import asyncio
import logging
import json
import os
import datetime
import threading
import random
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

# --- ПОКРАЩЕНИЙ ВЕБСЕРВЕР ДЛЯ RENDER (ЗАХИСТ ВІД SIGTERM) ---
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
# -----------------------------------------------------

# ТОКЕН ТА АДМІН (Рекомендується брати з системних змінних)
TOKEN = os.environ.get("BOT_TOKEN", "8949626852:AAGWNxuNaa4atk2BBtq8VFP64EUpu9acwCg")  
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

# --- СЛОВНИК ПЕРЕКЛАДІВ ---
LANGS = {
    "uk": {
        "start_msg": "Привіт! Я твій надійний помічник для завантаження відео, транскрипції голосу та генерації контенту.",
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
        "admin_request": "🔔 Заявка на PRO!\nКористувач: {user_link} (`{user_id}`)\nАктивуйте командою:\n`/givepro {user_id}`",
        "givepro_success": "✅ Користувачу `{tid}` успішно активовано та збережено PRO!",
        "pro_activated_notif": "🎉 Вашу оплату підтверджено! PRO активовано.",
        "video_menu_text": "🎥 **Завантаження відео**\n\nНадішліть посилання на відео з **TikTok**, і я завантажу його без водяного знака!\n\n📌 *Безкоштовно:* до 7 разів на день.",
        "video_limit_err": "❌ Вичерпано безкоштовний ліміт завантаження відео на сьогодні (7/7).\nОформіть PRO!",
        "video_loading": "⏳ Завантажую відео, зачекайте...",
        "video_link_err": "❌ Не вдалося отримати пряме посилання на відео. Спробуйте інше.",
        "video_html_err": "❌ Помилка: Сервер повернув HTML-сторінку замість медіафайлу.",
        "video_too_big": "❌ Відео занадто велике (понад 50 МБ).",
        "video_success_cap": "✅ Ось ваше відео без водяного знака!",
        "video_download_err": "❌ Помилка при завантаженні файлу.",
        "audio_menu_text": "🎙 **Аудіо інструменти (Перетворення в текст)**\n\nНадішліть голосове повідомлення або аудіофайл, і я переведу його у текст!\n\n⏱ **Ліміти тривалості:**\n• Безкоштовний: до **2 хвилин** (до 4 разів на день)\n• PRO: до **15 хвилин** (безлімітно щодня)",
        "audio_too_long": "❌ Файл занадто довгий! Максимальна тривалість — {limit_text}.",
        "audio_limit_err": "❌ Вичерпано безкоштовний ліміт транскрипції на сьогодні (4/4).",
        "audio_recognizing": "⏳ Розпізнаю аудіо та перетворюю на текст...",
        "audio_success": "📝 **Розпізнаний текст:**\n\n_{recognized_text}_",
        "audio_unknown_err": "❌ Не вдалося розпізнати мову в цьому аудіо.",
        "audio_proc_err": "❌ Сталася помилка при обробці аудіофайлу.",
        "ai_limit_err": "⭐ **Ви вичерпали 6 безкоштовних генерацій ідей на сьогодні.**\n\nПридбайте PRO для безліміту!",
        "ai_prompt_text": "💡 **Креативний ШІ Генератор ідей**\n\nНапишіть **будь-яку тему чи слово** (наприклад: авто, поїзд, ігри, лайфхак), і я згенерую унікальні концепції!",
        "ai_generating": "🧠 Створюю унікальні концепції для «{text}»...",
        "ai_exhausted": "❌ Вичерпано безкоштовний ліміт генерації ідей на сьогодні (6/6).",
        "lang_select_title": "🌐 Оберіть мову / Wybierz język / Choose language:",
        "lang_changed": "✅ Мову успішно змінено на Українську!",
        "ready_next": "Готово! Що робимо далі?",
        "fallback": "Скористайтеся меню нижче або натисніть /start для вибору розділу."
    },
    "pl": {
        "start_msg": "Cześć! Jestem Twoim niezawodnym pomocnikiem do pobierania wideo, transkrypcji głosu i generowania treści.",
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
        "buy_title": "💎 **Uzyskanie PRO**\nCena: **19 zł/miesiąc**\nPłatność przez **BLIK** na numer:\n`+48 733 985 396`\n\nPo przelewie kliknij przycisk poniżej:",
        "paid_btn": "📩 Zapłaciłem",
        "paid_sent": "Zgłoszenie zostało wysłane do administratora!",
        "admin_request": "🔔 Zgłoszenie PRO!\nUżytkownik: {user_link} (`{user_id}`)\nAktywuj komendą:\n`/givepro {user_id}`",
        "givepro_success": "✅ Użytkownikowi `{tid}` pomyślnie aktywowano i zapisano PRO!",
        "pro_activated_notif": "🎉 Twoja płatność została potwierdzona! PRO aktywowane.",
        "video_menu_text": "🎥 **Pobieranie wideo**\n\nWyślij link do wideo z **TikTok**, a pobieram je bez znaku wodnego!\n\n📌 *Darmowe:* do 7 razy dziennie.",
        "video_limit_err": "❌ Wyczerpano darmowy limit pobierania wideo na dziś (7/7).\nKup PRO!",
        "video_loading": "⏳ Pobieram wideo, proszę czekać...",
        "video_link_err": "❌ Nie udało się uzyskać bezpośredniego linku do wideo. Spróbuj innego.",
        "video_html_err": "❌ Błąd: Serwer zwrócił stronę HTML zamiast pliku multimedialnego.",
        "video_too_big": "❌ Wideo jest za duże (powyżej 50 MB).",
        "video_success_cap": "✅ Oto Twoje wideo bez znaku wodnego!",
        "video_download_err": "❌ Błąd podczas pobierania pliku.",
        "audio_menu_text": "🎙 **Narzędzia audio (Konwersja na tekst)**\n\nWyślij wiadomość głosową lub plik audio, a przekonwertuję go na tekst!\n\n⏱ **Limity czasu trwania:**\n• Darmowy: do **2 minut** (do 4 razy dziennie)\n• PRO: do **15 minut** (bez limitu codziennie)",
        "audio_too_long": "❌ Plik jest za długi! Maksymalny czas trwania to {limit_text}.",
        "audio_limit_err": "❌ Wyczerpano darmowy limit transkrypcji na dziś (4/4).",
        "audio_recognizing": "⏳ Rozpoznaję audio i konwertuję na tekst...",
        "audio_success": "📝 **Rozpoznany tekst:**\n\n_{recognized_text}_",
        "audio_unknown_err": "❌ Nie udało się rozpoznać mowy w tym audio.",
        "audio_proc_err": "❌ Wystąpił błąd podczas przetwarzania pliku audio.",
        "ai_limit_err": "⭐ **Wyczerpano 6 darmowych generacji pomysłów na dziś.**\n\nKup PRO dla braku limitów!",
        "ai_prompt_text": "💡 **Kreatywny generator pomysłów AI**\n\nNapisz **dowolny temat lub słowo** (np.: auto, pociąg, gry, lifehack), a wygeneruję unikalne koncepcje!",
        "ai_generating": "🧠 Tworzę unikalne koncepcje dla „{text}”...",
        "ai_exhausted": "❌ Wyczerpano darmowy limit generacji pomysłów na dziś (6/6).",
        "lang_select_title": "🌐 Wybierz język / Оберіть мову / Choose language:",
        "lang_changed": "✅ Język został pomyślnie zmieniony na Polski!",
        "ready_next": "Gotowe! Co robimy dalej?",
        "fallback": "Skorzystaj z menu poniżej lub wpisz /start, aby wybrać sekcję."
    },
    "en": {
        "start_msg": "Hello! I am your reliable assistant for downloading videos, voice transcription, and content generation.",
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
        "buy_title": "💎 **Get PRO**\nPrice: **19 zł/month**\nPayment via **BLIK** to number:\n`+48 733 985 396`\n\nAfter transfer, click the button below:",
        "paid_btn": "📩 I have paid",
        "paid_sent": "Application sent to administrator!",
        "admin_request": "🔔 PRO Request!\nUser: {user_link} (`{user_id}`)\nActivate with command:\n`/givepro {user_id}`",
        "givepro_success": "✅ Successfully activated and saved PRO for user `{tid}`!",
        "pro_activated_notif": "🎉 Your payment has been confirmed! PRO is active.",
        "video_menu_text": "🎥 **Video Downloader**\n\nSend a link to a **TikTok** video and I will download it without a watermark!\n\n📌 *Free:* up to 7 times a day.",
        "video_limit_err": "❌ Free video download limit reached for today (7/7).\nGet PRO!",
        "video_loading": "⏳ Downloading video, please wait...",
        "video_link_err": "❌ Failed to get direct video link. Try another one.",
        "video_html_err": "❌ Error: Server returned an HTML page instead of media file.",
        "video_too_big": "❌ Video is too large (over 50 MB).",
        "video_success_cap": "✅ Here is your video without a watermark!",
        "video_download_err": "❌ Error downloading the file.",
        "audio_menu_text": "🎙 **Audio Tools (Speech to text)**\n\nSend a voice message or audio file and I will convert it to text!\n\n⏱ **Duration limits:**\n• Free: up to **2 minutes** (up to 4 times a day)\n• PRO: up to **15 minutes** (unlimited daily)",
        "audio_too_long": "❌ File is too long! Maximum duration is {limit_text}.",
        "audio_limit_err": "❌ Free transcription limit reached for today (4/4).",
        "audio_recognizing": "⏳ Recognizing audio and converting to text...",
        "audio_success": "📝 **Recognized text:**\n\n_{recognized_text}_",
        "audio_unknown_err": "❌ Could not recognize speech in this audio.",
        "audio_proc_err": "❌ An error occurred while processing the audio file.",
        "ai_limit_err": "⭐ **You have exhausted 6 free idea generations for today.**\n\nGet PRO for unlimited access!",
        "ai_prompt_text": "💡 **Creative AI Idea Generator**\n\nType **any topic or word** (e.g., cars, trains, games, lifehack) and I will generate unique concepts!",
        "ai_generating": "🧠 Creating unique concepts for '{text}'...",
        "ai_exhausted": "❌ Free idea generation limit reached for today (6/6).",
        "lang_select_title": "🌐 Choose language / Оберіть мову / Wybierz język:",
        "lang_changed": "✅ Language successfully changed to English!",
        "ready_next": "Done! What's next?",
        "fallback": "Use the menu below or type /start to select a section."
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
        data[str_uid] = {
            "date": today,
            "ai": 0,
            "video": 0,
            "voice": 0
        }

    current_count = data[str_uid].get(action_type, 0)
    if current_count >= max_limit:
        return False

    data[str_uid][action_type] = current_count + 1
    save_json_file(LIMITS_FILE, data)
    return True

def save_pro_users(users):
    save_json_file(PRO_FILE, users)

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
            await bot.send_message(ADMIN_ID, t(ADMIN_ID, "admin_request", user_link=user_link, user_id=user.id), parse_mode="Markdown")
        except:
            pass
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
        await message.answer(t(ADMIN_ID, "givepro_success", tid=tid))
        await bot.send_message(tid, t(tid, "pro_activated_notif"))
    except:
        await message.answer("Помилка в ID.")

@dp.callback_query(F.data == "menu_video")
async def cb_vid(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    text = t(user_id, "video_menu_text")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

async def get_tiktok_direct_url(video_url: str) -> str:
    def extract_ytdlp():
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'extractor_args': {'tiktok': {'webpage_download': True}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url')
            except Exception as e:
                logging.error(f"Помилка yt-dlp: {e}")
                return None

    loop = asyncio.get_running_loop()
    direct_url = await loop.run_in_executor(None, extract_ytdlp)
    if direct_url:
        return direct_url

    api_url = f"https://www.tikwm.com/api/?url={video_url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        return data["data"]["play"]
    except Exception as e:
        logging.error(f"Помилка резервного API: {e}")
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
    
    video_url = raw_url
    if "vm.tiktok.com" in raw_url or "vt.tiktok.com" in raw_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(raw_url, allow_redirects=True, timeout=12, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                    video_url = str(resp.url)
        except Exception as e:
            logging.error(f"Помилка розгортання короткого посилання: {e}")

    video_link = await get_tiktok_direct_url(video_url)
    
    if not video_link:
        await status.edit_text(t(user_id, "video_link_err"))
        await send_main_menu(message)
        return

    temp_path = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_link, timeout=35, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get("Content-Type", "")
                    if "text/html" in content_type:
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
                    
                    video_file = FSInputFile(temp_path)
                    await message.answer_video(video_file, caption=t(user_id, "video_success_cap"))
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

@dp.message(F.voice | F.audio)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    max_duration = 900 if is_pro else 120 
    duration = message.voice.duration if message.voice else (message.audio.duration or 0)
    
    if duration > max_duration:
        limit_text = "15 minutes / 15 хвилин" if is_pro else "2 minutes / 2 хвилини"
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
                text = r.recognize_google(audio_data, language=sr_lang)
                return text

        loop = asyncio.get_running_loop()
        recognized_text = await loop.run_in_executor(None, convert_and_recognize)

        await status_msg.edit_text(t(user_id, "audio_success", recognized_text=recognized_text), parse_mode="Markdown")
        await send_main_menu(message, t(user_id, "ready_next"))

    except sr.UnknownValueError:
        await status_msg.edit_text(t(user_id, "audio_unknown_err"))
        await send_main_menu(message)
    except Exception as e:
        logging.error(f"Помилка розпізнавання голосу: {e}")
        await status_msg.edit_text(t(user_id, "audio_proc_err"))
        await send_main_menu(message)
    finally:
        for p in [ogg_path, wav_path]:
            try:
                if os.path.exists(p):
                    os.remove(p)
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
        ai_used = u_limits.get("ai", 0)
        
        if ai_used >= 6:
            text = t(user_id, "ai_limit_err")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(user_id, "buy_pro_inline"), callback_data="buy_pro")],
                [InlineKeyboardButton(text=t(user_id, "back"), callback_data="back_home")]
            ]]
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
        
        if u_lang == "pl":
            formats_pool = [
                ("Eksstremalny test / Test stresowy", "Sprawdzenie granic możliwości w najtrudniejszych warunkach"),
                ("Prawda bez cenzury / Obalanie mitów", "Przełamywanie popularnych schematów i szczera rozmowa"),
                ("Estetyczny POV / Kinowy przegląd", "Pełne oddanie atmosfery przez wciągające wizualia i dźwięk"),
                ("Sekretne lifehacki i ukryte funkcje", "To, o czym zwykle milczą instrukcje i profesjonalni eksperti"),
                ("Podróż w czasie / Porównanie pokoleń", "Ewolucja i porównanie tego, jak wszystko zmieniało się od przeszłości do teraźniejszości")
            ]
            hooks_pool = [
                f"«Nikt w internecie nie mówi o tym głównym ukrytym problemzie z {text}.»",
                f"«Co się stanie, jeśli użyjesz {text} na absolutnie maksymalnych ustawieniach?»",
                f"«Spędziłem cały tydzień, żeby ogarnąć {text}, i oto szokujący wynik.»",
                f"«Ten śmiertelny błąd z {text} popełnia 95% ludzi przez zwykłą niewiedzę.»"
            ]
            twists_pool = [
                "Niespodziewany finał, który całkowicie niszczy początkowy stereotyp widza.",
                "Nagłe cięcie kadru w kulminacyjnym momencie przy mocnym bicie muzycznym.",
                "Intrygujące prowokacyjne pytanie na końcu, zmuszające każdego do skomentowania."
            ]
            resp_title = "🔥 **Unikalne koncepcje kreatywne**"
            theme_lbl = "🎯 **Temat:**"
            feat_lbl = "• *Główny haczyk:* "
            hook_lbl = "• *Hook (0-3 sek):* "
            tw_lbl = "• *Finał:* "
            tags_lbl = "🏷 **Trendujące hashtagi:**"
        elif u_lang == "en":
            formats_pool = [
                ("Extreme Test / Stress Test", "Testing the limits of capabilities in the harshest real conditions"),
                ("Uncensored Truth / Myth Busting", "Breaking popular templates and speaking openly"),
                ("Aesthetic POV / Cinematic Review", "Full atmospheric immersion through engaging visuals and sound"),
                ("Secret Lifehacks & Hidden Features", "Things manuals and professional experts usually stay quiet about"),
                ("Time Travel / Generation Comparison", "Evolution and comparison of how things changed from past to present")
            ]
            hooks_pool = [
                f"«Nobody on the internet is talking about this main hidden issue with {text}.»",
                f"«What happens if you use {text} at absolute maximum settings?»",
                f"«I spent a whole week figuring out {text}, and here is the shocking result.»",
                f"«95% of people make this fatal mistake with {text} out of sheer ignorance.»"
            ]
            twists_pool = [
                "An unexpected finale that completely shatters the viewer's initial stereotype.",
                "A sharp frame cut at the climax moment under a striking music beat.",
                "An intriguing provocative question at the end forcing everyone to comment."
            ]
            resp_title = "🔥 **Unique Creative Concepts**"
            theme_lbl = "🎯 **Topic:**"
            feat_lbl = "• *Main feature:* "
            hook_lbl = "• *Hook (0-3 sec):* "
            tw_lbl = "• *Ending:* "
            tags_lbl = "🏷 **Trending hashtags:**"
        else:
            formats_pool = [
                ("Екстремальний тест-драйв / Стрес-тест", "Перевірка межі можливостей у найсуворіших реальних умовах"),
                ("Правда без цензури / Розвінчання міфів", "Розрив популярних шаблонів та відверта розмова на чистоту"),
                ("Естетичний POV / Кінематографічний огляд", "Повна передача атмосфери через захопливий візуал та звук"),
                ("Секретні лайфхаки та приховані функції", "Те, про що зазвичай мовчать інструкції та професійні експерти"),
                ("Подорож у часі / Порівняння поколінь", "Еволюція та порівняння того, як усе змінювалося від минулого до сьогодення")
            ]
            hooks_pool = [
                f"«Ніхто в інтернеті не розповідає про цю головну приховану проблему з {text}.»",
                f"«Що станеться, якщо використати {text} на абсолютно максимальних налаштуваннях?»",
                f"«Я витрачив цілий тиждень, щоб розібратися з {text}, і ось шокуючий результат.»",
                f"«Цю фатальну помилку з {text} роблять 95% людей через банальне незнання.»"
            ]
            twists_pool = [
                "Неочікуваний фінал, який повністю ламає початковий стереотип глядача.",
                "Різкий обрив кадру під кульмінаційний музичний біт або ефектна тиша.",
                "Інтригуюче провокативне запитання наприкінці, що змушує кожного написати коментар."
            ]
            resp_title = "🔥 **Унікальні креативні концепції**"
            theme_lbl = "🎯 **Тема:**"
            feat_lbl = "• *Головна фішка:* "
            hook_lbl = "• *Хук (0-3 сек):* "
            tw_lbl = "• *Розв'язка:* "
            tags_lbl = "🏷 **Трендові хештеги:**"

        selected_formats = random.sample(formats_pool, 3)
        h_choices = random.sample(hooks_pool, 3)
        t_choices = random.sample(twists_pool, 3)

        response_text = (
            f"{resp_title}\n"
            f"{theme_lbl} _{text}_\n\n"
            f"1️⃣ **Format 1: «{selected_formats[0][0]}»**\n"
            f"   {feat_lbl}{selected_formats[0][1]}.\n"
            f"   {hook_lbl}{h_choices[0]}\n"
            f"   {tw_lbl}{t_choices[0]}\n\n"
            f"2️⃣ **Format 2: «{selected_formats[1][0]}»**\n"
            f"   {feat_lbl}{selected_formats[1][1]}.\n"
            f"   {hook_lbl}{h_choices[1]}\n"
            f"   {tw_lbl}{t_choices[1]}\n\n"
            f"3️⃣ **Format 3: «{selected_formats[2][0]}»**\n"
            f"   {feat_lbl}{selected_formats[2][1]}.\n"
            f"   {hook_lbl}{h_choices[2]}\n"
            f"   {tw_lbl}{t_choices[2]}\n\n"
            f"{tags_lbl} `#тренди #{text.replace(' ', '')} #viral #foryou #tiktok`"
        )
        
        try:
            await wait_msg.edit_text(response_text, parse_mode="Markdown")
        except:
            await message.answer(response_text, parse_mode="Markdown")

        ai_waiting_users.discard(user_id)
        await send_main_menu(message, t(user_id, "ready_next"))
        return

    await message.answer(t(user_id, "fallback"))
    await send_main_menu(message)

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот запущено успішно з підтримкою кількох мов!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
