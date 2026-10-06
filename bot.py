import sys
import logging
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db, db_is_banned, db_get_user_language
from locales import TEXTS

from handlers import common, tiktok, ideas, stt, photoshop, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_activity.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("ToolBoxAI")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message.outer_middleware()
@dp.callback_query.outer_middleware()
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

dp.include_routers(
    common.router,
    tiktok.router,
    ideas.router,
    stt.router,
    photoshop.router,
    admin.router
)

async def main():
    logger.info("Initializing Database...")
    init_db()
    logger.info("Starting ToolBox AI Master Bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
