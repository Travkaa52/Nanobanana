# utils/helpers.py
import random
import re
from datetime import datetime
from config.settings import TIMEZONE

def now():
    """Текущее время"""
    return datetime.now(TIMEZONE)

def format_date(date):
    """Форматировать дату"""
    return date.strftime("%d.%m.%Y") if date else ""

def validate_dob(text):
    """Проверить дату рождения"""
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
        return False
    try:
        day, month, year = map(int, text.split('.'))
        return 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2024
    except:
        return False

def calculate_discount(price: int, value: int, type_: str) -> int:
    """Рассчитать скидку"""
    if type_ == 'fixed':
        return max(0, price - value)
    return int(price * (100 - value) / 100)

def generate_id(prefix: str = "") -> str:
    """Сгенерировать ID"""
    import hashlib
    import time
    return f"{prefix}{hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:8]}"

def format_tariff(key: str, data: dict) -> str:
    """Форматировать тариф"""
    days = "безстроково" if data['days'] is None else f"{data['days']} дн."
    return f"{data['emoji']} {data['name']} — {data['price']}₴ ({days})"
