import io
import asyncio
import logging
from PIL import Image
from rembg import remove

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db_get_user_language, db_log_usage
from locales import TEXTS
from keyboards import get_main_keyboard, get_back_keyboard

router = Router()
logger = logging.getLogger("ToolBoxAI")

class PhotoshopStates(StatesGroup):
    waiting_for_photoshop = State()

def process_background_removal(image_bytes: bytes) -> bytes:
    input_image = Image.open(io.BytesIO(image_bytes))
    output_image = remove(input_image)
    output_buffer = io.BytesIO()
    output_image.save(output_buffer, format="PNG")
    return output_buffer.getvalue()

@router.callback_query(F.data == "btn_photoshop")
async def cb_photoshop(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    await state.set_state(PhotoshopStates.waiting_for_photoshop)
    await callback.message.edit_text(TEXTS[lang]['prompt_photoshop'], reply_markup=get_back_keyboard(lang))
    await callback.answer()

@router.message(PhotoshopStates.waiting_for_photoshop, F.photo | F.document)
async def process_photoshop(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    
    db_log_usage(user_id, "photoshop")
    status_msg = await message.answer(TEXTS[lang]['ps_processing'])
    
    try:
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            file_id = message.document.file_id
            
        if not file_id:
            await status_msg.edit_text(TEXTS[lang]['ps_error'])
            await state.clear()
            await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
            return

        file_info = await bot.get_file(file_id)
        photo_bytes_io = await bot.download_file(file_info.file_path)
        input_bytes = photo_bytes_io.read()
        
        loop = asyncio.get_running_loop()
        output_bytes = await loop.run_in_executor(None, process_background_removal, input_bytes)
        
        output_file = BufferedInputFile(output_bytes, filename="no_background.png")
        await message.answer_document(document=output_file, caption=TEXTS[lang]['ps_success'])
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Photoshop Error: {e}")
        await status_msg.edit_text(TEXTS[lang]['ps_error'])
        
    await state.clear()
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
