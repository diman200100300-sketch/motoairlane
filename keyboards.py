from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from locales import TEXTS
from config import CREATOR_ID

def get_main_keyboard(lang: str, user_id: int) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS['uk'])
    buttons = [
        [InlineKeyboardButton(text=t['btn_tiktok'], callback_data="btn_tiktok")],
        [InlineKeyboardButton(text=t['btn_ideas'], callback_data="btn_ideas")],
        [InlineKeyboardButton(text=t['btn_stt'], callback_data="btn_stt")],
        [InlineKeyboardButton(text=t['btn_photoshop'], callback_data="btn_photoshop")],
        [InlineKeyboardButton(text=t['btn_lang'], callback_data="btn_lang")]
    ]
    
    if user_id == CREATOR_ID:
        buttons.append([
            InlineKeyboardButton(text=t['btn_owner'], callback_data="btn_owner"),
            InlineKeyboardButton(text=t['btn_admin'], callback_data="btn_admin")
        ])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS['uk'])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t['btn_back'], callback_data="btn_back")]
    ])

def get_lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="set_lang_pl")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")]
    ])

def get_admin_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS['uk'])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t['btn_stats'], callback_data="admin_stats")],
        [InlineKeyboardButton(text=t['btn_broadcast'], callback_data="admin_broadcast")],
        [InlineKeyboardButton(text=t['btn_ban_user'], callback_data="admin_ban"),
         InlineKeyboardButton(text=t['btn_unban_user'], callback_data="admin_unban")],
        [InlineKeyboardButton(text=t['btn_back'], callback_data="btn_back")]
    ])
