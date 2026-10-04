# Додаємо до імпортів для роботи з зображеннями та новими запитами
import io
from PIL import Image

# Розширення бази даних для фото-редактора та керування правами адмінів
def init_db_v19():
    try:
        conn = sqlite3.connect("bot_database_enterprise_v14.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS photo_jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                prompt TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Базу даних версії v19 (фото-редактор та ролі) успішно оновлено.")
    except Exception as e:
        logger.error(f"Помилка оновлення БД v19: {e}")

init_db_v19()

# Додаємо нові стани FSM для редактора фото та розширення адмінки
class PhotoEditStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_photo_prompt = State()

class AdminUpgradeStates(StatesGroup):
    waiting_for_target_user_for_pro = State()
    waiting_for_target_user_for_admin = State()
    waiting_for_target_user_for_main_admin = State()
# Оновлені словники для нових функцій у LANG_TEXTS
LANG_TEXTS['uk']['btn_photo_edit'] = "🎨 ШІ Редактор Фото"
LANG_TEXTS['uk']['photo_send'] = "🎨 Надішліть фотографію, яку хочете змінити (змінити фон, одяг або видалити об'єкти):"
LANG_TEXTS['uk']['photo_prompt'] = "✍️ Напишіть текстом, що саме потрібно змінити на фото (наприклад: *«Змінити фон на нічне місто»* або *«Прибрати зайвих людей на задньому плані»*):"
LANG_TEXTS['uk']['photo_processing'] = "⏳ Обробляю зображення через безкоштовні нейромережеві шлюзи..."
LANG_TEXTS['uk']['photo_error'] = "❌ Не вдалося обробити фото. Спробуйте інше зображення або простіший запит."

LANG_TEXTS['pl']['btn_photo_edit'] = "🎨 Edytor Zdjęć AI"
LANG_TEXTS['pl']['photo_send'] = "🎨 Wyślij zdjęcie, które chcesz edytować (zmiana tła, ubrań, usuwanie obiektów):"
LANG_TEXTS['pl']['photo_prompt'] = "✍️ Wpisz, co chcesz zmienić na zdjęciu:"
LANG_TEXTS['pl']['photo_processing'] = "⏳ Przetwarzam obraz przez darmowe bramki AI..."
LANG_TEXTS['pl']['photo_error'] = "❌ Nie udało się przetworzyć zdjęcia."

LANG_TEXTS['en']['btn_photo_edit'] = "🎨 AI Photo Editor"
LANG_TEXTS['en']['photo_send'] = "🎨 Send a photo you want to edit (change background, clothes, remove objects):"
LANG_TEXTS['en']['photo_prompt'] = "✍️ Describe what you want to change on the photo:"
LANG_TEXTS['en']['photo_processing'] = "⏳ Processing image through free AI gateways..."
LANG_TEXTS['en']['photo_error'] = "❌ Failed to process the photo."
def main_menu_kb_builder(user_id: int) -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    pro_active = check_pro_status(user_id)
    role = get_user_role(user_id)
    
    keyboard = [
        [InlineKeyboardButton(text=get_t(user_id, 'btn_tiktok'), callback_data="download_video")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_audio'), callback_data="audio_to_text")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_ai'), callback_data="ai_generator")],
        [InlineKeyboardButton(text=get_t(user_id, 'btn_photo_edit'), callback_data="photo_editor_start")],
    ]
    
    if pro_active:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_pro_active'), callback_data="pro_info")])
    else:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_buy_pro'), callback_data="buy_pro")])
        
    if user_id == CREATOR_ID:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_owner'), callback_data="owner_panel")])
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
    elif role in ['main_admin', 'admin']:
        keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_admin'), callback_data="admin_panel")])
        
    keyboard.append([InlineKeyboardButton(text=get_t(user_id, 'btn_lang'), callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
