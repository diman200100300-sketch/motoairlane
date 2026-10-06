import os
import asyncio
import logging
import shutil
import time
from aiohttp import web

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import db_init

# Імпорт усіх хендлерів з папки handlers
from handlers import common, stt, ideas, tiktok, photoshop, admin

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ToolBoxAI")

# ----------------------------------------------------
# 1. Anti-Spam Middleware (Захист від спаму)
# ----------------------------------------------------
class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 1.0):
        self.limit = limit
        self.user_last_message = {}

    async def __call__(self, handler, event, data):
        user_id = None
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id

        if user_id:
            current_time = time.time()
            last_time = self.user_last_message.get(user_id, 0)
            
            # Якщо з моменту останньої дії минуло менше ніж limit секунд
            if current_time - last_time < self.limit:
                if isinstance(event, Message):
                    await event.answer("⚠️ Не спамте! Зачекайте секунду перед наступною командою.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Не так швидко!", show_alert=True)
                return
                
            self.user_last_message[user_id] = current_time

        return await handler(event, data)

# ----------------------------------------------------
# 2. Автоматичне очищення тимчасового кешу
# ----------------------------------------------------
async def periodic_cleanup():
    """Фонова таска, яка щогодини чистить тимчасові файли"""
    while True:
        try:
            temp_dirs = ["temp", "downloads", "cache"]
            for folder in temp_dirs:
                if os.path.exists(folder):
                    for filename in os.listdir(folder):
                        file_path = os.path.join(folder, filename)
                        try:
                            if os.path.isfile(file_path) or os.path.islink(file_path):
                                # Видаляємо файли, старіші за 30 хвилин
                                if time.time() - os.path.getmtime(file_path) > 1800:
                                    os.unlink(file_path)
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path)
                        except Exception as e:
                            logger.error(f"Помилка видалення файлу {file_path}: {e}")
            logger.info("🧹 Тимчасовий кеш успішно очищено.")
        except Exception as e:
            logger.error(f"Помилка в системі очищення кешу: {e}")
        
        # Перевірка кожну годину (3600 сек)
        await asyncio.sleep(3600)

# ----------------------------------------------------
# 3. Фейковий веб-сервер для Render (Health Check)
# ----------------------------------------------------
async def handle_ping(request):
    return web.Response(text="Bot is alive and running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Веб-сервер для Render успішно запущено на порту {port}")

# ----------------------------------------------------
# 4. Основна функція запуску бота
# ----------------------------------------------------
async def main():
    # Ініціалізація бази даних
    try:
        db_init()
        logger.info("🗄 База даних ініціалізована.")
    except Exception as e:
        logger.warning(f"Примітка БД: {e}")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Встановлюємо Anti-Spam (1 секунда між повідомленнями, 0.7 сек для кнопок)
    dp.message.middleware(AntiSpamMiddleware(limit=1.0))
    dp.callback_query.middleware(AntiSpamMiddleware(limit=0.7))

    # Підключаємо всі роутери хендлерів
    dp.include_routers(
        common.router,
        stt.router,
        ideas.router,
        tiktok.router,
        photoshop.router,
        admin.router
    )

    # Запускаємо веб-сервер, щоб Render бачив відкритий порт
    await start_web_server()

    # Запускаємо фонове прибирання кешу
    asyncio.create_task(periodic_cleanup())

    logger.info("🚀 Бот ToolBox AI повністю готовий і запущений!")

    # Пропускаємо накопичені за час офлайну повідомлення і починаємо слухати
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
