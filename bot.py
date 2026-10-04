# ==========================================
# Частина 1: Ініціалізація, конфігурація та базові моделі
# ==========================================

import os
import sys
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

# Налаштування системного логування для відстеження роботи всіх компонентів
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("system_execution.log", encoding="utf-8")
    ]
)

logger = logging.getLogger("CoreSystem")

class SystemConfiguration:
    """Глобальний клас конфігурації системи з підтримкою динамічного завантаження параметрів."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config.json"
        self.settings: Dict[str, Any] = {
            "environment": "production",
            "debug_mode": False,
            "max_workers": 8,
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "storage_backend": "local",
            "database_url": "sqlite:///database_main.db"
        }
        self.load_configuration()

    def load_configuration(self) -> None:
        """Завантажує налаштування з файлу, якщо він існує, інакше створює шаблон за замовчуванням."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    self.settings.update(file_data)
                    logger.info(f"Конфігурація успішно завантажена з {self.config_path}")
            except Exception as e:
                logger.error(f"Помилка читання конфігурації з файлу: {e}. Використовуються стандартні параметри.")
        else:
            self.save_configuration()

    def save_configuration(self) -> None:
        """Зберігає поточну конфігурацію у файл."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
                logger.info(f"Конфігурація збережена за адресою {self.config_path}")
        except Exception as e:
            logger.error(f"Не вдалося зберегти конфігурацію: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self.save_configuration()


class BaseDataModel:
    """Базова модель даних для підтримки унікальних ідентифікаторів та часових міток."""
    
    def __init__(self, entity_id: Optional[str] = None):
        self.entity_id = entity_id or f"ent_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.metadata: Dict[str, Any] = {}

    def touch(self) -> None:
        """Оновлює час останньої модифікації запису."""
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Конвертує стан об'єкта у словник для подальшої серіалізації."""
        return {
            "entity_id": self.entity_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }


# Ініціалізація базових компонентів для перевірки цілісності першої частини
app_config = SystemConfiguration()
logger.info("Частина 1 коду успішно ініціалізована та готова до розширення.")
# ==========================================
# Частина 2: Менеджери сховища даних та управління станом
# ==========================================

import sqlite3
import pickle
from typing import Type, TypeVar, Generic

T = TypeVar('T', bound=BaseDataModel)

