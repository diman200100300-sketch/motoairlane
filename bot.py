import os
import io
import sys
import logging
import asyncio
import random
import sqlite3
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiohttp
import aiofiles
import speech_recognition as sr
from PIL import Image
from rembg import remove

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile, FSInputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ---------------------------------------------------------
# 1. ЛОГУВАННЯ ТА КОНФІГУРАЦІЯ
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_activity.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("ToolBoxAI")

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CREATOR_ID = int(os.getenv("CREATOR_ID", "0"))
DB_FILE = "toolbox_master.db"

# ---------------------------------------------------------
# 2. ПОВНА БАЗА ДАНИХ (SQLite)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Таблиця користувачів
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            language TEXT DEFAULT 'uk',
            is_banned INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            joined_at TEXT
        )
    """)
    
    # Таблиця статистики використання інструментів
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            feature TEXT,
            used_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def db_add_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name, language, joined_at)
        VALUES (?, ?, ?, 'uk', ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (user_id, username, first_name, now))
    conn.commit()
    conn.close()

def db_get_user_language(user_id: int) -> str:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 'uk'

def db_set_user_language(user_id: int, lang: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def db_log_usage(user_id: int, feature: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO usage_stats (user_id, feature, used_at) VALUES (?, ?, ?)", (user_id, feature, now))
    conn.commit()
    conn.close()

def db_get_stats() -> Dict[str, Any]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM usage_stats")
    total_usage = cursor.fetchone()[0]
    
    cursor.execute("SELECT feature, COUNT(*) FROM usage_stats GROUP BY feature")
    feature_stats = dict(cursor.fetchall())
    
    conn.close()
    return {
        "total_users": total_users,
        "banned_users": banned_users,
        "total_usage": total_usage,
        "feature_stats": feature_stats
    }

def db_get_all_user_ids() -> List[int]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def db_set_ban_status(user_id: int, status: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

def db_is_banned(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

# ---------------------------------------------------------
# 3. ПОЛІГЛОТ-СЛОВНИКИ ТЕКСТІВ (UK, PL, EN)
# ---------------------------------------------------------
TEXTS = {
    'uk': {
        'main_title': '⚙️ **Головне меню ToolBox AI**\n\nОберіть потрібний інструмент з панелі нижче:',
        'btn_tiktok': '📥 TikTok Downloader (No WM)',
        'btn_ideas': '💡 ШІ Генератор Ідей',
        'btn_stt': '🎙 Аудіо/Відео в Текст',
        'btn_photoshop': '🎨 ШІ-Фотошоп (Видалення фону)',
        'btn_lang': '🌐 Змінити мову / Language',
        'btn_owner': '👑 Панель Власника',
        'btn_admin': '🛡 Панель Адміністратора',
        'btn_back': '« Повернутися в меню',
        'prompt_tiktok': '📥 **TikTok Downloader**\n\nНадішліть посилання на відео з TikTok (наприклад: `https://vm.tiktok.com/...` або `https://www.tiktok.com/@user/video/...`):',
        'prompt_ideas': '💡 **ШІ Генератор Ідей**\n\nВведіть тему, тему відео або нішу (наприклад: *BMW E60, Brawl Stars, Ремонт квартир, Фінанси*):',
        'prompt_stt': '🎙 **Конвертер Медіа в Текст**\n\nНадішліть голосове повідомлення, аудіофайл (.mp3, .wav) або відео кліп (.mp4, .mov):',
        'prompt_photoshop': '🎨 **ШІ-Видалення фону**\n\nНадішліть фотографію (як фото або як файл PNG/JPG). Нейромережа видалить фон без втрати якості та артефактів:',
        'prompt_lang': '🌐 **Оберіть мову інтерфейсу / Select Interface Language:**',
        'lang_changed': '✅ Мову успішно змінено на **Українську** 🇺🇦',
        'tiktok_processing': '⏳ Завантажую відео без водяного знака з TikTok...',
        'tiktok_error': '❌ Помилка завантаження. Перевірте правильність посилання та спробуйте ще раз.',
        'stt_processing': '⏳ Конвертація файлу та розпізнавання мовлення через ШІ...',
        'stt_error': '❌ Не вдалося розпізнати мовлення. Перевірте чіткість аудіо або формат файлу.',
        'stt_result': '📝 **Розпізнаний текст з пунктуацією:**\n\n',
        'ps_processing': '⏳ Виконується нейромережева обробка зображення...',
        'ps_success': '✂️ **Фон успішно видалено!** Зображення збережено у форматі PNG з прозорим фоном.',
        'ps_error': '❌ Помилка при обробці зображення. Переконайтеся, що на фото чітко видно об’єкт.',
        'owner_menu': '👑 **Панель Власника системи**\n\nВам доступне повне керування ботом, базою даних та адміністраторами.',
        'admin_menu': '🛡 **Панель Адміністратора**\n\nОберіть необхідну дію для керування спільнотою:',
        'access_denied': '⛔ Доступ заборонено! Ця функція доступна лише адміністрації.',
        'banned_msg': '⛔ Ваш акаунт заблоковано в системі.',
        'btn_stats': '📊 Статистика системи',
        'btn_broadcast': '📢 Масова розсилка',
        'btn_ban_user': '🚫 Заблокувати ID',
        'btn_unban_user': '✅ Розблокувати ID',
        'prompt_broadcast': '📢 Надішліть текст або медіа-повідомлення для масової розсилки всім користувачам:',
        'prompt_ban': '🚫 Введіть Telegram User ID для блокування:',
        'prompt_unban': '✅ Введіть Telegram User ID для розблокування:',
        'broadcast_start': '🚀 Розсилку розпочато...',
        'broadcast_done': '✅ Розсилку завершено!\n\n• Успішно доправлено: {success}\n• Заблокували бота: {failed}',
        'user_banned': '✅ Користувача ID {id} заблоковано.',
        'user_unbanned': '✅ Користувача ID {id} розблоковано.',
        'invalid_id': '❌ Некоректний ID користувача.'
    },
    'pl': {
        'main_title': '⚙️ **Menu Główne ToolBox AI**\n\nWybierz narzędzie z poniższego panelu:',
        'btn_tiktok': '📥 TikTok Downloader (Bez WM)',
        'btn_ideas': '💡 Generator Pomysłów AI',
        'btn_stt': '🎙 Audio/Wideo na Tekst',
        'btn_photoshop': '🎨 AI-Photoshop (Usuwanie tła)',
        'btn_lang': '🌐 Zmień język / Language',
        'btn_owner': '👑 Panel Właściciela',
        'btn_admin': '🛡 Panel Administratora',
        'btn_back': '« Powrót do menu',
        'prompt_tiktok': '📥 **TikTok Downloader**\n\nWyślij link do filmu na TikToku (np.: `https://vm.tiktok.com/...`):',
        'prompt_ideas': '💡 **Generator Pomysłów AI**\n\nWpisz temat, temat wideo lub niszę (np.: *BMW E60, Brawl Stars, Remont mieszkania*):',
        'prompt_stt': '🎙 **Konwerter Mediów na Tekst**\n\nWyślij wiadomość głosową, plik audio (.mp3, .wav) lub wideo (.mp4, .mov):',
        'prompt_photoshop': '🎨 **AI-Usuwanie Tła**\n\nWyślij zdjęcie. Sieć neuronowa usunie tło bez utraty jakości:',
        'prompt_lang': '🌐 **Wybierz język interfejsu / Select Interface Language:**',
        'lang_changed': '✅ Język został pomyślnie zmieniony na **Polski** 🇵🇱',
        'tiktok_processing': '⏳ Pobieranie wideo bez znaku wodnego z TikToka...',
        'tiktok_error': '❌ Błąd pobierania. Sprawdź poprawność linku i spróbuj ponownie.',
        'stt_processing': '⏳ Konwersja pliku i rozpoznawanie mowy przez AI...',
        'stt_error': '❌ Nie udało się rozpoznać mowy. Sprawdź jakość dźwięku.',
        'stt_result': '📝 **Rozpoznany tekst z interpunkcją:**\n\n',
        'ps_processing': '⏳ Przetwarzanie obrazu przez sieć neuronową...',
        'ps_success': '✂️ **Tło zostało pomyślnie usunięte!** Obraz zapisano w formacie PNG.',
        'ps_error': '❌ Błąd przetwarzania obrazu.',
        'owner_menu': '👑 **Panel Właściciela Systemu**\n\nMasz pełny dostęp do zarządzania botem i bazą danych.',
        'admin_menu': '🛡 **Panel Administratora**\n\nWybierz akcję do zarządzania systemem:',
        'access_denied': '⛔ Dostęp zabroniony! Funkcja tylko dla administracji.',
        'banned_msg': '⛔ Twoje konto zostało zablokowane.',
        'btn_stats': '📊 Statystyki Systemu',
        'btn_broadcast': '📢 Masowa Wysyłka',
        'btn_ban_user': '🚫 Zablokuj ID',
        'btn_unban_user': '✅ Odblokuj ID',
        'prompt_broadcast': '📢 Wyślij treść wiadomości do masowej wysyłki:',
        'prompt_ban': '🚫 Wprowadź Telegram User ID do zablokowania:',
        'prompt_unban': '✅ Wprowadź Telegram User ID do odblokowania:',
        'broadcast_start': '🚀 Rozpoczęto wysyłkę...',
        'broadcast_done': '✅ Wysyłka zakończona!\n\n• Dostarczono: {success}\n• Zablokowane: {failed}',
        'user_banned': '✅ Użytkownik ID {id} został zablokowany.',
        'user_unbanned': '✅ Użytkownik ID {id} został odblokowany.',
        'invalid_id': '❌ Nieprawidłowy ID użytkownika.'
    },
    'en': {
        'main_title': '⚙️ **ToolBox AI Main Menu**\n\nSelect a tool from the options below:',
        'btn_tiktok': '📥 TikTok Downloader (No WM)',
        'btn_ideas': '💡 AI Content Idea Generator',
        'btn_stt': '🎙 Audio/Video to Text',
        'btn_photoshop': '🎨 AI-Photoshop (BG Remover)',
        'btn_lang': '🌐 Change Language',
        'btn_owner': '👑 Owner Panel',
        'btn_admin': '🛡 Admin Panel',
        'btn_back': '« Back to Menu',
        'prompt_tiktok': '📥 **TikTok Downloader**\n\nSend a link to a TikTok video (e.g., `https://vm.tiktok.com/...`):',
        'prompt_ideas': '💡 **AI Idea Generator**\n\nEnter any topic, video theme, or niche (e.g., *BMW E60, Gaming, Crypto, Real Estate*):',
        'prompt_stt': '🎙 **Media to Text Converter**\n\nSend a voice message, audio file (.mp3, .wav) or video file (.mp4, .mov):',
        'prompt_photoshop': '🎨 **AI Background Remover**\n\nSend a photo. The AI will remove the background cleanly with zero artifacts:',
        'prompt_lang': '🌐 **Select Interface Language:**',
        'lang_changed': '✅ Language successfully set to **English** 🇬🇧',
        'tiktok_processing': '⏳ Downloading TikTok video without watermark...',
        'tiktok_error': '❌ Download error. Check the link and try again.',
        'stt_processing': '⏳ Converting file and processing AI speech recognition...',
        'stt_error': '❌ Failed to recognize speech. Check audio clarity.',
        'stt_result': '📝 **Transcribed Text with Punctuation:**\n\n',
        'ps_processing': '⏳ AI neural network processing in progress...',
        'ps_success': '✂️ **Background removed successfully!** Image saved in PNG format.',
        'ps_error': '❌ Image processing error.',
        'owner_menu': '👑 **System Owner Panel**\n\nYou have complete control over system database and settings.',
        'admin_menu': '🛡 **Administrator Panel**\n\nChoose an administrative action:',
        'access_denied': '⛔ Access Denied! Restricted to system administration.',
        'banned_msg': '⛔ Your account is banned from using this bot.',
        'btn_stats': '📊 System Statistics',
        'btn_broadcast': '📢 Mass Broadcast',
        'btn_ban_user': '🚫 Ban User ID',
        'btn_unban_user': '✅ Unban User ID',
        'prompt_broadcast': '📢 Send the message content you want to broadcast to all users:',
        'prompt_ban': '🚫 Enter Telegram User ID to ban:',
        'prompt_unban': '✅ Enter Telegram User ID to unban:',
        'broadcast_start': '🚀 Broadcast initiated...',
        'broadcast_done': '✅ Broadcast finished!\n\n• Delivered: {success}\n• Failed/Blocked: {failed}',
        'user_banned': '✅ User ID {id} has been banned.',
        'user_unbanned': '✅ User ID {id} has been unbanned.',
        'invalid_id': '❌ Invalid User ID.'
    }
}

# ---------------------------------------------------------
# 4. РАЗВЕРНУТА БАЗА ШАБЛОНІВ ІДЕЙ (UK, PL, EN)
# ---------------------------------------------------------
IDEA_TEMPLATES = {
    'uk': {
        'auto': [
            "🏎 **Контент-план: Повний Тест-Драйв та Огляд**\n\n• **Заголовок:** «Чому всі купують {topic} у 2026 році?»\n• **Хук (перші 3 сек):** «Подумай двічі, перш ніж купувати {topic}... І ось чому!»\n• **Сценарій:**\n 1. Покажи 3 приховані плюси салону та керованості.\n 2. Назви 3 найдорожчі проблеми в обслуговуванні.\n 3. Порівняй ціну з конкурентами на ринку.\n• **Заклик до дії (CTA):** «Напиши в коментарях: узяв би собі чи обрав би аналог?»",
            "🛠 **Контент-план: Топ Помилок Власника**\n\n• **Заголовок:** «Ніколи не роби цього з {topic}!»\n• **Хук:** «Ця помилка коштуватиме тобі $1000 ремонту на {topic}!»\n• **Сценарій:**\n 1. Розбір помилок при заміні мастила та обслуговуванні.\n 2. Чому економія на запчастинах знищує цю модель.\n 3. Як продовжити ресурс двигуна удвічі.\n• **CTA:** «Збережи це відео, щоб не потрапити на дорогий ремонт!»"
        ],
        'gaming': [
            "🎮 **Контент-план: Секретні Фішки та Лайфхаки**\n\n• **Заголовок:** «Секретний трюк у {topic}, про який знають лише 1% гравців!»\n• **Хук:** «Хочеш підняти свій ранг у {topic} за 5 хвилин? Дивись уважно!»\n• **Сценарій:**\n 1. Покрокова демонстрація комбінації клавіш чи фішки карти.\n 2. Порівняння гри до та після використання секрету.\n 3. Як обіграти сильного суперника на розслабоні.\n• **CTA:** «Напиши свій поточний ранг у коментарях!»",
            "🔥 **Контент-план: Помилки Новачків**\n\n• **Заголовок:** «Як перестати зливати катки в {topic}»\n• **Хук:** «Ти все ще робиш ЦЮ помилку у {topic}?»\n• **Сценарій:**\n 1. Розбір 3 головних промахів новачка.\n 2. Ідеальні налаштування графіки та чутливості.\n• **CTA:** «Перешли це відео своєму тиммейту, який вічно зливає!»"
        ],
        'general': [
            "💡 **Контент-план: Розвінчання Міфів та Аналітика**\n\n• **Заголовок:** «Вся правда про {topic}, яку від вас приховують»\n• **Хук:** «Більшість людей помиляються щодо {topic}...»\n• **Сценарій:**\n 1. Розбір 3 найпопулярніших оман у цій ніші.\n 2. Реальні факти та цифри з особистого досвіду.\n• **CTA:** «А ви вірили в цей міф? Напишіть у коментарях!»",
            "📈 **Контент-план: Покроковий Посібник**\n\n• **Заголовок:** «Як розібратися в {topic} з нуля за 60 секунд»\n• **Хук:** «Забудь про складні інструкції. Ось як працює {topic}!»\n• **Сценарій:**\n 1. Крок 1: Базовий старт.\n 2. Крок 2: Головний секрет ефективності.\n 3. Крок 3: Чого варто уникати.\n• **CTA:** «Зберігай у закладки, щоб не втратити!»"
        ]
    },
    'pl': {
        'auto': [
            "🏎 **Plan Treści: Pełny Test i Recenzja**\n\n• **Tytuł:** «Dlaczego wszyscy kupują {topic} w 2026 roku?»\n• **Hook:** «Pomyśl dwa razy, zanim kupisz {topic}... Oto dlaczego!»\n• **Scenariusz:**\n 1. Pokaż 3 ukryte zalety wnętrza i prowadzenia.\n 2. Wymień 3 najdroższe usterki w serwisie.\n• **CTA:** «Napisz w komentarzu, czy kupiłbyś ten samochód!»"
        ],
        'gaming': [
            "🎮 **Plan Treści: Ukryte Sztuczki i Porady**\n\n• **Tytuł:** «Sekretny trik w {topic}, o którym wie tylko 1% graczy!»\n• **Hook:** «Chcesz podnieść rangę w {topic}? Zobacz to!»\n• **Scenariusz:**\n 1. Pokazanie triku krok po kroku.\n 2. Porównanie gry przed i po zastosowaniu.\n• **CTA:** «Napisz swoją rangę w komentarzu!»"
        ],
        'general': [
            "💡 **Plan Treści: Prawda i Mity**\n\n• **Tytuł:** «Cała prawda o {topic}, której nikt Ci nie mówi»\n• **Hook:** «Większość ludzi myli się co do {topic}...»\n• **Scenariusz:**\n 1. Obalenie 3 najpopularniejszych mitów.\n 2. Fakty i liczby.\n• **CTA:** «Napisz w komentarzu, co o tym myślisz!»"
        ]
    },
    'en': {
        'auto': [
            "🏎 **Content Strategy: Full Car Review & Test Drive**\n\n• **Headline:** «Why everyone is buying {topic} in 2026?»\n• **Hook:** «Think twice before buying {topic}... Here is why!»\n• **Script:**\n 1. Show 3 hidden features of interior & performance.\n 2. List top 3 expensive maintenance issues.\n• **CTA:** «Comment below: Would you buy this or an alternative?»"
        ],
        'gaming': [
            "🎮 **Content Strategy: Secret Pro Tips**\n\n• **Headline:** «Secret {topic} trick only 1% of players know!»\n• **Hook:** «Want to rank up fast in {topic}? Watch this!»\n• **Script:**\n 1. Step-by-step secret movement/keybind showcase.\n 2. Before vs After comparison.\n• **CTA:** «Drop your current rank in the comments!»"
        ],
        'general': [
            "💡 **Content Strategy: Myth Busting**\n\n• **Headline:** «The ultimate truth about {topic} nobody tells you»\n• **Hook:** «Most people are completely wrong about {topic}...»\n• **Script:**\n 1. Debunking top 3 common misconceptions.\n 2. Real proof & actionable facts.\n• **CTA:** «Save this video for later!»"
        ]
    }
}

# ---------------------------------------------------------
# 5. КЛАВІАТУРИ И КНОПКИ
# ----------------
# ---------------------------------------------------------
# 6. СТАНИ (FSM)
# ---------------------------------------------------------
class BotStates(StatesGroup):
    waiting_for_tiktok = State()
    waiting_for_idea = State()
    waiting_for_stt = State()
    waiting_for_photoshop = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_ban = State()
    waiting_for_unban = State()

# ---------------------------------------------------------
# 7. ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ ОБРОБКИ МЕДІА ТА ТЕКСТУ
# ---------------------------------------------------------
def restore_punctuation(text: str, lang: str) -> str:
    words = text.split()
    if not words:
        return ""
    words[0] = words[0].capitalize()
    
    q_words = {
        'uk': ["як", "скільки", "хто", "що", "де", "чому", "коли", "навіщо"],
        'pl': ["jak", "ile", "kto", "co", "gdzie", "dlaczego", "kiedy"],
        'en': ["how", "what", "who", "where", "why", "when", "which"]
    }.get(lang, ["як", "how", "jak"])

    c_words = {
        'uk': ["а", "але", "що", "щоб", "бо", "якщо"],
        'pl': ["a", "ale", "że", "żeby", "bo", "jeśli"],
        'en': ["and", "but", "that", "because", "if"]
    }.get(lang, ["а", "ale", "but"])

    result = []
    for i, word in enumerate(words):
        w_lower = word.lower()
        if i > 0 and w_lower in q_words:
            result.append("?")
            word = word.capitalize()
        elif i > 0 and w_lower in c_words:
            result.append(",")
        result.append(word)
        
    final_str = " ".join(result).replace(" ?", "?").replace(" ,", ",")
    if not final_str.endswith("?") and not final_str.endswith("."):
        final_str += "."
    return final_str

def generate_idea_response(topic: str, lang: str) -> str:
    topic_lower = topic.lower()
    auto_keys = ["бмв", "bmw", "авто", "машина", "audi", "mercedes", "x5", "samochód", "car", "auto"]
    game_keys = ["бравл", "brawl", "гра", "game", "dota", "pubg", "cs", "gra", "rust", "gta", "minecraft"]
    
    if any(k in topic_lower for k in auto_keys):
        cat = 'auto'
    elif any(k in topic_lower for k in game_keys):
        cat = 'gaming'
    else:
        cat = 'general'
        
    lang_templates = IDEA_TEMPLATES.get(lang, IDEA_TEMPLATES['uk'])
    cat_templates = lang_templates.get(cat, lang_templates['general'])
    tpl = random.choice(cat_templates)
    return tpl.format(topic=topic.capitalize())

async def download_tiktok_no_wm(url: str) -> Optional[bytes]:
    api_url = "https://www.tikwm.com/api/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.post(api_url, data={'url': url}) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    video_url = data["data"]["play"]
                    async with session.get(video_url) as v_resp:
                        if v_resp.status == 200:
                            return await v_resp.read()
        except Exception as e:
            logger.error(f"Error downloading TikTok video: {e}")
    return None

def process_background_removal(image_bytes: bytes) -> bytes:
    input_image = Image.open(io.BytesIO(image_bytes))
    output_image = remove(input_image)
    output_buffer = io.BytesIO()
    output_image.save(output_buffer, format="PNG")
    return output_buffer.getvalue()

# ---------------------------------------------------------
# 8. ІНІЦІАЛІЗАЦІЯ БОТА ТА МІДЛВЕЙР БЛОКУВАННЯ
# ---------------------------------------------------------
init_db()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

@router.message.outer_middleware()
@router.callback_query.outer_middleware()
async def check_ban_middleware(handler, event, data):
    user = data.get("event_from_user")
    if user and db_is_banned(user.id):
        lang = db_get_user_language(user.id)
        if isinstance(event, Message):
            await event.answer(TEXTS[lang]['banned_msg'])
        elif isinstance(event, CallbackQuery):
            await event.answer(TEXTS[lang]['banned_msg'], show_alert=True)
        return
    return await handler(event, data)

# ---------------------------------------------------------
# 9. ОБРОБНИКИ КОМАНД ТА ГОЛОВНОГО МЕНЮ
# ---------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db_add_user(user.id, user.username or "", user.first_name or "")
    lang = db_get_user_language(user.id)
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user.id))

@router.callback_query(F.data == "btn_back")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    await callback.message.edit_text(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
    await callback.answer()

@router.callback_query(F.data == "btn_lang")
async def cb_lang(callback: CallbackQuery):
    lang = db_get_user_language(callback.from_user.id)
    await callback.message.edit_text(TEXTS[lang]['prompt_lang'], reply_markup=get_lang_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: CallbackQuery):
    new_lang = callback.data.split("_")[2]
    user_id = callback.from_user.id
    db_set_user_language(user_id, new_lang)
    await callback.message.answer(TEXTS[new_lang]['lang_changed'])
    await callback.message.answer(TEXTS[new_lang]['main_title'], reply_markup=get_main_keyboard(new_lang, user_id))
    await callback.answer()

# ---------------------------------------------------------
# 10. ФУНКЦІОНАЛЬНІ ОБРОБНИКИ (FSM СТАНИ)
# ---------------------------------------------------------

# --- TikTok Downloader ---
@router.callback_query(F.data == "btn_tiktok")
async def cb_tiktok(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    await state.set_state(BotStates.waiting_for_tiktok)
    await callback.message.edit_text(TEXTS[lang]['prompt_tiktok'], reply_markup=get_back_keyboard(lang))
    await callback.answer()

@router.message(BotStates.waiting_for_tiktok, F.text)
async def process_tiktok(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    url = message.text.strip()
    
    db_log_usage(user_id, "tiktok")
    status_msg = await message.answer(TEXTS[lang]['tiktok_processing'])
    
    video_bytes = await download_tiktok_no_wm(url)
    if video_bytes:
