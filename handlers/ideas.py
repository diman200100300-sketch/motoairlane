import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db_get_user_language, db_log_usage
from locales import TEXTS, IDEA_TEMPLATES
from keyboards import get_main_keyboard, get_back_keyboard

router = Router()

class IdeaStates(StatesGroup):
    waiting_for_idea = State()

def generate_idea_response(topic: str, lang: str) -> str:
    topic_lower = topic.lower()
    auto_keys = ["бмв", "bmw", "авто", "машина", "audi", "mercedes", "x5", "samochód", "car", "auto"]
    game_keys = ["бравл", "brawl", "гра", "game", "dota", "pubg", "cs", "gra", "rust", "gta", "minecraft"]
    
    if any(k in topic_lower for k in auto_keys):
        cat = 'auto'
    elif any(k in topic_lower for k in game_keys):
        cat = 'gaming'
    else:
        cat = 'general'
        
    lang_templates = IDEA_TEMPLATES.get(lang, IDEA_TEMPLATES['uk'])
    cat_templates = lang_templates.get(cat, lang_templates['general'])
    tpl = random.choice(cat_templates)
    return tpl.format(topic=topic.capitalize())

@router.callback_query(F.data == "btn_ideas")
async def cb_ideas(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = db_get_user_language(user_id)
    await state.set_state(IdeaStates.waiting_for_idea)
    await callback.message.edit_text(TEXTS[lang]['prompt_ideas'], reply_markup=get_back_keyboard(lang))
    await callback.answer()

@router.message(IdeaStates.waiting_for_idea, F.text)
async def process_idea(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = db_get_user_language(user_id)
    
    db_log_usage(user_id, "ideas")
    idea_result = generate_idea_response(message.text, lang)
    
    await message.answer(idea_result)
    await state.clear()
    await message.answer(TEXTS[lang]['main_title'], reply_markup=get_main_keyboard(lang, user_id))
