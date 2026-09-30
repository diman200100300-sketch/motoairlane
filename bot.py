import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# 🔑 Встав сюди токен свого бота від @BotFather
API_TOKEN = "8949626852:AAFpFd6EyoNA56aP6EnjPWOB54Kpsht_5CE"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Словник для збереження лімітів: {user_id: {"date": "2026-09-30", "count": 0}}
user_limits = {}
MAX_LIMIT = 7


# Стани для FSM
class BotStates(StatesGroup):
  waiting_for_video_link = State()
  waiting_for_audio = State()
  waiting_for_idea_topic = State()


# Головне меню з кнопками
def get_main_menu():
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="📥 Завантажити відео (TikTok/Insta)",
                  callback_data="btn_video",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎙 Голос у текст", callback_data="btn_audio"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💡 Генератор ідей", callback_data="btn_ideas"
              )
          ],
          [
              InlineKeyboardButton(
                  text="⭐ Мій профіль / Ліміти", callback_data="btn_profile"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💎 Купити PRO — 19 zł/міс", callback_data="btn_pro"
              )
          ],
      ]
  )
  return keyboard


# Функція перевірки ліміту
def check_limit(user_id: int) -> bool:
  today = str(datetime.date.today())
  if user_id not in user_limits:
    user_limits[user_id] = {"date": today, "count": 0}

  # Якщо настала нова доба — скидаємо лічильник
  if user_limits[user_id]["date"] != today:
    user_limits[user_id] = {"date": today, "count": 0}

  if user_limits[user_id]["count"] >= MAX_LIMIT:
    return False
  return True


# Витрата однієї спроби
def use_attempt(user_id: int):
  if user_id in user_limits:
    user_limits[user_id]["count"] += 1


# Старт бота
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  text = (
      "👋 Привіт! Я твій універсальний помічник-бот.\n\n"
      f"⚡️ У тебе є **{MAX_LIMIT} безплатних спроб на день** для будь-яких функцій (відео, аудіо, ідеї).\n\n"
      "Обери потрібну дію в меню нижче:"
  )
  await message.answer(text, reply_markup=get_main_menu())


# Кнопка профілю
@dp.callback_query(F.data == "btn_profile")
async def show_profile(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  today = str(datetime.date.today())

  if user_id not in user_limits or user_limits[user_id]["date"] != today:
    used = 0
  else:
    used = user_limits[user_id]["count"]

  remaining = max(0, MAX_LIMIT - used)
  text = (
      f"👤 **Твій профіль:**\n\n"
      f"📊 Використано сьогодні: {used} / {MAX_LIMIT}\n"
      f"✨ Залишилось спроб: **{remaining}**\n\n"
      "Ліміти оновляться опівночі автоматично! 🌙"
  )
  await callback.message.edit_text(text, reply_markup=get_main_menu())
  await callback.answer()


# Інформація про покупку PRO через BLIK
@dp.callback_query(F.data == "btn_pro")
async def show_pro_info(callback: types.CallbackQuery):
  text = (
      "💎 **PRO-доступ — 19 zł на місяць:**\n\n"
      "Що входить у підписку:\n"
      "• ♾ Повний безліміт на завантаження відео (TikTok / Insta)\n"
      "• ♾ Необмежена розшифровка аудіо в текст\n"
      "• ♾ Генератор ідей без обмежень\n\n"
      "🇵🇱 **Як сплатити в Польщі:**\n"
      "1. Надішли **19 zł** через **BLIK** на номер телефону: `+48 733 985 396`\n"
      "2. Надішли скріншот переказу або час платежу сюди в особисті повідомлення адміністратору.\n"
      "3. Отримай безліміт на свій акаунт за 1 хвилину! ⚡️"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="⬅️ Назад у меню", callback_data="back_to_menu"
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard)
  await callback.answer()


@dp.callback_query(F.data == "back_to_menu")
async def back_menu(callback: types.CallbackQuery):
  await callback.message.edit_text(
      "Головне меню:", reply_markup=get_main_menu()
  )
  await callback.answer()


# 1. Завантаження відео
@dp.callback_query(F.data == "btn_video")
async def action_video(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  if not check_limit(user_id):
    await callback.answer(
        "❌ Твої безплатні спроби на сьогодні вичерпано! Оформи PRO.",
        show_alert=True,
    )
    return

  await state.set_state(BotStates.waiting_for_video_link)
  await callback.message.edit_text(
      "🔗 Надішли мені посилання на відео з TikTok або Instagram:"
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_video_link)
async def process_video_link(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  if not check_limit(user_id):
    await message.answer(
        "❌ Ліміт вичерпано! Спробуй завтра або придбай PRO-доступ."
    )
    await state.clear()
    return

  link = message.text
  use_attempt(user_id)

  await message.answer(
      f"📥 Завантажую відео за посиланням:\n`{link}`\n\n*(тут з'явиться завантажений файл)*",
      reply_markup=get_main_menu(),
  )
  await state.clear()


# 2. Голос у текст
@dp.callback_query(F.data == "btn_audio")
async def action_audio(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  if not check_limit(user_id):
    await callback.answer(
        "❌ Твої безплатні спроби на сьогодні вичерпано! Оформи PRO.",
        show_alert=True,
    )
    return

  await state.set_state(BotStates.waiting_for_audio)
  await callback.message.edit_text(
      "🎙 Надішли мені голосове повідомлення або аудіофайл, і я переведу його в текст:"
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_audio, F.voice | F.audio)
async def process_audio_file(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  if not check_limit(user_id):
    await message.answer("❌ Ліміт вичерпано на сьогодні!")
    await state.clear()
    return

  use_attempt(user_id)

  await message.answer(
      "🎧 Аудіо отримано. Розшифровую...\n\n*(тут з'явиться текст)*",
      reply_markup=get_main_menu(),
  )
  await state.clear()


@dp.message(BotStates.waiting_for_audio)
async def process_audio_wrong_type(message: types.Message):
  await message.answer(
      "⚠️ Будь ласка, надішли саме **голосове повідомлення** або аудіофайл!"
  )


# 3. Генератор ідей
@dp.callback_query(F.data == "btn_ideas")
async def action_ideas(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  if not check_limit(user_id):
    await callback.answer(
        "❌ Твої безплатні спроби на сьогодні вичерпано! Оформи PRO.",
        show_alert=True,
    )
    return

  await state.set_state(BotStates.waiting_for_idea_topic)
  await callback.message.edit_text(
      "💡 Напиши тематику (наприклад: *поїзди, машини, лайфхаки*), і я згенерую ідеї для контенту:"
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_idea_topic)
async def process_idea_topic(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  if not check_limit(user_id):
    await message.answer("❌ Ліміт вичерпано на сьогодні!")
    await state.clear()
    return

  topic = message.text
  use_attempt(user_id)

  ideas_text = (
      f"🔥 **Ось ідеї на тему «{topic}»:**\n\n"
      "1. Зроби динамічне відео з акцентом на деталі, які зазвичай ніхто не помічає.\n"
      "2. Порівняй два популярні міфи та доведи чому це не так.\n"
      "3. Формат короткого челенджу під популярний трек."
  )

  await message.answer(
      ideas_text, reply_markup=get_main_menu(), parse_mode="Markdown"
  )
  await state.clear()


# Запуск бота
if __name__ == "__main__":
  import asyncio

  print("Бот запущено...")
  asyncio.run(dp.start_polling(bot))
