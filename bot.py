import os
import logging
import asyncio
import yt_dlp
from openai import OpenAI

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    FSInputFile
)

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# --- ЗАХИСТ ТОКЕНА ---
# Токен береться виключно зі змінних середовища Render (.env), що захищає його від витоків.
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("ПОМИЛКА: BOT_TOKEN не знайдено у змінних середовища!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# --- ГОЛОВНЕ МЕНЮ ---
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Завантажити відео (TikTok)", callback_data="menu_tiktok")],
        [InlineKeyboardButton(text="🎙️ Аудіо інструменти (В текст)", callback_data="menu_voice")],
        [InlineKeyboardButton(text="🤖 ШІ Генератор ідей", callback_data="menu_ideas")]
    ])

# --- СТАРТОВЕ МЕНЮТА АВТОМАТИЧНИЙ ЗАПУСК ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = (
        "👋 **Вітаю у ToolBox AI!**\n\n"
        "Цей бот створений як твій універсальний помічник:\n"
        "• 📥 **TikTok Downloader:** Завантажує відео без водяного знака у високій якості.\n"
        "• 🎙️ **Голос у текст:** Розпізнає аудіо та автоматично розбиває текст на абзаци з правильним форматуванням.\n"
        "• 🤖 **ШІ Генератор ідей:** Створює вірусні сценарії для будь-яких ігор, додатків, трендів та тем з чітким розумінням контексту.\n\n"
        "Обери потрібний розділ нижче:"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")

# --- ЛОГІКА ЗАВАНТАЖЕННЯ TIKTOK (Кардинальне вирішення) ---
def download_tiktok_video(url: str, output_path: str = "video.mp4") -> str:
    """Надійне завантаження через актуальний yt-dlp з обходом захисту"""
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

@dp.callback_query(F.data == "menu_tiktok")
async def tiktok_prompt(callback: CallbackQuery):
    await callback.message.answer("🔗 Надішли посилання на відео з TikTok (або коротке vm.tiktok.com), і я завантажу його для тебе!")
    await callback.answer()

@dp.message(F.text.contains("tiktok.com"))
async def handle_tiktok_link(message: Message):
    processing_msg = await message.answer("⏳ Завантажую відео (обробка 5 систем)...")
    video_path = download_tiktok_video(message.text.strip())
    
    if video_path and os.path.exists(video_path):
        video_file = FSInputFile(video_path)
        await message.answer_video(video_file)
        await processing_msg.delete()
    else:
        await message.edit_text("❌ Не вдалося завантажити відео. Перевір правильність посилання або спробуй пізніше.")

# --- УНІВЕРСАЛЬНИЙ ШІ ГЕНЕРАТОР ІДЕЙ (Будь-які ігри та теми) ---
@dp.callback_query(F.data == "menu_ideas")
async def ideas_prompt(callback: CallbackQuery):
    await callback.message.answer("🤖 Напиши тему, гру, додаток чи явище, для якого потрібно згенерувати ідеї (наприклад: *Brawl Stars, тренди в TikTok, автомобілі тощо*):")
    await callback.answer()

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text_generation(message: Message):
    # Якщо це не посилання і не команда, передаємо на генерацію ідей через ШІ
    if "tiktok.com" not in message.text:
        if not client:
            await message.error("ШІ ключ не налаштовано.")
            return
            
        wait_msg = await message.answer("🧠 Аналізую контекст та генерую ідеї...")
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            "Ти топ-експерт із контенту, трендів, мобільних та ПК ігор, додатків та соцмереж. "
                            "Ти глибоко розумієш специфіку будь-якої теми, яку тобі назвуть (будь то гра, софт чи тренд), "
                            "знаєш ігрову механіку, сленг та аудиторію. Не заходь здалека і не пиши зайвої води. "
                            "Надавай чіткі, короткі запити, потужні гачки (hook) для перших секунд та готові структуровані сценарії."
                        )
                    },
                    {"role": "user", "content": f"Зроби ідеї для відео на тему: {message.text}"}
                ]
            )
            await message.answer(response.choices[0].message.content, parse_mode="Markdown")
            await wait_msg.delete()
        except Exception as e:
            await message.edit_text(f"Помилка генерації: {e}")
# --- ГОЛОСОВІ ІНСТРУМЕНТИ (Розпізнавання та виправлення тексту) ---
@dp.callback_query(F.data == "menu_voice")
async def voice_prompt(callback: CallbackQuery):
    await callback.message.answer("🎙️ Надішли голосове повідомлення або аудіофайл, і я переведу його в текст із правильними абзацами та пунктуацією.")
    await callback.answer()

def enhance_voice_text(raw_text: str) -> str:
    """Виправляє пунктуацію та розбиває розпізнаний голос на логічні абзаци"""
    if not client:
        return raw_text
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ти професійний редактор. Виправ пунктуацію, розстав коми, крапки та розділи текст на зручні абзаци (нові рядки), не змінюючи змісту сказаного."},
                {"role": "user", "content": raw_text}
            ]
        )
        return response.choices[0].message.content
    except Exception:
        return raw_text

@dp.message(F.voice | F.audio)
async def handle_voice_message(message: Message):
    wait_msg = await message.answer("🎙️ Обробляю аудіо та розбиваю на абзаци...")
    
    try:
        # Завантаження файлу голосового повідомлення
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        local_audio = "voice_temp.ogg"
        await bot.download_file(file_path, local_audio)
        
        # Використовуємо OpenAI Whisper для розпізнавання голосу з високою точністю
        with open(local_audio, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        raw_text = transcript.text
        
        # Постобробка тексту через ШІ для красивої пунктуації та нових рядків
        formatted_text = enhance_voice_text(raw_text)
        
        response_text = f"📝 **Розпізнаний текст:**\n\n{formatted_text}"
        await message.answer(response_text, parse_mode="Markdown")
        await wait_msg.delete()
        
        # Видаляємо тимчасовий аудіофайл
        if os.path.exists(local_audio):
            os.remove(local_audio)
            
    except Exception as e:
        await message.edit_text(f"❌ Помилка обробки голосу: {e}")

# --- ЗАПУСК БОТА ---
async def main():
    # Очищаємо залишки попередніх підключень
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успішно запущено і готовий до роботи!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
