import asyncio
import logging
import json
import os
import datetime
import threading
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
import yt_dlp
import aiohttp
import speech_recognition as sr
from pydub import AudioSegment
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    FSInputFile
)

# --- МІНІ-ВЕБСЕРВЕР ДЛЯ RENDER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()
# -----------------------------------

# ТОКЕН ТА АДМІН
TOKEN = "8949626852:AAEryOoDCCPAbtNw842LybKcSlK-eXg37HY"  
ADMIN_ID = 738520454

bot = Bot(token=TOKEN)
dp = Dispatcher()

PRO_FILE = "pro_users.json"
LIMITS_FILE = "user_limits.json"
ai_waiting_users = set()

def load_json_file(filename, default_val):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except:
            return default_val
    return default_val

def save_json_file(filename, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Помилка збереження {filename}: {e}")

pro_users = load_json_file(PRO_FILE, [])

# --- СИСТЕМА ЩОДЕННИХ ЛІМІТІВ ---
def get_today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def check_and_update_limit(user_id: int, action_type: str, max_limit: int) -> bool:
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    if is_pro:
        return True

    data = load_json_file(LIMITS_FILE, {})
    today = get_today_str()
    str_uid = str(user_id)

    if str_uid not in data or data[str_uid].get("date") != today:
        data[str_uid] = {
            "date": today,
            "ai": 0,
            "video": 0,
            "voice": 0
        }

    current_count = data[str_uid].get(action_type, 0)
    if current_count >= max_limit:
        return False

    data[str_uid][action_type] = current_count + 1
    save_json_file(LIMITS_FILE, data)
    return True

def save_pro_users(users):
    save_json_file(PRO_FILE, users)

BLIK_NUMBER = "+48 733 985 396"
PRICE = "19 zł/місяць"

def get_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Генератор ідей")],
            [KeyboardButton(text="⭐ Мій профіль")],
            [KeyboardButton(text="💎 Купити PRO — 19 zł/міс")]
        ],
        resize_keyboard=True
    )

def get_inline_menu(is_pro: bool):
    keyboard = [
        [InlineKeyboardButton(text="🎥 Завантажити відео (TikTok)", callback_data="menu_video")],
        [InlineKeyboardButton(text="🎙 Аудіо інструменти (В текст)", callback_data="menu_audio")],
        [InlineKeyboardButton(text="🤖 ШІ Генератор ідей", callback_data="menu_ai")],
    ]
    if not is_pro:
        keyboard.append([InlineKeyboardButton(text="⭐ Купити PRO (19 zł)", callback_data="buy_pro")])
    else:
        keyboard.append([InlineKeyboardButton(text="✅ PRO Активно", callback_data="pro_info")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_main_menu(message: types.Message, text_prefix=""):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status_text = "⭐ Статус: **PRO (Безліміт)**" if is_pro else "⭐ Статус: **Безкоштовний**"
    
    text = f"{text_prefix}\n\n{status_text}\n\nОберіть розділ нижче:" if text_prefix else f"{status_text}\n\nОберіть розділ нижче:"
    await message.answer(text, reply_markup=get_reply_menu(), parse_mode="Markdown")
    await message.answer("Меню керування:", reply_markup=get_inline_menu(is_pro))

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    ai_waiting_users.discard(message.from_user.id)
    await send_main_menu(message, "Привіт! Я твій надійний помічник для завантаження відео (з обходом обмежень), транскрипції голосу та креативного ШІ.")

@dp.message(F.text == "💡 Генератор ідей")
async def btn_ai(message: types.Message):
    await show_ai(message)

@dp.message(F.text == "⭐ Мій профіль")
async def btn_prof(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    status = "PRO (Безліміт)" if is_pro else "Безкоштовний"
    
    data = load_json_file(LIMITS_FILE, {})
    u_limits = data.get(str(user_id), {}) if not is_pro else {}
    
    ai_used = u_limits.get("ai", 0) if not is_pro else 0
    vid_used = u_limits.get("video", 0) if not is_pro else 0
    voice_used = u_limits.get("voice", 0) if not is_pro else 0
    
    limits_info = ""
    if not is_pro:
        limits_info = (
            f"\n📊 **Ліміти на сьогодні:**\n"
            f"• Генератор ідей: Використано {ai_used}/6\n"
            f"• Завантаження відео: Використано {vid_used}/7\n"
            f"• Голосові в текст: Використано {voice_used}/4\n"
        )

    await message.answer(f"👤 Ваш ID: `{user_id}`\nСтатус: **{status}**{limits_info}", parse_mode="Markdown")
    await send_main_menu(message)

@dp.message(F.text.startswith("💎 Купити PRO"))
async def btn_buy_text(message: types.Message):
    await send_buy(message)

async def send_buy(target):
    text = f"💎 **Отримання PRO**\nЦіна: **{PRICE}**\nОплата через **BLIK** на номер:\n`{BLIK_NUMBER}`\n\nПісля переказу натисніть кнопку нижче:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Я сплатив", callback_data="paid_confirm")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
    ])
    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "buy_pro")
