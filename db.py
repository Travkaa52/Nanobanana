# db.py
# db.py (добавьте в начало)
from config import TIMEZONE
import os
import asyncpg
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Глобальный пул соединений
_pool: Optional[asyncpg.Pool] = None

async def init_db_pool():
    """Инициализация пула соединений с PostgreSQL Aiven"""
    global _pool
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL не задан в переменных окружения")
    
    try:
        # Для Aiven нужно специальное SSL конфигурирование
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=10,
            command_timeout=60,
            max_inactive_connection_lifetime=300,
            ssl='require'  # Aiven требует SSL
        )
        logger.info("✅ Пул соединений с PostgreSQL Aiven успешно создан")
        
        # Проверяем подключение
        async with _pool.acquire() as conn:
            await conn.execute("SELECT 1")
            logger.info("✅ Тестовое подключение успешно")
        
        return _pool
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
        raise

async def close_db_pool():
    """Закрытие пула соединений"""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("✅ Пул соединений с PostgreSQL закрыт")

@asynccontextmanager
async def get_connection():
    """Получение соединения из пула"""
    if not _pool:
        raise Exception("Пул соединений не инициализирован")
    async with _pool.acquire() as conn:
        yield conn

async def execute_query(query: str, *args) -> str:
    """Выполнение запроса без возврата результата"""
    async with get_connection() as conn:
        return await conn.execute(query, *args)

async def fetch_query(query: str, *args) -> List[asyncpg.Record]:
    """Выполнение запроса с возвратом всех строк"""
    async with get_connection() as conn:
        return await conn.fetch(query, *args)

async def fetch_row(query: str, *args) -> Optional[asyncpg.Record]:
    """Выполнение запроса с возвратом одной строки"""
    async with get_connection() as conn:
        return await conn.fetchrow(query, *args)

async def fetch_val(query: str, *args) -> Any:
    """Выполнение запроса с возвратом одного значения"""
    async with get_connection() as conn:
        return await conn.fetchval(query, *args)

# -------------------------
# ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ
# -------------------------
async def get_user(user_id: str) -> Optional[Dict]:
    """Получение пользователя по ID"""
    query = """
        SELECT user_id, username, first_name, balance, referred_by, 
               ref_count, has_bought, joined_date, total_spent, 
               language, blocked, tariff, tariff_purchase_date, tariff_expires_at
        FROM users 
        WHERE user_id = $1
    """
    row = await fetch_row(query, int(user_id))
    if row:
        return dict(row)
    return None

async def create_user(user_id: str, username: str, first_name: str, referred_by: str = None):
    """Создание нового пользователя"""
    now = datetime.now()
    query = """
        INSERT INTO users (user_id, username, first_name, referred_by, joined_date, tariff)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (user_id) DO NOTHING
    """
    await execute_query(query, int(user_id), username, first_name, 
                        int(referred_by) if referred_by else None, now, 'free')

async def update_user_balance(user_id: str, amount: int):
    """Обновление баланса пользователя"""
    query = "UPDATE users SET balance = balance + $1 WHERE user_id = $2"
    await execute_query(query, amount, int(user_id))

async def update_user_bought(user_id: str, amount: int):
    """Обновление статуса покупки"""
    query = "UPDATE users SET has_bought = TRUE, total_spent = total_spent + $1 WHERE user_id = $2"
    await execute_query(query, amount, int(user_id))

async def increment_ref_count(user_id: str):
    """Увеличение счетчика рефералов"""
    query = "UPDATE users SET ref_count = ref_count + 1 WHERE user_id = $1"
    await execute_query(query, int(user_id))

# -------------------------
# ФУНКЦИИ ДЛЯ РАБОТЫ С ТАРИФАМИ
# -------------------------
async def buy_tariff(user_id: str, tariff_key: str, duration_days: int = None):
    """Покупка тарифа пользователем"""
    now = datetime.now()
    purchase_date = now
    
    expires_at = None
    if duration_days is not None:
        expires_at = now + timedelta(days=duration_days)
    
    query = """
        UPDATE users 
        SET tariff = $1, tariff_purchase_date = $2, tariff_expires_at = $3
        WHERE user_id = $4
    """
    await execute_query(query, tariff_key, purchase_date, expires_at, int(user_id))

async def get_user_tariff_info(user_id: str) -> Dict:
    """Получение информации о тарифе пользователя"""
    user = await get_user(user_id)
    if not user:
        return {"tariff": "free", "is_active": False, "days_left": 0}
    
    tariff = user.get("tariff", "free")
    expires_at = user.get("tariff_expires_at")
    
    now = datetime.now()
    
    if expires_at and expires_at > now:
        days_left = (expires_at - now).days
        return {
            "tariff": tariff,
            "is_active": True,
            "days_left": days_left,
            "expires_at": expires_at,
            "purchase_date": user.get("tariff_purchase_date")
        }
    elif expires_at is None and tariff != "free":
        return {
            "tariff": tariff,
            "is_active": True,
            "days_left": -1,
            "expires_at": None,
            "purchase_date": user.get("tariff_purchase_date")
        }
    else:
        return {
            "tariff": tariff,
            "is_active": False,
            "days_left": 0,
            "expires_at": None,
            "purchase_date": None
        }

