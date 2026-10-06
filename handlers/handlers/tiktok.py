import logging
from typing import Optional
import aiohttp
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db_get_user_language, db_log_usage
from locales import TEXTS
from keyboards import get_main_keyboard, get_back_keyboard

router = Router()
logger = logging.getLogger("ToolBoxAI")

class TikTokStates(StatesGroup):
    waiting_for_tiktok = State()

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

@router.callback_query(F.data == "btn_tiktok")
async def cb_tiktok(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    await state.set_state(TikTokStates.waiting_for_tiktok)
    await callback.message.edit_text(TEXTS[lang]['prompt_tiktok'], reply_markup=get_back_keyboard(lang))
    await callback.answer()

@router.message(TikTokStates.waiting_for_tiktok, F.text)
async def process_tiktok(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    url = message.text.strip()
    
    db_log_usage(user_id, "tiktok")
    status_msg = await message.answer(TEXTS[lang]['tiktok_processing'])
    
    video_bytes = await download_tiktok_no_wm(url)
    if video_bytes:
        video_file = BufferedInputFile(video_bytes, filename="tiktok_video.mp4")
        await message.answer_video(video=video_file)
        await status_msg.delete()
    else:
        await status_msg.edit_text(TEXTS[lang]['tiktok_error'])
        
    await state.clear()
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
