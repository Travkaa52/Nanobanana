# config.py
import os
import pytz
from dotenv import load_dotenv

load_dotenv()

# Конфигурация бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "5423792783"))
NOTIFICATION_CHAT_ID = int(os.getenv("NOTIFICATION_CHAT_ID", "-1002003419071"))
TIMEZONE = pytz.timezone("Europe/Kyiv")
BOT_USERNAME = os.getenv("BOT_USERNAME", "FunsDiia_bot")
REFERRAL_REWARD = 19

PAYMENT_REQUISITES = "💳 Картка: 5355573250476310\n👤 Отримувач: SenseBank"
PAYMENT_LINK = "https://send.monobank.ua/jar/6R3gd9Ew8w"

# Состояния для ConversationHandler
AWAITING_FIO, AWAITING_DOB, AWAITING_SEX, AWAITING_PROMOCODE, AWAITING_PHOTO = range(5)
AWAITING_FEEDBACK = 5
AWAITING_NEW_TARIFF_NAME, AWAITING_NEW_TARIFF_PRICE, AWAITING_NEW_TARIFF_DAYS = range(6, 9)
AWAITING_BROADCAST_MESSAGE = 9
AWAITING_NEW_PROMOCODE_NAME, AWAITING_NEW_PROMOCODE_TYPE, AWAITING_NEW_PROMOCODE_VALUE, AWAITING_NEW_PROMOCODE_LIMIT = range(10, 14)