async def is_tariff_active(user_id: str) -> bool:
    """Проверка активности тарифа пользователя"""
    info = await get_user_tariff_info(user_id)
    return info["is_active"]

# -------------------------
# ФУНКЦИИ ДЛЯ РАБОТЫ С ПРОМОКОДАМИ
# -------------------------
async def create_promocode(
    code: str,
    discount_type: str,
    discount_value: int,
    max_activations: int = 1,
    expires_at: datetime = None,
    tariff_name: str = None
):
    """Создание промокода"""
    query = """
        INSERT INTO promocodes (code, discount_type, discount_value, max_activations, expires_at, tariff_name)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (code) DO UPDATE SET
            discount_type = EXCLUDED.discount_type,
            discount_value = EXCLUDED.discount_value,
            max_activations = EXCLUDED.max_activations,
            expires_at = EXCLUDED.expires_at,
            tariff_name = EXCLUDED.tariff_name,
            is_active = TRUE
    """
    await execute_query(
        query, code.upper(), discount_type, discount_value, 
        max_activations, expires_at, tariff_name
    )

async def get_promocode(code: str) -> Optional[Dict]:
    """Получение информации о промокоде"""
    query = """
        SELECT id, code, discount_type, discount_value, max_activations, 
               used_count, is_active, expires_at, tariff_name, created_at
        FROM promocodes 
        WHERE code = $1
    """
    row = await fetch_row(query, code.upper())
    return dict(row) if row else None

async def check_promocode_valid(code: str, user_id: str) -> tuple[bool, str, Dict]:
    """Проверка валидности промокода"""
    promo = await get_promocode(code)
    if not promo:
        return False, "❌ Промокод не знайдено", None
    
    if not promo.get("is_active", True):
        return False, "❌ Промокод не активний", None
    
    expires_at = promo.get("expires_at")
    if expires_at and expires_at < datetime.now():
        return False, "❌ Термін дії промокоду закінчився", None
    
    if promo.get("max_activations", 0) > 0:
        if promo.get("used_count", 0) >= promo["max_activations"]:
            return False, "❌ Ліміт активацій промокоду вичерпано", None
    
    query = "SELECT 1 FROM user_promocodes WHERE user_id = $1 AND promo_code = $2"
    used = await fetch_row(query, int(user_id), code.upper())
    if used:
        return False, "❌ Ви вже використовували цей промокод", None
    
    return True, "✅ Промокод дійсний", promo

async def apply_promocode(code: str, user_id: str) -> tuple[bool, str, Optional[Dict]]:
    """Активация промокода пользователем"""
    is_valid, message, promo = await check_promocode_valid(code, user_id)
    if not is_valid:
        return False, message, None
    
    if promo.get("tariff_name"):
        await buy_tariff(user_id, promo["tariff_name"], None)
        result = {"tariff": promo["tariff_name"], "free_tariff": True}
    else:
        result = {
            "discount_type": promo["discount_type"],
            "discount_value": promo["discount_value"],
            "free_tariff": False
        }
    
    query = """
        INSERT INTO user_promocodes (user_id, promo_code, used_at)
        VALUES ($1, $2, $3)
    """
    await execute_query(query, int(user_id), code.upper(), datetime.now())
    
    update_query = "UPDATE promocodes SET used_count = used_count + 1 WHERE code = $1"
    await execute_query(update_query, code.upper())
    
    return True, f"✅ Промокод {code} успішно активовано!", result

async def get_user_promocodes(user_id: str) -> List[Dict]:
    """Получение всех промокодов, активированных пользователем"""
    query = """
        SELECT p.code, p.discount_type, p.discount_value, up.used_at, p.tariff_name
        FROM user_promocodes up
        JOIN promocodes p ON up.promo_code = p.code
        WHERE up.user_id = $1
        ORDER BY up.used_at DESC
    """
    rows = await fetch_query(query, int(user_id))
    return [dict(row) for row in rows]

# -------------------------
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАКАЗАМИ
# -------------------------
async def create_order_async(order_id: str, user_id: str, tariff: str, fio: str, 
                             dob: str, sex: str, price: int, promo_code: str = None,
                             discount_amount: int = 0, final_price: int = None):
    """Создание заказа"""
    if final_price is None:
        final_price = price - discount_amount
    
    query = """
        INSERT INTO orders (order_id, user_id, tariff, fio, dob, sex, price, 
                           promo_code, discount_amount, final_price, created_at, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'pending')
    """
    await execute_query(
        query, order_id, int(user_id), tariff, fio, dob, sex, price,
        promo_code, discount_amount, final_price, datetime.now()
    )

async def update_order_status_async(order_id: str, status: str):
    """Обновление статуса заказа"""
    query = "UPDATE orders SET status = $1, approved_at = $2 WHERE order_id = $3"
    await execute_query(query, status, datetime.now(), order_id)

async def get_order_async(order_id: str) -> Optional[Dict]:
    """Получение заказа по ID"""
    query = """
        SELECT order_id, user_id, tariff, fio, dob, sex, price, 
               promo_code, discount_amount, final_price, created_at, status, approved_at
        FROM orders 
        WHERE order_id = $1
    """
    row = await fetch_row(query, order_id)
    return dict(row) if row else None