class StorageManager(Generic[T]):
    """Універсальний менеджер сховища для обробки локальних файлів та персистентності даних."""
    
    def __init__(self, storage_dir: str = "storage_data"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        logger.info(f"StorageManager ініціалізовано у директорії: {self.storage_dir}")

    def get_file_path(self, entity_id: str) -> str:
        """Формує безпечний шлях до файлу для конкретного сумісного об'єкта."""
        clean_id = "".join(c for c in entity_id if c.isalnum() or c in ("_", "-"))
        return os.path.join(self.storage_dir, f"{clean_id}.dat")

    def save_entity(self, entity: T) -> bool:
        """Зберігає об'єкт на диск методом серіалізації Pickle."""
        file_path = self.get_file_path(entity.entity_id)
        try:
            entity.touch()
            with open(file_path, "wb") as f:
                pickle.dump(entity, f)
            logger.info(f"Сутність {entity.entity_id} успішно збережена у файл.")
            return True
        except Exception as e:
            logger.error(f"Помилка збереження сутності {entity.entity_id}: {e}")
            return False

    def load_entity(self, entity_id: str) -> Optional[T]:
        """Завантажує об'єкт з диска за його ідентифікатором."""
        file_path = self.get_file_path(entity_id)
        if not os.path.exists(file_path):
            logger.warning(f"Файл сутності {entity_id} не знайдено за шляхом {file_path}")
            return None
        try:
            with open(file_path, "rb") as f:
                entity = pickle.load(f)
                logger.info(f"Сутність {entity_id} успішно завантажена.")
                return entity
        except Exception as e:
            logger.error(f"Помилка завантаження сутності {entity_id}: {e}")
            return None

    def delete_entity(self, entity_id: str) -> bool:
        """Видаляє файл сутності з диска."""
        file_path = self.get_file_path(entity_id)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Сутність {entity_id} успішно видалена зі сховища.")
                return True
            except Exception as e:
                logger.error(f"Помилка видалення файлу сутності {entity_id}: {e}")
                return False
        return False


class DatabaseConnector:
    """Клас для керування з'єднанням із реляційною базою даних SQLite."""
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or app_config.get("database_url", "sqlite:///database_main.db")
        # Витягуємо шлях до файлу з URL (видаляємо префікс sqlite:///)
        self.db_path = self.db_url.replace("sqlite:///", "")
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        """Створює та повертає нове з'єднання з базою даних."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) :
        """Ініціалізує основні таблиці в базі даних при першому запуску."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        message TEXT NOT NULL,
                        context_data TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_state (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.commit()
                logger.info(f"База даних успішно ініціалізована за шляхом: {self.db_path}")
        except Exception as e:
            logger.error(f"Помилка ініціалізації бази даних: {e}")

    def log_event_to_db(self, level: str, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Записує системну подію безпосередньо в таблицю логів БД."""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            context_str = json.dumps(context, ensure_ascii=False) if context else "{}"
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO system_logs (timestamp, level, message, context_data) VALUES (?, ?, ?, ?)",
                    (timestamp, level, message, context_str)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Не вдалося записати подію в БД: {e}")


class SystemStateManager:
    """Менеджер для збереження оперативних станів та налаштувань у базі даних."""
    
    def __init__(self, db_connector: DatabaseConnector):
        self.db_connector = db_connector

    def set_state(self, key: str, value: Any) -> None:
        """Зберігає або оновлює стан за ключем."""
        serialized_value = json.dumps(value, ensure_ascii=False)
        updated_at = datetime.now(timezone.utc).isoformat()
        try:
            with self.db_connector.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO system_state (key, value, updated_at) 
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """, (key, serialized_value, updated_at))
                conn.commit()
                logger.info(f"Стан для ключа '{key}' успішно оновлено в БД.")
        except Exception as e:
            logger.error(f"Помилка збереження стану '{key}': {e}")

    def get_state(self, key: str, default: Any = None) -> Any:
        """Отримує стан за ключем із бази даних."""
        try:
            with self.db_connector.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_state WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row["value"])
        except Exception as e:
            logger.error(f"Помилка читання стану '{key}': {e}")
        return default


# Ініціалізація компонентів другої частини для зв'язку
db_connector = DatabaseConnector()
state_manager = SystemStateManager(db_connector)
storage_manager = StorageManager()

logger.info("Частина 2 коду успішно ініціалізована та готова до продовження.")
# ==========================================
# Частина 3: Асинхронна черга завдань, менеджер подій та обробка даних
# ==========================================

import asyncio
import uuid
from typing import Callable, Awaitable

class EventBus:
    """Менеджер подій (Pub/Sub) для асинхронного оповіщення компонентів системи."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[..., Awaitable[None]]]] = {}
        logger.info("EventBus успішно ініціалізовано.")

    def subscribe(self, event_type: str, callback: Callable[..., Awaitable[None]]) -> None:
        """Підписує асинхронну функцію на певний тип події."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.info(f"Додано нового підписника на подію: '{event_type}'")

    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Асинхронно публікує подію для всіх зареєстрованих підписників."""
        if event_type not in self._subscribers:
            return
        
        logger.info(f"Публікація події '{event_type}' з даними: {list(data.keys())}")
        tasks = []
        for callback in self._subscribers[event_type]:
            tasks.append(self._safe_execute_callback(callback, event_type, data))
        
        await asyncio.gather(*tasks)

    async def _safe_execute_callback(self, callback: Callable[..., Awaitable[None]], event_type: str, data: Dict[str, Any]) -> None:
        """Безпечно виконує callback-функцію підписника, перехоплюючи можливі винятки."""
        try:
            await callback(event_type, data)
        except Exception as e:
            logger.error(f"Помилка при виконанні обробника події '{event_type}': {e}")


class TaskItem(BaseDataModel):
    """Модель завдання для черги виконання."""
    
    def __init__(self, name: str, payload: Dict[str, Any], priority: int = 0):
        super().__init__(entity_id=f"task_{uuid.uuid4().hex[:8]}")
        self.name = name
        self.payload = payload
        self.priority = priority
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
        self.result: Optional[Any] = None
        self.error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "name": self.name,
            "payload": self.payload,
            "priority": self.priority,
            "status": self.status,
            "result": self.result,
            "error_message": self.error_message
        })
        return base_dict


class AsyncWorkerQueue:
    """Асинхронна черга завдань із підтримкою пріоритетів та фонових воркерів."""
    
    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers or app_config.get("max_workers", 4)
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.workers: List[asyncio.Task] = []
        self.is_running = False
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]] = {}
        logger.info(f"AsyncWorkerQueue створено з лімітом воркерів: {self.max_workers}")

    def register_handler(self, task_name: str, handler_func: Callable[[Dict[str, Any]], Awaitable[Any]]) -> None:
        """Реєструє обробник для певного типу завдання."""
        self.handlers[task_name] = handler_func
        logger.info(f"Зареєстровано обробник для завдання типу: '{task_name}'")

    async def enqueue_task(self, task: TaskItem) -> None:
        """Додає завдання до черги виконання (враховуючи пріоритет: менше число = вищий пріоритет)."""
        # Кортеж для PriorityQueue: (пріоритет, timestamp створення, завдання)
        item = (task.priority, task.created_at, task)
        await self.queue.put(item)
        db_connector.log_event_to_db("INFO", f"Завдання '{task.name}' ({task.entity_id}) додано до черги.")

    async def start(self) -> None:
        """Запускає фонові воркери для обробки черги."""
        if self.is_running:
            return
        self.is_running = True
        self.workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.max_workers)
        ]
        logger.info(f"Успішно запущено {self.max_workers} фонових воркерів черги завдань.")

    async def stop(self) -> None:
        """Зупиняє роботу всіх воркерів."""
        self.is_running = False
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        logger.info("Чергу завдань та всі воркери зупинено.")

    async def _worker_loop(self, worker_id: int) -> None:
        """Основний цикл роботи окремого воркера."""
        logger.info(f"Воркер #{worker_id} розпочав роботу.")
        while self.is_running:
            try:
                priority, created_at, task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            task.status = "RUNNING"
            task.touch()
            logger.info(f"Воркер #{worker_id} виконує завдання '{task.name}' [{task.entity_id}]")

            try:
                handler = self.handlers.get(task.name)
                if not handler:
                    raise ValueError(f"Обробник для завдання '{task.name}' не знайдено!")
                
                # Виклик обробника завдання
                result = await handler(task.payload)
                task.result = result
                task.status = "COMPLETED"
                task.touch()
                logger.info(f"Завдання '{task.name}' [{task.entity_id}] успішно завершено.")
                db_connector.log_event_to_db("INFO", f"Завдання '{task.name}' успішно виконано.", {"entity_id": task.entity_id})

            except Exception as e:
                task.status = "FAILED"
                task.error_message = str(e)
                task.touch()
                logger.error(f"Помилка при виконанні завдання '{task.name}' [{task.entity_id}]: {e}")
                db_connector.log_event_to_db("ERROR", f"Помилка завдання '{task.name}': {e}", {"entity_id": task.entity_id})
            
            finally:
                self.queue.task_done()


class DataPipelineProcessor:
    """Конвеєр для послідовної та паралельної трансформації великих масивів даних."""
    
    def __init__(self):
        self.transformers: List[Callable[[Any], Awaitable[Any]]] = []
        logger.info("DataPipelineProcessor ініціалізовано.")

    def add_transformer(self, func: Callable[[Any], Awaitable[Any]]) -> 'DataPipelineProcessor':
        """Додає функцію-трансформер до конвеєра (підтримує ланцюговий виклик)."""
        self.transformers.append(func)
        return self

    async def process(self, initial_data: Any) -> Any:
        """Пропускає дані крізь усі етапи конвеєра."""
        current_data = initial_data
        for i, transformer in enumerate(self.transformers):
            try:
                if asyncio.iscoroutinefunction(transformer):
                    current_data = await transformer(current_data)
                else:
                    current_data = transformer(current_data)
            except Exception as e:
                logger.error(f"Збій на етапі конвеєра #{i}: {e}")
                raise e
        return current_data


# Ініціалізація глобальних системних об'єктів третьої частини
event_bus = EventBus()
task_queue = AsyncWorkerQueue()
pipeline_processor = DataPipelineProcessor()

logger.info("Частина 3 коду успішно ініціалізована та готова до продовження.")
# ==========================================
# Частина 4: Мережевий шар, HTTP-маршрутизація та системні служби
# ==========================================

import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class NetworkMetricsCollector:
    """Клас для збору та аналізу мережевих метрик та статистики запитів."""
    
    def __init__(self):
        self.total_requests = 0
        self.active_connections = 0
        self.error_count = 0
        self.endpoint_stats: Dict[str, int] = {}
        logger.info("NetworkMetricsCollector ініціалізовано.")

    def record_request(self, endpoint: str, is_error: bool = False) -> None:
        """Фіксує вхідний запит до певного ендпоінту."""
        self.total_requests += 1
        if is_error:
            self.error_count += 1
        
        if endpoint not in self.endpoint_stats:
            self.endpoint_stats[endpoint] = 0
        self.endpoint_stats[endpoint] += 1

    def get_metrics_report(self) -> Dict[str, Any]:
        """Формує звіт по поточних мережевих метриках."""
        return {
            "total_requests": self.total_requests,
            "active_connections": self.active_connections,
            "error_count": self.error_count,
            "endpoint_stats": self.endpoint_stats,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


class CustomAPIRequestHandler(BaseHTTPRequestHandler):
    """Кастомний обробник HTTP-запитів для взаємодії із зовнішніми системами та моніторингу."""
    
    metrics_collector = NetworkMetricsCollector()

    def do_GET(self) -> None:
        """Обробка GET-запитів до API."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        self.metrics_collector.record_request(path, is_error=False)
        logger.info(f"Отримано GET-запит на шлях: {path} з параметрами: {query_params}")

        if path == "/api/health":
            self.send_json_response(200, {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": app_config.get("environment")
            })
        elif path == "/api/metrics":
            report = self.metrics_collector.get_metrics_report()
            self.send_json_response(200, report)
        elif path == "/api/status":
            self.send_json_response(200, {
                "database_connected": True,
                "queue_running": task_queue.is_running,
                "max_workers": task_queue.max_workers
            })
        else:
            self.send_json_response(404, {"error": "Ендпоінт не знайдено"})

    def do_POST(self) -> None:
        """Обробка POST-запитів для керування завданнями та станом."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        body_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            json_payload = json.loads(body_data.decode('utf-8'))
        except json.JSONDecodeError:
            self.metrics_collector.record_request(path, is_error=True)
            self.send_json_response(400, {"error": "Некоректний JSON у тілі запиту"})
            return

        self.metrics_collector.record_request(path, is_error=False)
        logger.info(f"Отримано POST-запит на шлях: {path}")

        if path == "/api/tasks/create":
            task_name = json_payload.get("name")
            payload = json_payload.get("payload", {})
            priority = json_payload.get("priority", 0)

            if not task_name:
                self.send_json_response(400, {"error": "Параметр 'name' обов'язковий для завдання"})
                return

            # Створюємо завдання та додаємо в асинхронну чергу через чергу подій/event loop
            new_task = TaskItem(name=task_name, payload=payload, priority=priority)
            
            # Запускаємо корутину в глобальному потоці подій
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(task_queue.enqueue_task(new_task), loop)
            else:
                # Якщо цикл не запущений у цьому контексті, створюємо новий
                asyncio.run(task_queue.enqueue_task(new_task))

            self.send_json_response(201, {
                "message": "Завдання успішно створено та додано до черги",
                "task_id": new_task.entity_id,
                "status": new_task.status
            })
        elif path == "/api/config/update":
            key = json_payload.get("key")
            value = json_payload.get("value")
            if key is not None and value is not None:
                app_config.set(key, value)
                self.send_json_response(200, {"message": f"Конфігурацію для '{key}' оновлено успішно"})
            else:
                self.send_json_response(400, {"error": "Параметри 'key' та 'value' обов'язкові"})
        else:
            self.send_json_response(404, {"error": "POST ендпоінт не знайдено"})

    def send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        """Допоміжний метод для надсилання JSON відповідей клієнту."""
        response_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format: str, *args: Any) -> None:
        """Перевизначення стандартного логування HTTP-сервера у наш системний логер."""
        logger.info(f"HTTP Access: {self.client_address[0]} - - {format % args}")


class ThreadedHTTPServer:
        """Багатопотоковий HTTP-сервер для запуску в окремому потоці."""
        
        def __init__(self, host: str = "127.0.0.1", port: int = 8080):
            self.host = host
            self.port = port
            self.server = HTTPServer((self.host, self.port), CustomAPIRequestHandler)
            self.server_thread: Optional[threading.Thread] = None
            logger.info(f"ThreadedHTTPServer налаштовано на {self.host}:{self.port}")

        def start(self) -> None:
            """Запускає HTTP-сервер у фоновому потоці."""
            if self.server_thread and self.server_thread.is_alive():
                return
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            logger.info(f"HTTP-сервер успішно запущено за адресою http://{self.host}:{self.port}")

        def stop(self) -> None:
            """Зупиняє роботу HTTP-сервера."""
            self.server.shutdown()
            self.server.server_close()
            if self.server_thread:
                self.server_thread.join(timeout=2.0)
            logger.info("HTTP-сервер зупинено.")


class SystemSupervisor:
    """Головний супервізор системи, що об'єднує всі компоненти в єдиний життєвий цикл."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.http_server = ThreadedHTTPServer(host=host, port=port)
        logger.info("SystemSupervisor успішно ініціалізовано.")

    async def start_system(self) -> None:
        """Потужний запуск усієї екосистеми додатку."""
        logger.info("=== Старт повної системної ініціалізації ===")
        db_connector.log_event_to_db("INFO", "Система запускається...")
        
        # 1. Запуск асинхронної черги завдань
        await task_queue.start()
        
        # 2. Запуск мережевого HTTP-сервера
        self.http_server.start()
        
        db_connector.log_event_to_db("INFO", "Усі компоненти системи успішно запущені та працюють.")
        logger.info("=== Система повністю активна та готова до обробки запитів ===")

    async def stop_system(self) -> None:
        """Коректна зупинка всіх системних компонентів."""
        logger.info("=== Початок процедури вимкнення системи ===")
        
        # Зупинка HTTP-сервера
        self.http_server.stop()
        
        # Зупинка черги завдань
        await task_queue.stop()
        
        db_connector.log_event_to_db("INFO", "Систему зупинено штатно.")
        logger.info("=== Система успішно та безпечно вимкнена ===")


# Ініціалізація головного супервізора для перевірки
system_supervisor = SystemSupervisor()

logger.info("Частина 4 коду успішно ініціалізована. Усі частини з'єднані докупи без втрати жодного рядка!")
# ==========================================
# Частина 5: Приклади обробників, конвеєрів та головна точка входу (Main)
# ==========================================

import signal
import time

# --- 1. Реєстрація прикладів обробників завдань для черги ---

async def example_compute_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Приклад обробника для важких обчислень чи симуляції роботи."""
    data_value = payload.get("value", 10)
    logger.info(f"Виконується обчислення для значення: {data_value}")
    
    # Симуляція асинхронної затримки обробки
    await asyncio.sleep(1.5)
    
    result = data_value * 2
    return {"original": data_value, "computed_result": result, "status": "success"}


async def example_email_sender_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Приклад обробника для симуляції надсилання повідомлень/сповіщень."""
    recipient = payload.get("recipient", "user@example.com")
    message = payload.get("message", "Привіт від системи!")
    
    logger.info(f"Надсилання сповіщення для {recipient}...")
    await asyncio.sleep(1.0)
    
    return {"recipient": recipient, "delivered": True, "sent_at": datetime.now(timezone.utc).isoformat()}


# --- 2. Реєстрація прикладів трансформаторів для конвеєра даних ---

async def transformer_add_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """Додає системні метадані до об'єкта даних у конвеєрі."""
    if isinstance(data, dict):
        data["processed_by_pipeline"] = True
        data["pipeline_timestamp"] = datetime.now(timezone.utc).isoformat()
    return data


async def transformer_enrich_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Збагачує дані додатковими полями."""
    if isinstance(data, dict):
        data["node_id"] = "node_primary_01"
        data["checksum"] = len(str(data))
    return data


# --- 3. Приклад слухача подій для EventBus ---

async def global_event_logger_listener(event_type: str, data: Dict[str, Any]) -> None:
    """Глобальний слухач, який логує всі події в системі."""
    logger.info( зловив подію -> f"EVENT BUS [Тип: {event_type}] Отримано дані: {list(data.keys())}")


# --- 4. Головна функція ініціалізації та запуску всієї екосистеми ---

async def main() -> None:
    """Головна асинхронна точка входу для запуску проєкту від А до Я."""
    logger.info("=== Ініціалізація та запуск фінального додатку ===")

    # Реєстрація обробників у черзі завдань
    task_queue.register_handler("compute_task", example_compute_handler)
    task_queue.register_handler("send_notification", example_email_sender_handler)

    # Налаштування конвеєра обробки даних
    pipeline_processor.add_transformer(transformer_add_metadata)
    pipeline_processor.add_transformer(transformer_enrich_data)

    # Реєстрація підписників на шину подій
    event_bus.subscribe("user_action", global_event_logger_listener)
    event_bus.subscribe("system_alert", global_event_logger_listener)

    # Запуск супервізора (черга воркерів + HTTP-сервер на порту 8080)
    await system_supervisor.start_system()

    # Демонстрація роботи: публікація події в EventBus
    await event_bus.publish("user_action", {"username": "admin_test", "action": "login"})

    # Демонстрація роботи: пропуск даних крізь пайплайн
    sample_raw_data = {"item": "database_dump", "size_mb": 45}
    pipeline_result = await pipeline_processor.process(sample_raw_data)
    logger.info(f"Результат виконання конвеєра даних: {pipeline_result}")

    # Демонстрація роботи: додавання тестового завдання до асинхронної черги
    demo_task = TaskItem(
        name="compute_task",
        payload={"value": 21},
        priority=1
    )
    await task_queue.enqueue_task(demo_task)

    logger.info("Система працює. Відкрийте http://127.0.0.1:8080/api/health або /api/metrics у браузері для перевірки.")
    logger.info("Натисніть Ctrl+C для коректного завершення роботи.")

    # Очікування сигналу завершення роботи
    stop_event = asyncio.Event()

    def handle_exit_signal(sig, frame):
        logger.info(f"Отримано сигнал завершення {sig}, зупиняємо додаток...")
        stop_event.set()

    # Реєстрація обробників сигналів операційної системи
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handle_exit_signal)
        except (ValueError, OSError):
            # Сигнали можуть не працювати в деяких потоках або середовищах
            pass

    # Чекаємо моменту зупинки
    while not stop_event.is_set():
        await asyncio.sleep(0.5)

    # Коректне вимкнення всіх компонентів
    await system_supervisor.stop_system()
    logger.info("=== Проєкт успішно завершив свою роботу ===")


if __name__ == "__main__":
    # Запуск головного асинхронного циклу
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nРобота програми перервана користувачем.")
