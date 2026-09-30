import asyncio
import os
import logging
from html import escape
from bs4 import BeautifulSoup
import aiohttp
import aiosqlite

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logging.basicConfig(level=logging.INFO)

# Токен та проксі (якщо проксі не потрібен — залиште None)
TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_БОТА")
PROXY = None  # Приклад: "http://user:pass@ip:port" або None

# --- 1. АСИНХРОННА БАЗА ДАНИХ ---
async def init_db():
    async with aiosqlite.connect('database.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                brand TEXT,
                max_price INTEGER,
                min_year INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sent_ads (
                ad_url TEXT PRIMARY KEY
            )
        ''')
        await db.commit()

# --- 2. НАЛАШТУВАННЯ AIOGRAM ---
session = AiohttpSession(proxy=PROXY) if PROXY else None
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())

class FilterState(StatesGroup):
    brand = State()
    max_price = State()
    min_year = State()

# --- 3. ХЕНДЛЕРИ ТЕЛЕГРАМ-БОТА ---
@dp.message(Command('start'))
async def start_cmd(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='🔍 Додати авто-фільтр', callback_data='add_filter')],
        [types.InlineKeyboardButton(text='📋 Мої сповіщення', callback_data='my_filters')]
    ])
    await message.answer(
        f'Cześć, {message.from_user.first_name}! 🚗⚡\n'
        f'Ласкаво просимо до MotoAirline Bot!\n'
        f'Я моніторю OLX та Otomoto в реальному часі.\n\n'
        f'Оберіть дію в меню нижче:',
        reply_markup=kb
    )

@dp.callback_query(F.data == 'add_filter')
async def start_filter(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer('Введіть марку авто (наприклад: bmw, audi, hyundai):')
    await state.set_state(FilterState.brand)
    await call.answer()

@dp.message(FilterState.brand)
async def process_brand(message: types.Message, state: FSMContext):
    # Очищаємо назву марки для підстави в URL (малі літери, без пробілів)
    brand_clean = message.text.strip().lower().replace(' ', '-')
    await state.update_data(brand=brand_clean)
    await message.answer('Введіть максимальну ціну в PLN (наприклад: 25000):')
    await state.set_state(FilterState.max_price)

@dp.message(FilterState.max_price)
async def process_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer('Будь ласка, введіть число!')
    await state.update_data(max_price=int(message.text))
    await message.answer('Введіть мінімальний рік випуску (наприклад: 2012):')
    await state.set_state(FilterState.min_year)

@dp.message(FilterState.min_year)
async def process_year(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer('Будь ласка, введіть рік числом!')
    
    data = await state.get_data()
    user_id = message.from_user.id
    brand = data['brand']
    max_price = data['max_price']
    min_year = int(message.text)

    async with aiosqlite.connect('database.db') as db:
        await db.execute(
            'INSERT INTO filters (user_id, brand, max_price, min_year) VALUES (?, ?, ?, ?)', 
            (user_id, brand, max_price, min_year)
        )
        await db.commit()

    await state.clear()
    await message.answer(
        f'✅ Фільтр успішно збережено та активовано!\n\n'
        f'🚘 Марка: <b>{escape(brand.upper())}</b>\n'
        f'💰 Ціна до: <b>{max_price} PLN</b>\n'
        f'📅 Рік від: <b>{min_year}</b>\n\n'
        f'🔎 Бот починає моніторинг OLX...',
        parse_mode="HTML"
    )

@dp.callback_query(F.data == 'my_filters')
async def show_filters(call: types.CallbackQuery):
    async with aiosqlite.connect('database.db') as db:
        async with db.execute('SELECT brand, max_price, min_year FROM filters WHERE user_id = ?', (call.from_user.id,)) as cursor:
            rows = await cursor.fetchall()
    
    if not rows:
        await call.message.answer('У вас ще немає активних фільтрів.')
        await call.answer()
        return
    
    msg = '📋 <b>Ваші активні фільтри:</b>\n\n'
    for r in rows:
        msg += f'• <b>{escape(r[0].upper())}</b> | до {r[1]} PLN | від {r[2]} року\n'
    await call.message.answer(msg, parse_mode="HTML")
    await call.answer()

# --- 4. ПАРСЕР ТА ФОНОВИЙ МОНІТОРИНГ ---
async def parse_olx(brand: str, max_price: int, min_year: int):
    # Актуальний формат URL для OLX.pl
    search_url = (
        f"https://www.olx.pl/motoryzacja/samochody/{brand}/"
        f"?search%5Bfilter_float_price%3Ato%5D={max_price}"
        f"&search%5Bfilter_float_year%3Afrom%5D={min_year}"
        f"&search%5Border%5D=created_at%3Adesc" # Сортування за новізною
    )
    
    ads = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }

    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(search_url, headers=headers, proxy=PROXY, timeout=15) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Шукаємо контейнери оголошень (усі верстки OLX використовують data-cy="l-card")
                    cards = soup.find_all('div', {'data-cy': 'l-card'})
                    
                    for card in cards:
                        link_tag = card.find('a', href=True)
                        title_tag = card.find('h6') or card.find('h4')
                        
                        if link_tag and title_tag:
                            link = link_tag['href']
                            if not link.startswith('http'):
                                link = 'https://www.olx.pl' + link
                            
                            # Ігноруємо рекламні промо-посилання третьої сторони
                            if 'otodom.pl' in link:
                                continue

                            title = title_tag.text.strip()
                            
                            # Шукаємо ціну серед тегів p або div
                            price_element = card.find('p', {'data-testid': 'ad-price'})
                            price = price_element.text.strip() if price_element else 'Ціна не вказана'

                            ads.append({
                                'title': title,
                                'price': price,
                                'url': link
                            })
                else:
                    logging.warning(f"Парсинг повернув статус {resp.status} для URL: {search_url}")
    except Exception as e:
        logging.error(f"Помилка парсингу OLX ({brand}): {e}")

    return ads

async def bg_monitoring():
    """Фонова задача: перевірка оголошень кожні 3 хвилини"""
    while True:
        try:
            async with aiosqlite.connect('database.db') as db:
                async with db.execute('SELECT user_id, brand, max_price, min_year FROM filters') as cursor:
                    filters = await cursor.fetchall()

                for user_id, brand, max_price, min_year in filters:
                    found_ads = await parse_olx(brand, max_price, min_year)
                    
                    for ad in found_ads:
                        # Перевіряємо, чи надсилали вже таке оголошення
                        async with db.execute('SELECT ad_url FROM sent_ads WHERE ad_url = ?', (ad['url'],)) as check_cursor:
                            if not await check_cursor.fetchone():
                                # Зберігаємо в базу
                                await db.execute('INSERT INTO sent_ads (ad_url) VALUES (?)', (ad['url'],))
                                await db.commit()

                                # Екрануємо текстові дані для HTML
                                safe_title = escape(ad['title'])
                                safe_price = escape(ad['price'])

                                msg_text = (
                                    f"🚨 <b>ЗНАЙДЕНО НОВЕ ОГОЛОШЕННЯ!</b>\n\n"
                                    f"📌 <b>{safe_title}</b>\n"
                                    f"💰 <b>Ціна:</b> {safe_price}\n\n"
                                    f"🔗 <a href='{ad['url']}'>Переглянути оголошення на OLX</a>"
                                )
                                try:
                                    await bot.send_message(chat_id=user_id, text=msg_text, parse_mode="HTML")
                                except (TelegramForbiddenError, TelegramBadRequest) as e:
                                    logging.warning(f"Не вдалося надіслати повідомлення користувачу {user_id}: {e}")
                    
                    # Невелика затримка між фільтрами, щоб не отримувати 429 Too Many Requests від OLX
                    await asyncio.sleep(2)

        except Exception as e:
            logging.error(f"Помилка у фоновому моніторингу: {e}")

        await asyncio.sleep(180)

# --- 5. ГОЛОВНИЙ ЗАПУСК ---
async def main():
    await init_db()
    # Запускаємо фоновий моніторинг
    asyncio.create_task(bg_monitoring())
    # Видаляємо застарілі webhook, якщо вони були
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
