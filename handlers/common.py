import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import (
    db_add_user, 
    db_get_user_language, 
    db_set_user_language, 
    db_is_banned,
    db_log_usage
)
from keyboards import get_main_keyboard, get_language_keyboard

router = Router()
logger = logging.getLogger("ToolBoxAI")

# Тексти для привітання та мов
START_TEXTS = {
    'ua': "👋 **Привіт! Я ToolBox AI** — твій багатофункціональний помічник.\n\n"
          "🚀 **Що я вмію:**\n"
          "🎙 **Голос у текст:** Надішли аудіо чи голосове повідомлення.\n"
          "💡 **Генератор ідей:** Отримуй свіжі ідеї для контенту чи бізнесу.\n"
          "📥 **TikTok Downloader:** Надішли посилання на відео.\n"
          "🖼 **Photoshop AI:** Видаляй фон з фото в один клік.\n\n"
          "Обери потрібну функцію в меню нижче 👇",
    'en': "👋 **Hello! I am ToolBox AI** — your multifunctional assistant.\n\n"
          "🚀 **Features:**\n"
          "🎙 **Voice to Text:** Send audio or voice message.\n"
          "💡 **Ideas Generator:** Get fresh ideas for content or business.\n"
          "📥 **TikTok Downloader:** Send a link to a video.\n"
          "🖼 **Photoshop AI:** Remove background from photos in one click.\n\n"
          "Select a feature from the menu below 👇",
    'pl': "👋 **Cześć! Jestem ToolBox AI** — Twój wielofunkcyjny asystent.\n\n"
          "🚀 **Funkcje:**\n"
          "🎙 **Głos na tekst:** Wyślij wiadomość głosową.\n"
          "💡 **Generator pomysłów:** Uzyskaj pomysły na treści lub biznes.\n"
          "📥 **TikTok Downloader:** Wyślij link do filmu.\n"
          "🖼 **Photoshop AI:** Usuń tło ze zdjęcia jednym kliknięciem.\n\n"
          "Wybierz funkcję z menu poniżej 👇"
}

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    # Реєстрація користувача в БД
    db_add_user(user_id, username, first_name)
    db_log_usage(user_id, "start")
    
    # Перевірка бану
    if db_is_banned(user_id):
        await message.answer("❌ Ваш акаунт заблоковано.")
        return

    lang = db_get_user_language(user_id) or 'ua'
    text = START_TEXTS.get(lang, START_TEXTS['ua'])
    
    await message.answer(
        text, 
        reply_markup=get_main_keyboard(lang), 
        parse_mode="Markdown"
    )

@router.message(F.text.in_(["🌐 Мова / Language", "🌐 Мова", "🌐 Language"]))
async def cmd_change_language(message: Message):
    user_id = message.from_user.id
    if db_is_banned(user_id):
        return
        
    await message.answer(
        "Оберіть мову інтерфейсу / Choose language:", 
        reply_markup=get_language_keyboard()
    )

@router.callback_query(F.data.startswith("set_lang_"))
async def process_language_change(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang_code = callback.data.split("_")[-1]
    
    db_set_user_language(user_id, lang_code)
    
    confirm_texts = {
        'ua': "✅ Мову успішно змінено!",
        'en': "✅ Language updated successfully!",
        'pl': "✅ Język został pomyślnie zmieniony!"
    }
    
    await callback.answer(confirm_texts.get(lang_code, "✅ Success"))
    
    text = START_TEXTS.get(lang_code, START_TEXTS['ua'])
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer(
        "Меню оновлено:", 
        reply_markup=get_main_keyboard(lang_code)
    )
