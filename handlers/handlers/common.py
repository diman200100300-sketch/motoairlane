from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from database import db_add_user, db_get_user_language, db_set_user_language
from locales import TEXTS
from keyboards import get_main_keyboard, get_lang_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db_add_user(user.id, user.username or "", user.first_name or "")
    lang = db_get_user_language(user.id)
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user.id))

@router.callback_query(F.data == "btn_back")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    await callback.message.edit_text(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
    await callback.answer()

@router.callback_query(F.data == "btn_lang")
async def cb_lang(callback: CallbackQuery):
    lang = db_get_user_language(callback.from_user.id)
    await callback.message.edit_text(TEXTS[lang]['prompt_lang'], reply_markup=get_lang_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: CallbackQuery):
    new_lang = callback.data.split("_")[2]
    user_id = callback.from_user.id
    db_set_user_language(user_id, new_lang)
    await callback.message.answer(TEXTS[new_lang]['lang_changed'])
    await callback.message.answer(TEXTS[new_lang]['main_title'], reply_markup=get_main_keyboard(new_lang, user_id))
    await callback.answer()