async def cb_buy(callback: types.CallbackQuery):
    await send_buy(callback)

@dp.callback_query(F.data == "paid_confirm")
async def cb_paid(callback: types.CallbackQuery):
    user = callback.from_user
    user_link = f"@{user.username}" if user.username else f"ID: {user.id}"
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🔔 Заявка на PRO!\nКористувач: {user_link} (`{user.id}`)\nАктивуйте командою:\n`/givepro {user.id}`", parse_mode="Markdown")
        except:
            pass
    await callback.answer("Заявку надіслано адміністратору!", show_alert=True)

@dp.callback_query(F.data == "back_home")
async def cb_home(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    ai_waiting_users.discard(user_id)
    await callback.message.edit_text("Головне меню:", reply_markup=get_inline_menu(is_pro))
    await callback.answer()

@dp.callback_query(F.data == "pro_info")
async def cb_pro_info(callback: types.CallbackQuery):
    await callback.answer("У вас вже активовано PRO-статус!", show_alert=True)

@dp.message(Command("givepro"))
async def cmd_give(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Приклад: `/givepro ID`", parse_mode="Markdown")
        return
    try:
        tid = int(args[1])
        if tid not in pro_users:
            pro_users.append(tid)
            save_pro_users(pro_users)
        await message.answer(f"✅ Користувачу `{tid}` успішно активовано та збережено PRO!")
        await bot.send_message(tid, "🎉 Вашу оплату підтверджено! PRO активовано.")
    except:
        await message.answer("Помилка в ID.")

@dp.callback_query(F.data == "menu_video")
async def cb_vid(callback: types.CallbackQuery):
    text = "🎥 **Завантаження відео**\n\nНадішліть посилання на відео з **TikTok** (робочі короткі та повні посилання, з обходом обмежень), і я завантажу його без водяного знака!\n\n📌 *Безкоштовно:* до 7 разів на день."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- СТАБІЛЬНЕ ОТРИМАННЯ ПРЯМОГО ПОСИЛАННЯ ---
async def get_tiktok_direct_url(video_url: str) -> str:
    def extract_ytdlp():
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 25,
            'extractor_args': {'tiktok': {'webpage_download': True}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url')
            except Exception as e:
                logging.error(f"Помилка yt-dlp: {e}")
                return None

    loop = asyncio.get_running_loop()
    direct_url = await loop.run_in_executor(None, extract_ytdlp)
    
    if direct_url:
        return direct_url

    api_url = f"https://www.tikwm.com/api/?url={video_url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=12) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        return data["data"]["play"]
    except Exception as e:
        logging.error(f"Помилка резервного API: {e}")

    return None

@dp.message(F.text.startswith("http"))
async def down_media(message: types.Message):
    user_id = message.from_user.id
    
    if not check_and_update_limit(user_id, "video", 7):
        await message.answer("❌ Ви вичерпали безкоштовний ліміт завантаження відео на сьогодні (7/7).\nОформіть PRO, щоб зняти всі ліміти!")
        await send_main_menu(message)
        return

    raw_url = message.text.strip()
    status = await message.answer("⏳ Завантажую відео, будь ласка, зачекайте... Це може зайняти кілька секунд.")
    
    video_url = raw_url
    if "vm.tiktok.com" in raw_url or "vt.tiktok.com" in raw_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(raw_url, allow_redirects=True, timeout=12) as resp:
                    video_url = str(resp.url)
        except Exception as e:
            logging.error(f"Помилка розгортання короткого посилання: {e}")

    video_link = await get_tiktok_direct_url(video_url)
    
    if not video_link:
        await status.edit_text("❌ Не вдалося отримати відео (можливо, воно видалене, приватне або накладено жорстке блокування). Спробуйте інше посилання.")
        await send_main_menu(message)
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_link, timeout=30) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get("Content-Type", "")
                    if "text/html" in content_type:
                        await status.edit_text("❌ Помилка: Сервер повернув сторінку замість відео файлу.")
                        await send_main_menu(message)
                        return

                    video_bytes = await resp.read()
                    
                    if len(video_bytes) > 50 * 1024 * 1024:
                        await status.edit_text("❌ Відео занадто велике для відправки через бота (понад 50 МБ).")
                        await send_main_menu(message)
                        return

                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
                        temp_video.write(video_bytes)
                        temp_path = temp_video.name
                    
                    video_file = FSInputFile(temp_path)
                    await message.answer_video(video_file, caption="✅ Ось ваше відео без водяного знака!")
                    
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                else:
                    await status.edit_text("❌ Помилка при завантаженні файлу з сервера.")
                    
        await status.delete()
        await send_main_menu(message, "Готово! Що робимо далі?")
    except Exception as e:
        logging.error(f"Помилка надсилання відео: {e}")
        try:
            await status.edit_text(f"❌ Сталася помилка при надсиланні відео.")
        except:
            pass
        await send_main_menu(message)

@dp.callback_query(F.data == "menu_audio")
async def cb_aud(callback: types.CallbackQuery):
    text = (
        "🎙 **Аудіо інструменти (Перетворення в текст)**\n\n"
        "Надішліть голосове повідомлення або аудіофайл, і я переведу його у текст!\n\n"
        "⏱ **Ліміти тривалості:**\n"
        "• Безкоштовний: до **2 хвилин** (до 4 разів на день)\n"
        "• PRO: до **15 хвилин** (безлімітно щодня)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.voice | F.audio)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    max_duration = 900 if is_pro else 120 
    duration = message.voice.duration if message.voice else (message.audio.duration or 0)
    
    if duration > max_duration:
        limit_text = "15 хвилин" if is_pro else "2 хвилини"
        await message.answer(f"❌ Файл занадто довгий! Максимальна тривалість для вашого статусу — {limit_text}.")
        await send_main_menu(message)
        return

    if not check_and_update_limit(user_id, "voice", 4):
        await message.answer("❌ Ви вичерпали безкоштовний ліміт транскрипції голосу на сьогодні (4/4).\nПридбайте PRO для безлімітного перетворення!")
        await send_main_menu(message)
        return

    status_msg = await message.answer("⏳ Розпізнаю аудіо та перетворюю на текст...")

    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file_info = await bot.get_file(file_id)
    
    import tempfile
    ogg_path = tempfile.mktemp(suffix=".ogg")
    wav_path = tempfile.mktemp(suffix=".wav")

    try:
        await bot.download_file(file_info.file_path, ogg_path)

        def convert_and_recognize():
            sound = AudioSegment.from_file(ogg_path)
            sound.export(wav_path, format="wav")
            
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                text = r.recognize_google(audio_data, language="uk-UA")
                return text

        loop = asyncio.get_running_loop()
        recognized_text = await loop.run_in_executor(None, convert_and_recognize)

        await status_msg.edit_text(f"📝 **Розпізнаний текст:**\n\n_{recognized_text}_", parse_mode="Markdown")
        await send_main_menu(message, "Готово!")

    except sr.UnknownValueError:
        await status_msg.edit_text("❌ Не вдалося розпізнати мову (тихо або немає чітких слів).")
        await send_main_menu(message)
    except Exception as e:
        logging.error(f"Помилка розпізнавання голосу: {e}")
        await status_msg.edit_text("❌ Сталася помилка при обробці аудіофайлу.")
        await send_main_menu(message)
    finally:
        for p in [ogg_path, wav_path]:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass

@dp.callback_query(F.data == "menu_ai")
async def cb_ai_menu(callback: types.CallbackQuery):
    await show_ai(callback)

async def show_ai(target):
    user_id = target.from_user.id
    is_pro = (user_id == ADMIN_ID) or (user_id in pro_users)
    
    if not is_pro:
        data = load_json_file(LIMITS_FILE, {})
        u_limits = data.get(str(user_id), {})
        ai_used = u_limits.get("ai", 0)
        
        if ai_used >= 6:
            text = "⭐ **Ви вичерпали 6 безкоштовних генерацій ідей на сьогодні.**\n\nПридбайте PRO-підписку, щоб отримати безлімітний доступ!"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Купити PRO (19 zł)", callback_data="buy_pro")],
                [InlineKeyboardButton(text="« Назад", callback_data="back_home")]
            ])
            if isinstance(target, types.CallbackQuery):
                await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
                await target.answer()
            else:
                await target.answer(text, reply_markup=kb, parse_mode="Markdown")
            return

    ai_waiting_users.add(user_id)
    text = f"💡 **Креативний ШІ Генератор ідей**\n\nНапишіть **будь-яку тему чи слово**, і я згенерую глибокі й масштабні концепції для відео!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="back_home")]])
    
    if isinstance(target, types.CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except:
            await target.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="Markdown")

# --- УНІКАЛЬНИЙ КРЕАТИВНИЙ ГЕНЕРАТОР ІДЕЙ ---
@dp.message(F.text)
async def handle_text_messages(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id in ai_waiting_users:
        if not check_and_update_limit(user_id, "ai", 6):
            ai_waiting_users.discard(user_id)
            await message.answer("❌ Ви вичерпали безкоштовний ліміт генерації ідей на сьогодні (6/6).")
            await send_main_menu(message)
            return
            
        wait_msg = await message.answer(f"🧠 Генерую повністю унікальні та різні концепції для «{text}»...")
        await asyncio.sleep(1.5)
        
        # Виправлені варіанти хуків без синтаксичних помилок
        hooks_1 = [
            f"«Я перевірив це на власному досвіді, і ось до чого це призвело з {text}...»",
            f"«Ніхто в інтернеті не говорить про цю сувору правду щодо {text}.»",
            f"«Що буде, якщо взяти {text} і довести все до повного абсурду?»",
            f"«Цю фатальну помилку з {text} роблять абсолютно всі новачки.»"
        ]
        hooks_2 = [
            f"«Побудова кадру починається з того, про що мовчать експерти про {text}.»",
            f"«Зазирнемо за лаштунки: як насправді працює {text} у реальному житті.»",
            f"«Дивіться уважно на ці деталі, бо повторити це з {text} буде складно.»"
        ]
        hooks_3 = [
            f"«Розбиваємо головний міф про {text}, у який чомусь досі вірять.»",
            f"«Чому досвідчені люди ніколи б не зробили так із {text}?»",
            f"«Експеримент на межі: чи витримає {text} такий тиск?»"
        ]

        h1 = random.choice(hooks_1)
        h2 = random.choice(hooks_2)
        h3 = random.choice(hooks_3)

        response_text = (
            f"🔥 **Унікальні креативні концепції**\n"
            f"🎯 **Тема:** _{text}_\n\n"
            f"1️⃣ **Формат «Жорсткий розбір / Експеримент»**\n"
            f"   • *Головна фішка:* Повна перевірка міфів на практиці без цензури.\n"
            f"   • *Хук на 0-3 сек:* {h1}\n"
            f"   • *Розв'язка:* Несподіваний висновок наприкінці, який змусить переглянути відео повторно.\n\n"
            f"2️⃣ **Формат «Динамічний POV / Естетика деталізації»**\n"
            f"   • *Головна фішка:* Фокус на атмосфері, унікальних ракурсах і звуках навколо.\n"
            f"   • *Хук на 0-3 сек:* {h2}\n"
            f"   • *Розв'язка:* Різкий обрив кадру під кульмінаційний біт або тиша з однією сильною фразою.\n\n"
            f"3️⃣ **Формат «Провокація / Контрастне порівняння»**\n"
            f"   • *Головна фішка:* Зіткнення двох протилежних поглядів чи очікувань.\n"
            f"   • *Хук на 0-3 сек:* {h3}\n"
            f"   • *Розв'язка:* Інтригуюче запитання до глядачів у коментарях для активації охоплень.\n\n"
            f"🏷 **Трендові хештеги:** `#тренди #{text.replace(' ', '')} #viral #foryou #tiktok`"
        )
        
        try:
            await wait_msg.edit_text(response_text, parse_mode="Markdown")
        except:
            await message.answer(response_text, parse_mode="Markdown")

        ai_waiting_users.discard(user_id)
        await send_main_menu(message, "Бажаєте згенерувати ще ідеї чи завантажити відео?")
        return

    await message.answer("Скористайтеся меню нижче або натисніть /start для вибору розділу.")
    await send_main_menu(message)

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот запущено успішно!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
