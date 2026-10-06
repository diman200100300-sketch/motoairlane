import sqlite3
import logging

DB_NAME = "bot_database.db"
logger = logging.getLogger("ToolBoxAI")

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    """Ініціалізація бази даних та створення необхідних таблиць"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'ua',
                is_banned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                feature TEXT,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        logger.info("🗄 База даних успішно ініціалізована.")

def db_add_user(user_id: int, username: str = "", first_name: str = ""):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        conn.commit()

def db_get_user_language(user_id: int) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row['language']:
            return row['language']
        return 'ua'

def db_set_user_language(user_id: int, lang: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()

def db_is_banned(user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return bool(row['is_banned'])
        return False

def db_set_ban_status(user_id: int, status: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, user_id))
        conn.commit()

def db_log_usage(user_id: int, feature: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO usage_logs (user_id, feature) VALUES (?, ?)", (user_id, feature))
        conn.commit()

def db_get_all_user_ids() -> list:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        rows = cursor.fetchall()
        return [row['user_id'] for row in rows]

def db_get_stats() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM users WHERE is_banned = 1")
        banned_users = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM usage_logs")
        total_usage = cursor.fetchone()['total']
        
        cursor.execute("SELECT feature, COUNT(*) as count FROM usage_logs GROUP BY feature")
        feature_stats = {row['feature']: row['count'] for row in cursor.fetchall()}
        
        return {
            'total_users': total_users,
            'banned_users': banned_users,
            'total_usage': total_usage,
            'feature_stats': feature_stats
        }
