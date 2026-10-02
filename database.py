import sqlite3
import logging
import datetime

DB_NAME = "toolbox_bot.db"
logger = logging.getLogger(__name__)

def init_db():
    """Ініціалізація та створення всіх необхідних таблиць бази даних"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                lang TEXT DEFAULT 'uk',
                is_pro INTEGER DEFAULT 0,
                pro_expire TEXT,
                daily_video_count INTEGER DEFAULT 0,
                last_date TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                notifications INTEGER DEFAULT 1,
                voice_mode TEXT DEFAULT 'standard'
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Базу даних успішно ініціалізовано.")
    except Exception as e:
        logger.error(f"Помилка при ініціалізації бази даних: {e}")

def get_user_lang(user_id: int) -> str:
    """Отримати поточну мову інтерфейсу користувача"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else "uk"
    except Exception as e:
        logger.error(f"Помилка отримання мови користувача {user_id}: {e}")
        return "uk"

def set_user_lang(user_id: int, lang: str):
    """Встановити нову мову інтерфейсу для користувача"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Помилка оновлення мови для {user_id}: {e}")

def check_and_update_limit(user_id: int, action_type: str, max_limit: int) -> bool:
    """Перевірка та оновлення денних лімітів використання безкоштовних інструментів"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT is_pro, daily_video_count, last_date FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        today = datetime.date.today().isoformat()
        
        if not row:
            cursor.execute("INSERT INTO users (user_id, daily_video_count, last_date) VALUES (?, 1, ?)", (user_id, today))
            conn.commit()
            conn.close()
            return True
            
        is_pro, count, last_date = row
        if is_pro == 1:
            conn.close()
            return True  # PRO статус дає повний безліміт
            
        if last_date != today:
            cursor.execute("UPDATE users SET daily_video_count = 1, last_date = ? WHERE user_id = ?", (today, user_id))
            conn.commit()
            conn.close()
            return True
            
        if count >= max_limit:
            conn.close()
            return False
            
        cursor.execute("UPDATE users SET daily_video_count = daily_video_count + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Помилка перевірки лімітів для {user_id}: {e}")
        return True
