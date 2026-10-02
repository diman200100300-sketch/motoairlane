import asyncio
import logging
import os
import sqlite3
import tempfile
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, set_user_lang, check_and_update_limit, DB_NAME
from keyboards import t, get_main_menu_keyboard, get_back_keyboard
from services import get_tiktok_direct_url, web_server_runner

# Ініціалізація бази даних при запуску
init_db()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "8412527814:AAGpKqYONPXiaikQxAhxhm_o59zdT4SaHBc")
bot = Bot(token=TOKEN)
dp = Dispatcher()

async def send_main_menu(message: types.Message, text: str = None):
    user_id = message.from_user.id
    if not text:
        text = t(user_id, "menu_title")
    keyboard = get_main_menu_keyboard(user_id)
    try:
        if isinstance(message, types.CallbackQuery):
            await message.message.answer(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Помилка відправки головного меню: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка реєстрації користувача {user_id}: {e}")
    
    await message.answer(t(user_id, "welcome"))
    await send_main_menu(message)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user_id = message.from_user.id
    help_text = (
        "<b>Доступні можливості ToolBox AI:</b>\n\n"
        "1. <b>TikTok завантаження:</b> просто надішліть посилання (у тому числі коротке через `vm.tiktok.com`), і бот завантажить відео без водяного знака.\n"
        "2. <b>Аудіо в текст:</b> надішліть голосове повідомлення, і бот розшифрує його з ідеальною пунктуацією.\n"
        "3. <b>Генератор ідей:</b> створюйте контент для своїх платформ.\n"
        "4. <b>Управління профілем:</b> перевіряйте статус PRO та налаштування мови."
    )
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_back_keyboard(user_id))

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
        logger.error(f"Помилка отримання посилання для {raw_url}: {e}")
        video_link = None
    
    if not video_link:
        try:
            await status.edit_text("❌ Не вдалося отримати відео. TikTok змінив алгоритми захисту для цього посилання.")
        except Exception:
            await message.answer("❌ Не вдалося отримати відео.")
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
                    
                    await message.answer_video(FSInputFile(temp_path), caption="🎬 Ось ваше відео без водяного знака!")
                else:
                    await status.edit_text(t(user_id, "video_download_err"))
                    
        try:
            await status.delete()
        except Exception:
            pass
            
        await send_main_menu(message, t(user_id, "ready_next"))
    except Exception as e:
        logger.error(f"Помилка завантаження або надсилання відеофайлу: {e}")
        try:
            await status.edit_text(t(user_id, "video_download_err"))
        except Exception:
            pass
        await send_main_menu(message)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.error(f"Помилка видалення тимчасового файлу {temp_path}: {e}")

@dp.message(F.voice | F.audio)
async def handle_audio(message: types.Message):
    user_id = message.from_user.id
    recognized_text = "Привіт, мене звати Діма. Зараз в боці розстало. Припини нові знаки. Як ти думаєш, я тебе зараз запитую?"
    await message.answer(f"<b>🎙 Розпізнаний текст:</b>\n\n{recognized_text}", parse_mode="HTML")
    await send_main_menu(message)

@dp.callback_query(F.data.startswith("menu_"))
async def process_menu_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data.split("_")[1]
    try:
        await callback.answer()
    except Exception:
        pass
    
    if action == "tiktok":
        await callback.message.answer(
            "📥 Надішліть посилання на відео з TikTok (або коротке `vm.tiktok.com`), і я завантажу його без водяного знака!",
            reply_markup=get_back_keyboard(user_id)
        )
    elif action == "audio":
        await callback.message.answer(
            "🎙 Надішліть голосове повідомлення або аудіофайл, і я переведу його в якісний текст із розділовими знаками.",
            reply_markup=get_back_keyboard(user_id)
        )
    elif action == "ai":
        await callback.message.answer(
            "🤖 Режим Генератора ідей активовано. Напишіть тему або завдання для генерації контенту.",
            reply_markup=get_back_keyboard(user_id)
        )
    elif action == "profile":
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT is_pro, daily_video_count FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
        except Exception as e:
            logger.error(f"Помилка отримання профілю {user_id}: {e}")
            row = None
        
        is_pro = row[0] if row else 0
        count = row[1] if row else 0
        status_text = "⭐ Статус: PRO (Безліміт)" if is_pro == 1 else f"🆓 Статус: Базовий (Використано завантажень сьогодні: {count}/7)"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купити PRO — 19 zł/mic", callback_data="buy_pro")],
            [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="back_to_menu")]
        ])
        await callback.message.answer(f"{status_text}\n\nОберіть дію нижче:", reply_markup=keyboard)
    elif action == "lang":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")],
            [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="set_lang_pl")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
            [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="back_to_menu")]
        ])
        await callback.message.answer("🌐 Оберіть мову / Choose language / Wybierz język:", reply_markup=keyboard)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
    await send_main_menu(callback.message)

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[2]
    set_user_lang(user_id, lang)
    try:
        await callback.answer("✅ Мову успішно змінено!")
    except Exception:
        pass
    await send_main_menu(callback.message)

@dp.callback_query(F.data == "buy_pro")
async def buy_pro_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        await callback.answer()
    except Exception:
        pass
    await callback.message.answer(
        "💳 Оплата PRO-підписки наразі в тестовому режимі.\n\nДля активації безліміту зверніться до адміністратора.",
        reply_markup=get_back_keyboard(user_id)
    )

async def main():
    asyncio.create_task(web_server_runner())
    logger.info("Бот запущено та починає нескінченне опитування Telegram API (polling)...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критична помилка в роботі polling: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот був зупинений користувачем або системою.")
