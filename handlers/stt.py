import os
import logging
import subprocess
import speech_recognition as sr

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db_get_user_language, db_log_usage
from locales import TEXTS
from keyboards import get_main_keyboard, get_back_keyboard

router = Router()
logger = logging.getLogger("ToolBoxAI")

class STTStates(StatesGroup):
    waiting_for_stt = State()

def restore_punctuation(text: str, lang: str) -> str:
    words = text.split()
    if not words:
        return ""
    words[0] = words[0].capitalize()
    
    q_words = {
        'uk': ["як", "скільки", "хто", "що", "де", "чому", "коли", "навіщо"],
        'pl': ["jak", "ile", "kto", "co", "gdzie", "dlaczego", "kiedy"],
        'en': ["how", "what", "who", "where", "why", "when", "which"]
    }.get(lang, ["як", "how", "jak"])

    c_words = {
        'uk': ["а", "але", "що", "щоб", "бо", "якщо"],
        'pl': ["a", "ale", "że", "żeby", "bo", "jeśli"],
        'en': ["and", "but", "that", "because", "if"]
    }.get(lang, ["а", "ale", "but"])

    result = []
    for i, word in enumerate(words):
        w_lower = word.lower()
        if i > 0 and w_lower in q_words:
            result.append("?")
            word = word.capitalize()
        elif i > 0 and w_lower in c_words:
            result.append(",")
        result.append(word)
        
    final_str = " ".join(result).replace(" ?", "?").replace(" ,", ",")
    if not final_str.endswith("?") and not final_str.endswith("."):
        final_str += "."
    return final_str

@router.callback_query(F.data == "btn_stt")
async def cb_stt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    await state.set_state(STTStates.waiting_for_stt)
    await callback.message.edit_text(TEXTS[lang]['prompt_stt'], reply_markup=get_back_keyboard(lang))
    await callback.answer()

@router.message(STTStates.waiting_for_stt, F.content_type.in_({'voice', 'audio', 'video', 'document'}))
async def process_stt(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    
    db_log_usage(user_id, "stt")
    status_msg = await message.answer(TEXTS[lang]['stt_processing'])
    
    file_id = None
    if message.voice:
        file_id = message.voice.file_id
    elif message.audio:
        file_id = message.audio.file_id
    elif message.video:
        file_id = message.video.file_id
    elif message.document:
        file_id = message.document.file_id

    if not file_id:
        await status_msg.edit_text(TEXTS[lang]['stt_error'])
        await state.clear()
        await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
        return

    src_path = f"temp_input_{user_id}"
    wav_path = f"temp_output_{user_id}.wav"
    
    try:
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, src_path)
        
        subprocess.run([
            "ffmpeg", "-y", "-i", src_path,
            "-ar", "16000", "-ac", "1", wav_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            sr_lang = {'uk': 'uk-UA', 'pl': 'pl-PL', 'en': 'en-US'}.get(lang, 'uk-UA')
            raw_text = recognizer.recognize_google(audio_data, language=sr_lang)
            formatted_text = restore_punctuation(raw_text, lang)
            
            await status_msg.edit_text(f"{TEXTS[lang]['stt_result']}{formatted_text}")
    except Exception as e:
        logger.error(f"STT Error: {e}")
        await status_msg.edit_text(TEXTS[lang]['stt_error'])
    finally:
        for p in [src_path, wav_path]:
            if os.path.exists(p):
                os.remove(p)
                
    await state.clear()
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
