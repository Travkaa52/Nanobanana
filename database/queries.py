# database/queries.py
from datetime import datetime, timedelta
from database.db import execute, fetch, fetchone

# ========== USERS ==========
async def get_user(uid: int) -> dict:
    return await fetchone("SELECT * FROM users WHERE user_id = $1", uid)

async def create_user(uid: int, name: str, username: str, referrer: int = None):
    await execute("""
        INSERT INTO users (user_id, name, username, referrer, joined, tariff)
        VALUES ($1, $2, $3, $4, $5, 'free')
        ON CONFLICT (user_id) DO NOTHING
    """, uid, name, username, referrer, datetime.now())

async def update_balance(uid: int, amount: int):
    await execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, uid)

async def add_ref_bonus(uid: int):
    await execute("UPDATE users SET refs = refs + 1 WHERE user_id = $1", uid)
    await update_balance(uid, 19)

async def buy_tariff(uid: int, tariff: str, days: int = None):
    start = datetime.now()
    end = start + timedelta(days=days) if days else None
    await execute("""
        UPDATE users 
        SET tariff = $1, tariff_start = $2, tariff_end = $3, bought = TRUE
        WHERE user_id = $4
    """, tariff, start, end, uid)

async def is_tariff_active(uid: int) -> bool:
    user = await get_user(uid)
    if not user or user['tariff'] == 'free':
        return False
    if user['tariff_end'] is None:
        return True
    return user['tariff_end'] > datetime.now()

# ========== ORDERS ==========
async def create_order(oid: str, uid: int, tariff: str, fio: str, dob: str, sex: str, 
                       price: int, promo: str = None, discount: int = 0, final: int = None):
    await execute("""
        INSERT INTO orders (order_id, user_id, tariff, fio, dob, sex, price, promo_code, discount_amount, final_price, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    """, oid, uid, tariff, fio, dob, sex, price, promo, discount, final or price - discount, datetime.now())

async def update_order(oid: str, status: str):
    await execute("UPDATE orders SET status = $1, approved_at = $2 WHERE order_id = $3", status, datetime.now(), oid)

# ========== PROMOCODES ==========
async def get_promo(code: str) -> dict:
    return await fetchone("SELECT * FROM promocodes WHERE code = $1 AND is_active = TRUE", code.upper())

async def use_promo(code: str, uid: int) -> tuple:
    promo = await get_promo(code)
    if not promo:
        return False, "❌ Промокод не знайдено"
    if promo['expires_at'] and promo['expires_at'] < datetime.now():
        return False, "❌ Термін дії минув"
    if promo['max_activations'] > 0 and promo['used_count'] >= promo['max_activations']:
        return False, "❌ Ліміт вичерпано"
    
    used = await fetchone("SELECT 1 FROM user_promocodes WHERE user_id = $1 AND promo_code = $2", uid, code)
    if used:
        return False, "❌ Ви вже використовували цей промокод"
    
    await execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = $1", code)
    await execute("INSERT INTO user_promocodes (user_id, promo_code, used_at) VALUES ($1, $2, $3)", uid, code, datetime.now())
    
    return True, f"✅ Промокод {code} активовано!", promo
