import os
import sqlite3
import logging
import subprocess
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from openai import OpenAI

# Автоматичне оновлення yt-dlp для стабільного завантаження відео
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
except Exception as e:
    logging.error(f"Помилка оновлення yt-dlp: {e}")

import yt_dlp

# Налаштування логування
logging.basicConfig(level=logging.INFO)

TOKEN = "ТВОЙ_TELEGRAM_BOT_TOKEN"
OPENAI_API_KEY = "ТВОЙ_OPENAI_API_KEY"
ADMIN_IDS = [123456789]  # Впиши сюди свій Telegram ID (як головного адміна)

bot = Bot(token=TOKEN)
dp = Dispatcher()
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Ініціалізація бази даних SQLite
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # Таблиця користувачів
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_pro INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            language TEXT DEFAULT 'uk'
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect("bot_database.db")

def is_user_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return bool(res and res[0] == 1)

def check_pro_status(user_id: int) -> bool:
    if is_user_admin(user_id):
        return True
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_pro FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return bool(res and res[1] == 1 if len(res)>1 else res and res[0] == 1) # Безпечна перевірка
class GenStates(StatesGroup):
    waiting_for_idea_prompt = State()
    waiting_for_video_link = State()

def main_menu_kb(is_pro: bool):
    kb = [
        [InlineKeyboardButton(text="📥 Завантажити відео (TikTok)", callback_data="download_video")],
        [InlineKeyboardButton(text="🎙️️ Аудіо інструменти (В текст)", callback_data="audio_to_text")],
        [InlineKeyboardButton(text="🤖 ШІ Генератор ідей (Глибокий аналіз)", callback_data="ai_generator")]
    ]
    if is_pro:
        kb.append([InlineKeyboardButton(text="✅ PRO Активно", callback_data="pro_active")])
    else:
        kb.append([InlineKeyboardButton(text="💎 Купити PRO — 19 zł/міс", callback_data="buy_pro")])
    
    kb.append([InlineKeyboardButton(text="🌐 Language / Мова / Język", callback_data="change_lang")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, is_pro FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute("INSERT INTO users (user_id, username, is_pro, is_admin) VALUES (?, ?, 0, 0)", (user_id, username))
        conn.commit()
    
    conn.close()
    
    pro_active = check_pro_status(user_id)
    status_text = "⭐ Статус: PRO (Безліміт)" if pro_active else "⭐ Статус: Безкоштовний"
    
    await message.answer(
        f"{status_text}\n\nОберіть розділ нижче:",
        reply_markup=main_menu_kb(pro_active)
    )

# Адмін-команда для надання прав помічника (адміна), який може роздавати PRO
@dp.message(Command("give_admin"))
async def cmd_give_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/give_admin <user_id>`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Користувачу `{target_id}` успішно надано права адміністратора (може видавати PRO).", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

# Команда для видачі PRO іншим користувачам (доступна тільки головному адміну або призначеним адмінам)
@dp.message(Command("give_pro"))
async def cmd_give_pro(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ Ця команда доступна лише адміністраторам.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Використання: `/give_pro <user_id>`", parse_mode="Markdown")
        return
    
    try:
        target_id = int(args[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await message.answer(f"💎 Статус PRO успішно активовано для користувача `{target_id}`!", parse_mode="Markdown")
        
        try:
            await bot.send_message(target_id, "🎉 Вітаємо! Ваш статус PRO успішно активовано адміністратором!")
        except:
            pass
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")
@dp.callback_query(F.data == "download_video")
async def cb_download_video(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 Надішліть посилання на TikTok, і я завантажу його за кілька секунд.")
    await state.set_state(GenStates.waiting_for_video_link)
    await callback.answer()

@dp.message(GenStates.waiting_for_video_link)
async def process_video_link(message: types.Message, state: FSMContext):
    url = message.text.strip()
    processing_msg = await message.answer("⏳ Обробка та завантаження відео...")
    
    output_filename = f"video_{message.from_user.id}.mp4"
    ydl_opts = {
        'outtmpl': output_filename,
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True
    }
    
    success = False
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        success = True
    except Exception as e:
        logging.error(f"Помилка завантаження yt-dlp: {e}")
        success = False
        
    await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
    
    if success and os.path.exists(output_filename):
        try:
            video_file = types.FSInputFile(output_filename)
            await message.answer_video(video=video_file)
        except Exception as err:
            await message.answer(f"❌ Не вдалося завантажити відео. Спробуйте інше посилання.")
            logging.error(f"Помилка відправки відео в Telegram: {err}")
        finally:
            if os.path.exists(output_filename):
                os.remove(output_filename)
    else:
        await message.answer("❌ Не вдалося завантажити відео. Спробуйте інше посилання.")
        
    await state.clear()
    pro_active = check_pro_status(message.from_user.id)
    await message.answer("Готово! Головне меню керування:", reply_markup=main_menu_kb(pro_active))

@dp.callback_query(F.data == "ai_generator")
async def cb_ai_generator(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "💡 **Глибокий ШІ Генератор ідей**\n\n"
        "Напишіть будь-яку тему, нішу чи об'єкт. ШІ проведе глибокий аналіз та видасть унікальні розгорнуті варіанти для створення контенту або відео без повторів!"
    )
    await state.set_state(GenStates.waiting_for_idea_prompt)
    await callback.answer()

@dp.message(GenStates.waiting_for_idea_prompt)
async def process_ai_idea(message: types.Message, state: FSMContext):
    prompt_text = message.text.strip()
    wait_msg = await message.answer("🧠 Проводжу глибокий аналіз та генерую унікальні варіанти контенту...")
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "Ти експерт з контент-маркетингу, сценарист та аналітик соцмереж. "
                        "Надавай глибокі, цікаві, розгорнуті та унікальні варіанти і сценарії для контенту чи відео за запитом користувача. "
                        "Уникайте банальних шаблонів. Кожна відповідь має бути детальною, практичною, містити чітку структуру (Механіка, Покроковий план, Ідеї для зйомки відео) "
                        "та давати конкретні інструкції, як це втілити у вірусний чи експертний контент."
                    )
                },
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.8,
            max_tokens=900
        )
        result_text = response.choices[0].message.content
    except Exception as e:
        result_text = f"❌ Сталася помилка при зверненні до ШІ: {e}"
        
    await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
    await message.answer(result_text, parse_mode="Markdown")
    
    await state.clear()
    pro_active = check_pro_status(message.from_user.id)
    await message.answer("Готово! Головне меню керування:", reply_markup=main_menu_kb(pro_active))
@dp.callback_query(F.data == "buy_pro")
async def cb_buy_pro(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Я сплатив", callback_data="i_paid")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "💎 **Отримання PRO**\n"
        "Ціна: 19 zł/місяць\n"
        "Оплата через BLIK на номер:\n`+48 733 985 396`",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "i_paid")
async def cb_i_paid(callback: types.CallbackQuery):
    await callback.message.answer(
        "⏳ Ваша оплата перевіряється адміністратором. Після підтвердження статус PRO буде активовано автоматично!"
    )
    # Повідомлення адміністраторам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, 
                f"🔔 Користувач @{callback.from_user.username or 'none'} (ID: `{callback.from_user.id}`) натиснув «Я сплатив».\n"
                f"Використайте команду: `/give_pro {callback.from_user.id}` для активації.",
                parse_mode="Markdown"
            )
        except:
            pass
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: types.CallbackQuery):
    pro_active = check_pro_status(callback.from_user.id)
    status_text = "⭐ Статус: PRO (Безліміт)" if pro_active else "⭐ Статус: Безкоштовний"
    await callback.message.edit_text(
        f"{status_text}\n\nОберіть розділ нижче:",
        reply_markup=main_menu_kb(pro_active)
    )
    await callback.answer()

# Запуск бота
if __name__ == "__main__":
    import asyncio
    async def main():
        await dp.start_polling(bot)
    asyncio.run(main())
