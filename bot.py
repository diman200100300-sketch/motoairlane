import os
import sys
import asyncio
import logging
import shutil
import time
from aiohttp import web

# Примусове виведення логів без затримок у буфері
sys.stdout.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ToolBoxAI")

# ----------------------------------------------------
# 1. Фейковий веб-сервер для Render (Запускається першим)
# ----------------------------------------------------
async def handle_ping(request):
    return web.Response(text="Bot is alive and running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render передає номер порту у змінну оточення PORT (за замовчуванням 10000)
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Веб-сервер Render успішно запущено на порту {port}")

# ----------------------------------------------------
# 2. Очищення кешу
# ----------------------------------------------------
async def periodic_cleanup():
    while True:
        try:
            temp_dirs = ["temp", "downloads", "cache"]
            for folder in temp_dirs:
                if os.path.exists(folder):
                    for filename in os.listdir(folder):
                        file_path = os.path.join(folder, filename)
                        try:
                            if os.path.isfile(file_path) or os.path.islink(file_path):
                                if time.time() - os.path.getmtime(file_path) > 1800:
                                    os.unlink(file_path)
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path)
                        except Exception as e:
                            logger.error(f"Помилка видалення кешу {file_path}: {e}")
            logger.info("🧹 Тимчасовий кеш очищено.")
        except Exception as e:
            logger.error(f"Помилка очищення кешу: {e}")
        
        await asyncio.sleep(3600)

# ----------------------------------------------------
# 3. Головна функція
# ----------------------------------------------------
async def main():
    # 1. Відразу відкриваємо порт для Render
    try:
        await start_web_server()
    except Exception as e:
        logger.error(f"Помилка запуску веб-сервера: {e}")

    # 2. Безпечно імпортуємо бібліотеки та хендлери
    try:
        from aiogram import Bot, Dispatcher, BaseMiddleware
        from aiogram.types import Message, CallbackQuery
        from aiogram.fsm.storage.memory import MemoryStorage

        from config import BOT_TOKEN
        from database import db_init
        from handlers import common, stt, ideas, tiktok, photoshop, admin

        # Ініціалізація БД
        db_init()
        logger.info("🗄 База даних готовa.")

        # Anti-Spam Middleware
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
                    
                    if current_time - last_time < self.limit:
                        if isinstance(event, Message):
                            await event.answer("⚠️ Не спамте! Зачекайте секунду.")
                        elif isinstance(event, CallbackQuery):
                            await event.answer("⚠️ Не так швидко!", show_alert=True)
                        return
                        
                    self.user_last_message[user_id] = current_time

                return await handler(event, data)

        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher(storage=MemoryStorage())

        dp.message.middleware(AntiSpamMiddleware(limit=1.0))
        dp.callback_query.middleware(AntiSpamMiddleware(limit=0.7))

        dp.include_routers(
            common.router,
            stt.router,
            ideas.router,
            tiktok.router,
            photoshop.router,
            admin.router
        )

        asyncio.create_task(periodic_cleanup())

        logger.info("🚀 Бот успішно запущений і готовий до роботи!")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    except Exception as e:
        logger.critical(f"❌ КРИТИЧНА ПОМИЛКА ПРИ ЗАПУСКУ БОТА: {e}", exc_info=True)
        # Утримуємо процес активним, щоб веб-сервер не падав і ви бачили логи
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
