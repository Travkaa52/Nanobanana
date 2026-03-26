# config/settings.py
import os
import pytz
from dotenv import load_dotenv

load_dotenv()

# Bot
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID", "5423792783"))
NOTIFY_CHAT = int(os.getenv("NOTIFICATION_CHAT_ID", "-1002003419071"))
BOT_NAME = os.getenv("BOT_USERNAME", "FunsDiia_bot")
TIMEZONE = pytz.timezone("Europe/Kyiv")

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# Referral
REFERRAL_BONUS = 19
MIN_WITHDRAW = 50

# Payment
PAYMENT = "💳 Картка: 5355573250476310\n👤 Отримувач: SenseBank"
PAYMENT_LINK = "https://send.monobank.ua/jar/6R3gd9Ew8w"

# States
STATE = {
    'FIO': 1, 'DOB': 2, 'SEX': 3, 'PROMO': 4, 'PHOTO': 5,
    'FEEDBACK': 6, 'TARIFF_NAME': 7, 'TARIFF_PRICE': 8, 'TARIFF_DAYS': 9,
    'BROADCAST': 10, 'PROMO_CODE': 11, 'PROMO_TYPE': 12, 'PROMO_VALUE': 13, 'PROMO_LIMIT': 14
}

# Tariffs
TARIFFS = {
    "1_day": {"name": "🌙 1 день", "price": 20, "days": 1, "emoji": "🌙"},
    "30_days": {"name": "📅 30 днів", "price": 70, "days": 30, "emoji": "📅"},
    "90_days": {"name": "🌿 90 днів", "price": 150, "days": 90, "emoji": "🌿"},
    "180_days": {"name": "🌟 180 днів", "price": 190, "days": 180, "emoji": "🌟"},
    "forever": {"name": "💎 Назавжди", "price": 250, "days": None, "emoji": "💎"}
}
