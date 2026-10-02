from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_user_lang

TRANSLATIONS = {
    "uk": {
        "welcome": "👋 Вітаю! Це ваш багатофункціональний ToolBox AI бот.\n\nОберіть потрібну функцію в меню нижче:",
        "video_loading": "⏳ Завантажую відео з TikTok без водяного знака, зачекайте хвилиночку...",
        "video_limit_err": "❌ Ви перевищили ліміт безкоштовних завантажень (до 7 разів на день). Оформіть PRO для безліміту!",
        "video_html_err": "❌ Помилка: сервер повернув сторінку замість файлу захисту.",
        "video_too_big": "❌ Відео занадто велике для надсилання через Telegram (ліміт 50MB).",
        "video_download_err": "❌ Не вдалося завантажити відеофайл через блокування платформи.",
        "ready_next": "Готово! Що робимо далі?",
        "menu_title": "Меню керування ToolBox AI:",
        "btn_tiktok": "🎥 Завантажити відео (TikTok)",
        "btn_audio": "🎙 Аудіо інструменти (В текст)",
        "btn_ai": "🤖 ШІ Генератор ідей",
        "btn_profile": "⭐️ Мій профіль / PRO",
        "btn_lang": "🌐 Language / Мова / Język",
        "back_btn": "« Назад"
    },
    "pl": {
        "welcome": "👋 Witaj! To jest Twój wszechstronny bot ToolBox AI.\n\nWybierz odpowiednią funkcję z menu poniżej:",
        "video_loading": "⏳ Pobieram wideo z TikTok bez znaku wodnego, proszę czekać...",
        "video_limit_err": "❌ Przekroczono dzienny limit bezpłatnych pobrań (do 7 razy). Aktywuj PRO!",
        "video_html_err": "❌ Błąd: serwer zwrócił stronę zamiast pliku zabezpieczeń.",
        "video_too_big": "❌ Wideo jest za duże do wysłania przez Telegram (limit 50MB).",
        "video_download_err": "❌ Nie udało się pobrać pliku wideo z powodu ochrony platformy.",
        "ready_next": "Gotowe! Co robimy dalej?",
        "menu_title": "Menu sterowania ToolBox AI:",
        "btn_tiktok": "🎥 Pobierz wideo (TikTok)",
        "btn_audio": "🎙 Narzędzia audio (Na tekst)",
        "btn_ai": "🤖 Generator pomysłów AI",
        "btn_profile": "⭐️ Mój profil / PRO",
        "btn_lang": "🌐 Język / Language / Мова",
        "back_btn": "« Wstecz"
    },
    "en": {
        "welcome": "👋 Hello! This is your multifunctional ToolBox AI bot.\n\nChoose the desired function from the menu below:",
        "video_loading": "⏳ Downloading video from TikTok without watermark, please wait...",
        "video_limit_err": "❌ You have exceeded the free download limit (up to 7 times/day). Get PRO!",
        "video_html_err": "❌ Error: server returned a security web page instead of a file.",
        "video_too_big": "❌ The video is too large to send via Telegram (50MB limit).",
        "video_download_err": "❌ Failed to download the video file due to platform protection.",
        "ready_next": "Done! What's next?",
        "menu_title": "ToolBox AI Control Menu:",
        "btn_tiktok": "🎥 Download video (TikTok)",
        "btn_audio": "🎙 Audio tools (To text)",
        "btn_ai": "🤖 AI Idea Generator",
        "btn_profile": "⭐️ My profile / PRO",
        "btn_lang": "🌐 Language / Мова / Język",
        "back_btn": "« Back"
    }
}

def t(user_id: int, key: str) -> str:
    """Отримати локалізований текст за ключем та мовою користувача"""
    lang = get_user_lang(user_id)
    return TRANSLATIONS.get(lang, TRANSLATIONS["uk"]).get(key, key)

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Головне інлайн-меню бота"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "btn_tiktok"), callback_data="menu_tiktok")],
        [InlineKeyboardButton(text=t(user_id, "btn_audio"), callback_data="menu_audio")],
        [InlineKeyboardButton(text=t(user_id, "btn_ai"), callback_data="menu_ai")],
        [InlineKeyboardButton(text=t(user_id, "btn_profile"), callback_data="menu_profile")],
        [InlineKeyboardButton(text=t(user_id, "btn_lang"), callback_data="menu_lang")]
    ])

def get_back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавіатура повернення назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="back_to_menu")]
    ])
