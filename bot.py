import os
import sys
import asyncio
import logging
import traceback
from aiohttp import web

# Примусове виведення логів без буферизації
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ToolBoxAI")

# 1. Запуск HTTP-сервера для Render
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 HTTP-сервер Render запущено на порту {port}")

# 2. Головна функція
async def main():
    await start_web_server()

    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        try:
            from config import BOT_TOKEN
            bot_token = BOT_TOKEN
        except Exception:
            pass

    if not bot_token:
        logger.critical("❌ ПОМИЛКА: Змінна BOT_TOKEN відсутня!")
        while True:
            await asyncio.sleep(3600)

    try:
        from aiogram import Bot, Dispatcher, BaseMiddleware
        from aiogram.types import Message, CallbackQuery
        from aiogram.fsm.storage.memory import MemoryStorage
        print("✅ aiogram успішно імпортовано")
    except Exception as e:
        logger.critical(f"❌ Помилка aiogram: {e}\n{traceback.format_exc()}")
        while True: await asyncio.sleep(3600)

    try:
        from database import db_init
        db_init()
        print("✅ База даних успішно ініціалізована")
    except Exception as e:
        logger.critical(f"❌ Помилка бази даних: {e}\n{traceback.format_exc()}")
        while True: await asyncio.sleep(3600)

    class AntiSpamMiddleware(BaseMiddleware):
        def __init__(self, limit: float = 1.0):
            self.limit = limit
            self.user_last_message = {}

        async def __call__(self, handler, event, data):
            import time
            user_id = event.from_user.id if isinstance(event, (Message, CallbackQuery)) else None
            if user_id:
                current_time = time.time()
                last_time = self.user_last_message.get(user_id, 0)
                if current_time - last_time < self.limit:
                    if isinstance(event, Message):
                        await event.answer("⚠️ Зачекайте секунду перед наступним повідомленням.")
                    return
                self.user_last_message[user_id] = current_time
            return await handler(event, data)

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AntiSpamMiddleware(limit=1.0))

    # Безпечне підключення хендлерів по одному
    routers_to_load = ["common", "stt", "ideas", "tiktok", "photoshop", "admin"]
    for r_name in routers_to_load:
        try:
            module = __import__(f"handlers.{r_name}", fromlist=["router"])
            dp.include_router(module.router)
            print(f"✅ Хендлер handlers.{r_name} успішно підключено")
        except Exception as e:
            logger.error(f"❌ ПОМИЛКА у файлі handlers/{r_name}.py: {e}\n{traceback.format_exc()}")

    logger.info("🚀 Бот ToolBox AI повністю готовий і запускає polling!")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"❌ Помилка під час polling: {e}\n{traceback.format_exc()}")
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Критичний виліт: {e}")
        import time
        while True:
            time.sleep(3600)
