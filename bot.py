# config.py
import os
from dotenv import load_dotenv

# Завантажуємо змінні середовища з локального файлу .env (якщо він є) 
# або з системних змінних Render
load_dotenv()

# Захист токена: беремо його виключно з прихованих системних змінних
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("ПОМИЛКА: Токен бота не знайдено! Перевір змінні середовища.")
# utils.py
import os
import yt_dlp
from openai import OpenAI

# Ініціалізація клієнта ШІ (якщо використовується OpenAI/DeepSeek API, ключ теж краще брати з env)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def download_tiktok_video(url: str, output_path: str = "video.mp4") -> str:
    """Надійне завантаження відео з TikTok без водяного знака з урахуванням захисту yt-dlp."""
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'best',
        'noplaylist': True,
        'quiet': True,
    }
    try:
        if os.path.exists(output_path):
            os.remove(output_path)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        print(f"Помилка завантаження TikTok: {e}")
        return None

def enhance_voice_text(raw_text: str) -> str:
    """Виправляє пунктуацію та розбиває розпізнаний голос на логічні абзаци."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ти редактор. Виправ пунктуацію, розстав коми, крапки та розділи текст на зручні абзаци (нові рядки), не змінюючи змісту сказаного."},
                {"role": "user", "content": raw_text}
            ]
        )
        return response.choices[0].message.content
    except Exception:
        return raw_text  # Якщо сталася помилка, повертаємо сирий текст

def generate_content_ideas(topic: str) -> str:
    """Генератор ідей з глибоким розумінням мобільних ігор (наприклад, Brawl Stars) та трендів."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "Ти топ-експерт з контенту для TikTok та YouTube Shorts. Ти досконало знаєш специфіку мобільних ігор (Brawl Stars тощо), тренди та сленг. Пиши коротко, чітко, без довгих вступів. Надавай потужні гачки (hook) для перших секунд та готові сценарії."
                },
                {"role": "user", "content": f"Зроби ідеї для відео на тему: {topic}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Помилка генерації ідей: {e}"
# bot.py
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN
from utils import download_tiktok_video, enhance_voice_text, generate_content_ideas

# Налаштування логування
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Головне інлайн-меню
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Завантажити відео (TikTok)", callback_data="menu_tiktok")],
        [InlineKeyboardButton(text="🎙️ Аудіо інструменти (В текст)", callback_data="menu_voice")],
        [InlineKeyboardButton(text="🤖 ШІ Генератор ідей", callback_data="menu_ideas")]
    ])

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обробник команди /start: виводить опис та головне меню"""
    welcome_text = (
        "👋 **Вітаю у ToolBox AI!**\n\n"
        "Цей бот створений як твій універсальний помічник:\n"
        "• 📥 Завантажує відео з TikTok без водяних знаків у високій якості.\n"
        "• 🎙️ Перетворює голос у текст із правильним форматуванням та пунктуацією.\n"
        "• 🤖 Генерує вірусні ідеї для твого контенту та ігор із чітким розумінням трендів.\n\n"
        "Обери потрібний розділ нижче:"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_tiktok")
async def tiktok_prompt(callback: CallbackQuery):
    await callback.message.answer("🔗 Надішли посилання на відео з TikTok (або коротке vm.tiktok.com):")
    await callback.answer()

# Приклад обробки посилань на TikTok у чаті
@dp.message(F.text.contains("tiktok.com"))
async def handle_tiktok_link(message: Message):
    processing_msg = await message.answer("⏳ Завантажую відео...")
    video_path = download_tiktok_video(message.text.strip())
    
    if video_path and os.path.exists(video_path):
        from aiogram.types import FSInputFile
        video_file = FSInputFile(video_path)
        await message.answer_video(video_file)
        await processing_msg.delete()
    else:
        await message.edit_text("❌ Не вдалося завантажити відео. Перевір посилання або спробуй пізніше.")

async def main():
    # Очищуємо вебхуки та запускаємо長 polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
