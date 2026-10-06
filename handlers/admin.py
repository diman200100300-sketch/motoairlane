import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import CREATOR_ID
from database import (
    db_get_user_language, db_get_stats, db_get_all_user_ids, 
    db_set_ban_status
)
from locales import TEXTS
from keyboards import get_main_keyboard, get_admin_keyboard, get_back_keyboard

router = Router()
logger = logging.getLogger("ToolBoxAI")

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_ban = State()
    waiting_for_unban = State()

@router.callback_query(F.data.in_({"btn_owner", "btn_admin"}))
async def cb_admin_panel(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    
    if user_id != CREATOR_ID:
        await callback.answer(TEXTS[lang]['access_denied'], show_alert=True)
        return
        
    menu_text = TEXTS[lang]['owner_menu'] if callback.data == "btn_owner" else TEXTS[lang]['admin_menu']
    await callback.message.edit_text(menu_text, reply_markup=get_admin_keyboard(lang))
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    
    if user_id != CREATOR_ID:
        await callback.answer(TEXTS[lang]['access_denied'], show_alert=True)
        return
        
    stats = db_get_stats()
    feat_text = "\n".join([f"• {feat}: {count}" for feat, count in stats['feature_stats'].items()])
    
    stats_msg = (
        f"📊 **Статистика ToolBox AI:**\n\n"
        f"👥 Всього користувачів: `{stats['total_users']}`\n"
        f"🚫 Заблокованих: `{stats['banned_users']}`\n"
        f"⚡ Загалом використань: `{stats['total_usage']}`\n\n"
        f"**Деталізація за інструментами:**\n{feat_text if feat_text else '• Немає даних'}"
    )
    
    await callback.message.edit_text(stats_msg, reply_markup=get_admin_keyboard(lang))
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    
    if user_id != CREATOR_ID:
        await callback.answer(TEXTS[lang]['access_denied'], show_alert=True)
        return
        
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.edit_text(TEXTS[lang]['prompt_broadcast'], reply_markup=get_back_keyboard(lang))
    await callback.answer()

@router.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    
    users = db_get_all_user_ids()
    await message.answer(TEXTS[lang]['broadcast_start'])
    
    success = 0
    failed = 0
    
    for u_id in users:
        try:
            await message.copy_to(chat_id=u_id)
            success += 1
            await asyncio.sleep(0.05)
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception as e:
            logger.error(f"Broadcast error for {u_id}: {e}")
            failed += 1
            
    done_msg = TEXTS[lang]['broadcast_done'].format(success=success, failed=failed)
    await message.answer(done_msg)
    await state.clear()
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))

@router.callback_query(F.data == "admin_ban")
async def cb_admin_ban(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    if user_id != CREATOR_ID:
        return
    await state.set_state(AdminStates.waiting_for_ban)
    await callback.message.edit_text(TEXTS[lang]['prompt_ban'], reply_markup=get_back_keyboard(lang))

@router.message(AdminStates.waiting_for_ban, F.text)
async def process_ban(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    try:
        target_id = int(message.text.strip())
        db_set_ban_status(target_id, 1)
        await message.answer(TEXTS[lang]['user_banned'].format(id=target_id))
    except ValueError:
        await message.answer(TEXTS[lang]['invalid_id'])
    await state.clear()
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))

@router.callback_query(F.data == "admin_unban")
async def cb_admin_unban(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    if user_id != CREATOR_ID:
        return
    await state.set_state(AdminStates.waiting_for_unban)
    await callback.message.edit_text(TEXTS[lang]['prompt_unban'], reply_markup=get_back_keyboard(lang))

@router.message(AdminStates.waiting_for_unban, F.text)
async def process_unban(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    try:
        target_id = int(message.text.strip())
        db_set_ban_status(target_id, 0)
        await message.answer(TEXTS[lang]['user_unbanned'].format(id=target_id))
    except ValueError:
        await message.answer(TEXTS[lang]['invalid_id'])
    await state.clear()
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
