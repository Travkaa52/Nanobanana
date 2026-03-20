import os
import json
import logging
import io
import random
import re
import pytz
import time
import hashlib
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any, List
from contextlib import contextmanager

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
    ContextTypes, filters, ConversationHandler
)
from telegram.error import TelegramError

# -------------------------
# НАЛАШТУВАННЯ
# -------------------------
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Токен бота не знайдено в змінних оточення!")

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "5423792783"))
NOTIFICATION_CHAT_ID = int(os.getenv("NOTIFICATION_CHAT_ID", "-1002003419071"))
TIMEZONE = pytz.timezone("Europe/Kyiv")
BOT_USERNAME = os.getenv("BOT_USERNAME", "FunsDiia_bot")

DB_FILE = "funsdiia.db"
REFERRAL_REWARD = 19

PAYMENT_REQUISITES = "💳 Картка: 5355573250476310\n👤 Отримувач: SenseBank"
PAYMENT_LINK = "https://send.monobank.ua/jar/6R3gd9Ew8w"

# Состояния для ConversationHandler
AWAITING_FIO, AWAITING_DOB, AWAITING_SEX, AWAITING_PROMOCODE, AWAITING_PHOTO = range(5)
AWAITING_FEEDBACK = 5
AWAITING_NEW_TARIFF_NAME, AWAITING_NEW_TARIFF_PRICE, AWAITING_NEW_TARIFF_DAYS = range(6, 9)
AWAITING_BROADCAST_MESSAGE = 9
AWAITING_NEW_PROMOCODE_NAME, AWAITING_NEW_PROMOCODE_TYPE, AWAITING_NEW_PROMOCODE_VALUE, AWAITING_NEW_PROMOCODE_LIMIT = range(10, 14)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"))
)
logger = logging.getLogger(__name__)

# -------------------------
# РОБОТА З БАЗОЮ ДАНИХ SQLITE
# -------------------------
def init_db():
    """Ініціалізація бази даних"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            referred_by TEXT,
            ref_count INTEGER DEFAULT 0,
            has_bought INTEGER DEFAULT 0,
            joined_date TEXT,
            total_spent INTEGER DEFAULT 0,
            language TEXT DEFAULT 'uk',
            blocked INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            user_id TEXT,
            tariff TEXT,
            fio TEXT,
            dob TEXT,
            sex TEXT,
            price INTEGER,
            promo_code TEXT,
            discount_amount INTEGER DEFAULT 0,
            final_price INTEGER,
            created_at TEXT,
            status TEXT DEFAULT 'pending',
            approved_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id TEXT PRIMARY KEY,
            user_id TEXT,
            username TEXT,
            first_name TEXT,
            feedback TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'new',
            replied_at TEXT,
            admin_reply TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tariffs (
            tariff_key TEXT PRIMARY KEY,
            name TEXT,
            price INTEGER,
            days INTEGER,
            emoji TEXT,
            active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            discount_type INTEGER,
            discount_value INTEGER,
            usage_limit INTEGER,
            used_count INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_promocodes (
            user_id TEXT,
            promo_code TEXT,
            used_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (promo_code) REFERENCES promocodes(code),
            PRIMARY KEY (user_id, promo_code)
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM tariffs")
    if cursor.fetchone()[0] == 0:
        default_tariffs = [
            ("1_day", "🌙 1 день", 20, 1, "🌙", 1),
            ("30_days", "📅 30 днів", 70, 30, "📅", 1),
            ("90_days", "🌿 90 днів", 150, 90, "🌿", 1),
            ("180_days", "🌟 180 днів", 190, 180, "🌟", 1),
            ("forever", "💎 Назавжди", 250, None, "💎", 1)
        ]
        cursor.executemany(
            "INSERT INTO tariffs (tariff_key, name, price, days, emoji, active) VALUES (?, ?, ?, ?, ?, ?)",
            default_tariffs
        )
    
    conn.commit()
    conn.close()

def db_execute(query: str, params: tuple = ()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()

def db_fetch_all(query: str, params: tuple = ()) -> List[tuple]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchall()
    conn.close()
    return result

def db_fetch_one(query: str, params: tuple = ()) -> Optional[tuple]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    return result

# -------------------------
# ФУНКЦІЇ ДЛЯ РОБОТИ З КОРИСТУВАЧАМИ
# -------------------------
def get_user(user_id: str) -> Optional[dict]:
    result = db_fetch_one(
        "SELECT user_id, username, first_name, balance, referred_by, ref_count, has_bought, joined_date, total_spent, language, blocked FROM users WHERE user_id = ?",
        (user_id,)
    )
    if result:
        return {
            "user_id": result[0], "username": result[1], "first_name": result[2],
            "balance": result[3], "referred_by": result[4], "ref_count": result[5],
            "has_bought": bool(result[6]), "joined_date": result[7], "total_spent": result[8],
            "language": result[9], "blocked": bool(result[10])
        }
    return None

def create_user(user_id: str, username: str, first_name: str, referred_by: str = None):
    db_execute(
        "INSERT INTO users (user_id, username, first_name, referred_by, joined_date) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, first_name, referred_by, datetime.now(TIMEZONE).isoformat())
    )

def update_user_balance(user_id: str, amount: int):
    db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

def update_user_bought(user_id: str, amount: int):
    db_execute("UPDATE users SET has_bought = 1, total_spent = total_spent + ? WHERE user_id = ?", (amount, user_id))

def increment_ref_count(user_id: str):
    db_execute("UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?", (user_id,))

# -------------------------
# ФУНКЦІЇ ДЛЯ РОБОТИ З ЗАМОВЛЕННЯМИ
# -------------------------
def create_order(order_id: str, user_id: str, tariff: str, fio: str, dob: str, sex: str, 
                 price: int, promo_code: str = None, discount_amount: int = 0, final_price: int = None):
    if final_price is None:
        final_price = price - discount_amount
    db_execute(
        "INSERT INTO orders (order_id, user_id, tariff, fio, dob, sex, price, promo_code, discount_amount, final_price, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, user_id, tariff, fio, dob, sex, price, promo_code, discount_amount, final_price, datetime.now(TIMEZONE).isoformat())
    )

def update_order_status(order_id: str, status: str):
    db_execute("UPDATE orders SET status = ?, approved_at = ? WHERE order_id = ?", 
               (status, datetime.now(TIMEZONE).isoformat(), order_id))

def get_order(order_id: str) -> Optional[dict]:
    result = db_fetch_one(
        "SELECT order_id, user_id, tariff, fio, dob, sex, price, promo_code, discount_amount, final_price, created_at, status, approved_at FROM orders WHERE order_id = ?",
        (order_id,)
    )
    if result:
        return {
            "order_id": result[0], "user_id": result[1], "tariff": result[2],
            "fio": result[3], "dob": result[4], "sex": result[5],
            "price": result[6], "promo_code": result[7], "discount_amount": result[8],
            "final_price": result[9], "created_at": result[10], "status": result[11], "approved_at": result[12]
        }
    return None

# -------------------------
# ФУНКЦІЇ ДЛЯ РОБОТИ З ВІДГУКАМИ
# -------------------------
def create_feedback(feedback_id: str, user_id: str, username: str, first_name: str, feedback_text: str):
    db_execute(
        "INSERT INTO feedback (feedback_id, user_id, username, first_name, feedback, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (feedback_id, user_id, username, first_name, feedback_text, datetime.now(TIMEZONE).isoformat())
    )

def update_feedback_status(feedback_id: str, status: str, admin_reply: str = None):
    if admin_reply:
        db_execute(
            "UPDATE feedback SET status = ?, replied_at = ?, admin_reply = ? WHERE feedback_id = ?",
            (status, datetime.now(TIMEZONE).isoformat(), admin_reply, feedback_id)
        )
    else:
        db_execute("UPDATE feedback SET status = ? WHERE feedback_id = ?", (status, feedback_id))

def get_feedback(feedback_id: str) -> Optional[dict]:
    result = db_fetch_one(
        "SELECT feedback_id, user_id, username, first_name, feedback, created_at, status, replied_at, admin_reply FROM feedback WHERE feedback_id = ?",
        (feedback_id,)
    )
    if result:
        return {
            "feedback_id": result[0], "user_id": result[1], "username": result[2],
            "first_name": result[3], "feedback": result[4], "created_at": result[5],
            "status": result[6], "replied_at": result[7], "admin_reply": result[8]
        }
    return None

# -------------------------
# ФУНКЦІЇ ДЛЯ РОБОТИ З ТАРИФАМИ
# -------------------------
def load_tariffs() -> dict:
    results = db_fetch_all("SELECT tariff_key, name, price, days, emoji, active FROM tariffs")
    tariffs = {}
    for row in results:
        tariffs[row[0]] = {
            "name": row[1], "price": row[2], "days": row[3],
            "emoji": row[4], "active": bool(row[5])
        }
    return tariffs

def add_tariff(key: str, name: str, price: int, days: int, emoji: str, active: int = 1):
    db_execute(
        "INSERT INTO tariffs (tariff_key, name, price, days, emoji, active) VALUES (?, ?, ?, ?, ?, ?)",
        (key, name, price, days, emoji, active)
    )

def delete_tariff(key: str):
    db_execute("DELETE FROM tariffs WHERE tariff_key = ?", (key,))

def get_active_tariffs() -> dict:
    tariffs = load_tariffs()
    return {k: v for k, v in tariffs.items() if v.get("active", True)}

def format_tariff_text(tariff_key: str, tariff_data: dict) -> str:
    return f"{tariff_data.get('emoji', '📦')} {tariff_data.get('name', tariff_key)} — {tariff_data.get('price', 0)}₴"

# -------------------------
# ФУНКЦІЇ ДЛЯ РОБОТИ З ПРОМОКОДАМИ
# -------------------------
def create_promocode(code: str, discount_type: int, discount_value: int, usage_limit: int):
    db_execute(
        "INSERT INTO promocodes (code, discount_type, discount_value, usage_limit, created_at) VALUES (?, ?, ?, ?, ?)",
        (code.upper(), discount_type, discount_value, usage_limit, datetime.now(TIMEZONE).isoformat())
    )

def get_promocode(code: str) -> Optional[dict]:
    result = db_fetch_one(
        "SELECT code, discount_type, discount_value, usage_limit, used_count, active FROM promocodes WHERE code = ?",
        (code.upper(),)
    )
    if result:
        return {
            "code": result[0], "discount_type": result[1], "discount_value": result[2],
            "usage_limit": result[3], "used_count": result[4], "active": bool(result[5])
        }
    return None

def use_promocode(code: str, user_id: str) -> tuple:
    promo = get_promocode(code)
    if not promo:
        return False, 0, "❌ Промокод не знайдено"
    if not promo["active"]:
        return False, 0, "❌ Промокод не активний"
    
    used = db_fetch_one(
        "SELECT 1 FROM user_promocodes WHERE user_id = ? AND promo_code = ?",
        (user_id, code.upper())
    )
    if used:
        return False, 0, "❌ Ви вже використовували цей промокод"
    
    if promo["usage_limit"] > 0 and promo["used_count"] >= promo["usage_limit"]:
        return False, 0, "❌ Ліміт використань промокоду вичерпано"
    
    if promo["discount_type"] == 1:
        return True, promo["discount_value"], f"✅ Промокод {code} активовано! Знижка {promo['discount_value']}₴"
    else:
        return True, promo["discount_value"], f"✅ Промокод {code} активовано! Знижка {promo['discount_value']}%"

def apply_promocode_to_price(price: int, discount_value: int, discount_type: int) -> int:
    if discount_type == 1:
        return max(0, price - discount_value)
    else:
        return int(price * (100 - discount_value) / 100)

def mark_promocode_used(code: str, user_id: str):
    db_execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code.upper(),))
    db_execute(
        "INSERT INTO user_promocodes (user_id, promo_code, used_at) VALUES (?, ?, ?)",
        (user_id, code.upper(), datetime.now(TIMEZONE).isoformat())
    )

def get_all_promocodes() -> List[dict]:
    results = db_fetch_all("SELECT code, discount_type, discount_value, usage_limit, used_count, active, created_at FROM promocodes ORDER BY created_at DESC")
    return [{
        "code": r[0], "discount_type": r[1], "discount_value": r[2],
        "usage_limit": r[3], "used_count": r[4], "active": bool(r[5]), "created_at": r[6]
    } for r in results]

def toggle_promocode_active(code: str):
    promo = get_promocode(code)
    if promo:
        db_execute("UPDATE promocodes SET active = ? WHERE code = ?", (0 if promo["active"] else 1, code.upper()))

def delete_promocode(code: str):
    db_execute("DELETE FROM promocodes WHERE code = ?", (code.upper(),))

# -------------------------
# ГЕНЕРАЦІЯ ДАНИХ
# -------------------------
def generate_rnokpp() -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(10))

def generate_passport_number() -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(9))

def generate_uznr() -> str:
    year = random.randint(1990, 2010)
    return f"{year}0128-{random.randint(10000, 99999)}"

def generate_prava_number() -> str:
    return f"AUX{random.randint(100000, 999999)}"

def generate_zagran_number() -> str:
    return f"FX{random.randint(100000, 999999)}"

def generate_bank_address() -> str:
    districts = ["Харківський", "Чугуївський", "Ізюмський", "Лозівський", "Богодухівський"]
    cities = ["м. Харків", "м. Чугуїв", "м. Мерефа", "м. Люботин", "смт Пісочин"]
    streets = ["Гарібальді", "Сумська", "Пушкінська", "Полтавський Шлях", "пр. Науки", "Клочківська"]
    
    district = random.choice(districts)
    city = random.choice(cities)
    street = random.choice(streets)
    building = random.randint(1, 150)
    apartment = random.randint(1, 250)
    
    return f"Харківська область, {district} район {city}, вул. {street}, буд. {building}, кв. {apartment}"

def generate_js_content(data: dict) -> str:
    try:
        rnokpp = generate_rnokpp()
        pass_num = generate_passport_number()
        uznr = generate_uznr()
        prava_num = generate_prava_number()
        zagran_num = generate_zagran_number()
        bank_addr = generate_bank_address()

        u_sex = data.get("sex", "Ж")
        sex_ua, sex_en = ("Ч", "M") if u_sex == "M" else ("Ж", "W")
        date_now = datetime.now(TIMEZONE).strftime("%d.%m.%Y")
        date_out = (datetime.now(TIMEZONE) + timedelta(days=3650)).strftime("%d.%m.%Y")
        
        student_number = f"{random.randint(2020, 2024)}{random.randint(100000, 999999)}"
        diploma_number = f"MT-{random.randint(100000, 999999)}"
        
        universities = ["ХНУ імені Каразіна", "НТУ ХПІ", "ХНЕУ імені С. Кузнеця", "ХНМУ", "ХНУРЕ"]
        faculties = ["Фізико-технічний", "Комп'ютерних наук", "Економічний", "Медичний", "Радіоелектроніки"]
        
        university = random.choice(universities)
        fakultet = random.choice(faculties)
        
        date_give_z = (datetime.now(TIMEZONE) - timedelta(days=random.randint(1000, 2000))).strftime("%d.%m.%Y")
        date_out_z = (datetime.now(TIMEZONE) + timedelta(days=random.randint(3000, 4000))).strftime("%d.%m.%Y")
        
        is_rights_enabled = random.choice([True, True, True, False])
        is_zagran_enabled = random.choice([True, True, False])
        is_diploma_enabled = random.choice([True, False])
        is_study_enabled = random.choice([True, True, False])

        return f"""// ========================================
// АВТОМАТИЧНО ЗГЕНЕРОВАНИЙ ФАЙЛ
// ========================================
// Дата: {date_now}
// Замовлення: {data.get('order_id', 'unknown')}
// ========================================

// === ОСНОВНІ ДАНІ ===
var fio                = "{data.get('fio', '')}";
var fio_en             = "{data.get('fio_en', data.get('fio', ''))}";
var birth              = "{data.get('dob', '')}";
var date_give          = "{date_now}";
var date_out           = "{date_out}";
var organ              = "0512";
var rnokpp             = "{rnokpp}";
var uznr               = "{uznr}";
var pass_number        = "{pass_num}";

// === ПРОПИСКА ===
var legalAdress        = "Харківська область";
var live               = "Харківська область";
var bank_adress        = "{bank_addr}";

// === СТАТЬ ===
var sex                = "{sex_ua}";
var sex_en             = "{sex_en}";

// === ВОДІЙСЬКІ ПРАВА ===
var rights_categories  = "A, B";
var prava_number       = "{prava_num}";
var prava_date_give    = "{date_now}";
var prava_date_out     = "{date_out}";
var pravaOrgan         = "0512";

// === ОСВІТА ===
var university         = "{university}";
var fakultet           = "{fakultet}";
var stepen_dip         = "Магістра";
var univer_dip         = "{university}";
var dayout_dip         = "{date_out}";
var special_dip        = "Прикладна математика";
var number_dip         = "{diploma_number}";
var form               = "Очна";

// === ЗАГРАНПАСПОРТ ===
var zagran_number      = "{zagran_num}";
var dateGiveZ          = "{date_give_z}";
var dateOutZ           = "{date_out_z}";

// === СТУДЕНТСЬКИЙ ===
var student_number     = "{student_number}";
var student_date_give  = "{date_now}";
var student_date_out   = "{date_out}";

// === НАЛАШТУВАННЯ ===
var isRightsEnabled    = {str(is_rights_enabled).lower()};
var isZagranEnabled    = {str(is_zagran_enabled).lower()};
var isDiplomaEnabled   = {str(is_diploma_enabled).lower()};
var isStudyEnabled     = {str(is_study_enabled).lower()};

// === ФАЙЛИ ===
var photo_passport     = "1.png";
var photo_rights       = "1.png";
var photo_students     = "1.png";
var photo_zagran       = "1.png";
var signPng            = "sign.png";

// ========================================
"""
    except Exception as e:
        logger.error(f"Помилка генерації JS: {e}")
        return "// Помилка генерації даних"

# -------------------------
# ОСНОВНІ ОБРОБНИКИ
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = str(update.effective_user.id)
        user = get_user(uid)
        
        ref_by = None
        if context.args and context.args[0]:
            potential_ref = context.args[0]
            if potential_ref != uid:
                ref_by = potential_ref
        
        if not user:
            create_user(uid, update.effective_user.username, update.effective_user.first_name, ref_by)
            if ref_by:
                try:
                    await context.bot.send_message(
                        ref_by,
                        f"👋 <b>Чудова новина!</b>\n\n"
                        f"Користувач {update.effective_user.first_name} приєднався за вашим посиланням!\n"
                        f"Щойно він зробить перше замовлення, ви отримаєте {REFERRAL_REWARD}₴ на рахунок.",
                        parse_mode="HTML"
                    )
                except:
                    pass

        kb = [
            [InlineKeyboardButton("🛍️ КАТАЛОГ ТАРИФІВ", callback_data="catalog")],
            [InlineKeyboardButton("👥 РЕФЕРАЛЬНА ПРОГРАМА", callback_data="ref_menu")],
            [InlineKeyboardButton("💬 ЗВОРОТНИЙ ЗВ'ЯЗОК", callback_data="feedback")],
            [InlineKeyboardButton("ℹ️ ПРО НАС", callback_data="about")]
        ]
        
        if str(update.effective_user.id) == str(ADMIN_USER_ID):
            kb.append([InlineKeyboardButton("👑 АДМІН-ПАНЕЛЬ", callback_data="admin_panel")])
        
        welcome_text = (
            f"🌸 <b>Вітаємо, {update.effective_user.first_name}!</b>\n\n"
            f"Раді вітати вас у <b>FunsDiia</b> — вашому надійному помічнику в генерації документів.\n\n"
            f"✨ <b>Що ми пропонуємо:</b>\n"
            f"• 📄 Генерація документів будь-якої складності\n"
            f"• ⚡️ Швидке виконання замовлень\n"
            f"• 💰 Вигідна реферальна програма\n"
            f"• 🎟️ Система промокодів для знижок\n"
            f"• 🎯 Індивідуальний підхід до кожного клієнта\n\n"
            f"Оберіть потрібний розділ нижче 👇"
        )
        
        await update.effective_message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в start: {e}")

async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "ℹ️ <b>Про бота FunsDiia</b>\n\n"
        "Ми — команда професіоналів, яка допомагає людям отримувати необхідні документи швидко та якісно.\n\n"
        "📌 <b>Як це працює:</b>\n"
        "1️⃣ Оберіть відповідний тариф у каталозі\n"
        "2️⃣ Введіть свої дані (ПІБ, дату народження, стать)\n"
        "3️⃣ Введіть промокод (якщо є) або пропустіть\n"
        "4️⃣ Надішліть фото 3x4\n"
        "5️⃣ Отримайте готові файли після підтвердження\n\n"
        "💡 <b>Чому обирають нас:</b>\n"
        "• ⚡️ Швидкість виконання — до 10 хвилин\n"
        "• 🎯 Висока якість генерації\n"
        "• 💰 Вигідні ціни та бонуси\n"
        "• 🎟️ Система промокодів для знижок\n"
        "• 🤝 Індивідуальний підхід\n\n"
        "📞 <b>Контакти для зв'язку:</b>\n"
        "• Адміністратор: @admin\n\n"
        "💰 <b>Оплата:</b>\n"
        "• Картка SenseBank\n"
        "• Monobank (миттєво)\n\n"
        "Дякуємо, що обираєте нас! 🌟"
    )
    
    kb = [[InlineKeyboardButton("🔙 НАЗАД ДО ГОЛОВНОГО", callback_data="home")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML", disable_web_page_preview=True)

async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "💬 <b>Зворотний зв'язок</b>\n\n"
        "Ми завжди раді почути вашу думку! 🌸\n\n"
        "📝 <b>Ви можете:</b>\n"
        "• Залишити відгук про роботу бота\n"
        "• Повідомити про помилку або неточність\n"
        "• Запропонувати ідею для покращення\n"
        "• Поставити запитання адміністратору\n\n"
        "✍️ <b>Напишіть ваше повідомлення нижче</b>\n"
        "Ми відповімо вам найближчим часом (зазвичай протягом 30 хвилин)."
    )
    
    kb = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="home")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    context.user_data["state"] = AWAITING_FEEDBACK

async def handle_feedback_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = str(update.effective_user.id)
        feedback_text = update.message.text
        
        feedback_id = hashlib.md5(f"{uid}{time.time()}".encode()).hexdigest()[:8]
        create_feedback(feedback_id, uid, update.effective_user.username, update.effective_user.first_name, feedback_text)
        
        kb = [[InlineKeyboardButton("✍️ ВІДПОВІСТИ", callback_data=f"reply_feedback:{feedback_id}")]]
        admin_message = (
            f"💬 <b>Новий відгук #{feedback_id}</b>\n\n"
            f"👤 <b>Від:</b> {update.effective_user.first_name}\n"
            f"📱 <b>Username:</b> @{update.effective_user.username}\n"
            f"🆔 <b>ID:</b> {uid}\n"
            f"📅 <b>Час:</b> {datetime.now(TIMEZONE).strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📝 <b>Повідомлення:</b>\n{feedback_text}\n\n"
            f"⬇️ <i>Натисніть кнопку нижче або зробіть Reply, щоб відповісти</i>"
        )
        
        await context.bot.send_message(
            NOTIFICATION_CHAT_ID,
            admin_message,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML"
        )
        
        await update.message.reply_text(
            "✅ <b>Дякуємо за ваш відгук!</b>\n\n"
            "Ваше повідомлення отримано. Ми розглянемо його найближчим часом і обов'язково відповімо.\n\n"
            "Гарного дня! 🌸",
            parse_mode="HTML"
        )
        
        context.user_data.clear()
    except Exception as e:
        logger.error(f"Помилка в handle_feedback_message: {e}")

async def ref_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        uid = str(update.effective_user.id)
        user = get_user(uid) or {"balance": 0, "ref_count": 0}
        
        ref_link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        potential_earnings = user.get('ref_count', 0) * REFERRAL_REWARD
        
        text = (
            f"👥 <b>Реферальна програма</b>\n\n"
            f"Запрошуйте друзів та отримуйте бонуси! 🎁\n\n"
            f"💰 <b>Бонус за кожного друга:</b> {REFERRAL_REWARD}₴\n"
            f"💎 <b>Мінімальний вивід:</b> 50₴\n\n"
            f"📊 <b>Ваша статистика:</b>\n"
            f"• 👤 Запрошено друзів: <b>{user.get('ref_count', 0)}</b>\n"
            f"• 💰 Потенційний заробіток: <b>{potential_earnings}₴</b>\n"
            f"• 💳 Поточний баланс: <b>{user.get('balance', 0)}₴</b>\n\n"
            f"🔗 <b>Ваше реферальне посилання:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            f"📱 <i>Поділіться цим посиланням з друзями та заробляйте разом з нами!</i>"
        )
        
        kb = [
            [InlineKeyboardButton("💰 ВИВЕСТИ КОШТИ", callback_data="withdraw")],
            [InlineKeyboardButton("🔙 НАЗАД", callback_data="home")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Помилка в ref_menu: {e}")

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    uid = str(update.effective_user.id)
    user = get_user(uid)
    balance = user.get("balance", 0) if user else 0
    
    if balance < 50:
        await query.edit_message_text(
            "❌ <b>Недостатньо коштів</b>\n\n"
            f"Мінімальна сума для виведення: 50₴\n"
            f"Ваш баланс: {balance}₴\n\n"
            f"Запрошуйте більше друзів, щоб накопичити потрібну суму! 🌸",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 НАЗАД", callback_data="ref_menu")
            ]]),
            parse_mode="HTML"
        )
        return
    
    kb = [[InlineKeyboardButton("✅ ПІДТВЕРДИТИ", callback_data=f"confirm_withdraw:{uid}:{balance}")]]
    await context.bot.send_message(
        NOTIFICATION_CHAT_ID,
        f"💰 <b>Запит на виведення коштів</b>\n\n"
        f"👤 <b>Користувач:</b> {update.effective_user.first_name}\n"
        f"📱 <b>Username:</b> @{update.effective_user.username}\n"
        f"🆔 <b>ID:</b> {uid}\n"
        f"💳 <b>Сума:</b> {balance}₴\n"
        f"📅 <b>Час:</b> {datetime.now(TIMEZONE).strftime('%d.%m.%Y %H:%M')}",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )
    
    await query.edit_message_text(
        "✅ <b>Запит відправлено!</b>\n\n"
        "Ваш запит на виведення коштів передано адміністратору.\n"
        "Очікуйте на зарахування протягом 24 годин.\n\n"
        "Дякуємо за співпрацю! 🌸",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 НАЗАД", callback_data="ref_menu")
        ]]),
        parse_mode="HTML"
    )

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tariffs = get_active_tariffs()
    
    kb = []
    for key, tariff in tariffs.items():
        kb.append([InlineKeyboardButton(format_tariff_text(key, tariff), callback_data=f"tar:{key}")])
    
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="home")])
    
    text = "🛍️ <b>Наші тарифи</b>\n\nОберіть відповідний пакет:\n\n"
    for key, tariff in tariffs.items():
        days_text = "безстроково" if tariff.get('days') is None else f"{tariff.get('days')} днів"
        text += f"{tariff.get('emoji', '📦')} <b>{tariff.get('name')}</b> — {tariff.get('price')}₴ ({days_text})\n"
    
    text += "\nПісля вибору тарифу вам потрібно буде ввести:\n"
    text += "• 📝 ПІБ (українською)\n"
    text += "• 📅 Дату народження\n"
    text += "• 👤 Стать\n"
    text += "• 🎟️ Промокод (якщо є)\n"
    text += "• 📸 Фото 3x4\n\n"
    text += "Тисніть на кнопку з потрібним тарифом 👇"
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def select_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tariff_key = query.data.split(":")[1]
    tariffs = get_active_tariffs()
    
    if tariff_key in tariffs:
        tariff = tariffs[tariff_key]
        context.user_data["tariff"] = tariff_key
        context.user_data["tariff_price"] = tariff["price"]
        context.user_data["tariff_text"] = format_tariff_text(tariff_key, tariff)
        context.user_data["state"] = AWAITING_FIO
        
        await query.edit_message_text(
            f"{tariff.get('emoji', '📦')} <b>Ви обрали тариф:</b> {tariff.get('name')} — {tariff.get('price')}₴\n\n"
            f"✍️ <b>Введіть ваше ПІБ</b>\n"
            f"(українською мовою, наприклад: Іванов Іван Іванович)\n\n"
            f"📝 <i>Будь ласка, перевірте правильність написання</i>",
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text("❌ <b>Тариф не знайдено</b>", parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Перевіряємо чи це відповідь в групі сповіщень
        if update.effective_chat.id == NOTIFICATION_CHAT_ID and update.message.reply_to_message:
            await handle_admin_reply(update, context)
            return

        state = context.user_data.get("state")
        
        # Адмін-функції (додавання тарифів)
        if state in [AWAITING_NEW_TARIFF_NAME, AWAITING_NEW_TARIFF_PRICE, AWAITING_NEW_TARIFF_DAYS]:
            await handle_new_tariff_input(update, context)
            return
        
        # Адмін-функції (додавання промокодів)
        if state in [AWAITING_NEW_PROMOCODE_NAME, AWAITING_NEW_PROMOCODE_TYPE, 
                     AWAITING_NEW_PROMOCODE_VALUE, AWAITING_NEW_PROMOCODE_LIMIT]:
            await handle_new_promo_input(update, context)
            return
        
        # Розсилка
        if state == AWAITING_BROADCAST_MESSAGE:
            await handle_broadcast_message(update, context)
            return
        
        # Зворотній зв'язок
        if state == AWAITING_FEEDBACK:
            await handle_feedback_message(update, context)
            return
        
        # Основний діалог замовлення
        if state == AWAITING_FIO:
            fio = update.message.text.strip()
            if len(fio.split()) < 2:
                await update.message.reply_text(
                    "❌ <b>Помилка</b>\n\nБудь ласка, введіть повне ПІБ (мінімум 2 слова).\nНаприклад: Іванов Іван Іванович",
                    parse_mode="HTML"
                )
                return
            
            context.user_data["fio"] = fio
            context.user_data["state"] = AWAITING_DOB
            await update.message.reply_text(
                "📅 <b>Дата народження</b>\n\nВведіть дату у форматі: <b>ДД.ММ.РРРР</b>\nНаприклад: 01.01.1990\n\n<i>Переконайтеся, що дата введена правильно</i>",
                parse_mode="HTML"
            )
            
        elif state == AWAITING_DOB:
            dob = update.message.text.strip()
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', dob):
                await update.message.reply_text(
                    "❌ <b>Неправильний формат</b>\n\nВикористовуйте формат: <b>ДД.ММ.РРРР</b>\nНаприклад: 01.01.1990",
                    parse_mode="HTML"
                )
                return
            
            try:
                day, month, year = map(int, dob.split('.'))
                if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2024):
                    raise ValueError
                
                context.user_data["dob"] = dob
                context.user_data["state"] = AWAITING_SEX
                
                kb = [[
                    InlineKeyboardButton("Чоловік ♂️", callback_data="sex:M"),
                    InlineKeyboardButton("Жінка ♀️", callback_data="sex:W")
                ]]
                await update.message.reply_text("👤 <b>Виберіть стать:</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            except:
                await update.message.reply_text("❌ <b>Неправильна дата</b>\n\nБудь ласка, введіть коректну дату народження.", parse_mode="HTML")
        
        elif state == AWAITING_PROMOCODE:
            await handle_promocode_input(update, context)
        
        elif state == AWAITING_PHOTO:
            # Це обробляється через handle_media
            pass
        
        else:
            # Якщо не в діалозі - пересилаємо в групу
            if update.effective_chat.id != NOTIFICATION_CHAT_ID:
                await update.message.forward(NOTIFICATION_CHAT_ID)
                await update.message.reply_text(
                    "💬 <b>Повідомлення передано адміністратору</b>\n\nОчікуйте на відповідь найближчим часом.",
                    parse_mode="HTML"
                )
    except Exception as e:
        logger.error(f"Помилка в handle_message: {e}")

async def select_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data["sex"] = query.data.split(":")[1]
    context.user_data["state"] = AWAITING_PROMOCODE
    
    sex_text = "чоловік" if context.user_data["sex"] == "M" else "жінка"
    
    await query.edit_message_text(
        f"✅ <b>Стать обрано:</b> {sex_text}\n\n"
        f"🎟️ <b>Промокод</b>\n\n"
        f"Якщо у вас є промокод на знижку, введіть його нижче.\n"
        f"Якщо промокоду немає, натисніть кнопку «ПРОПУСТИТИ».\n\n"
        f"<i>Промокод можна використати лише один раз</i>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭️ ПРОПУСТИТИ", callback_data="skip_promo")
        ]]),
        parse_mode="HTML"
    )

async def handle_promocode_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        code = update.message.text.strip().upper()
        
        success, discount_value, message = use_promocode(code, str(update.effective_user.id))
        
        if not success:
            await update.message.reply_text(
                f"{message}\n\n"
                f"🎟️ Спробуйте інший промокод або натисніть «ПРОПУСТИТИ»:",
                parse_mode="HTML"
            )
            return
        
        # Зберігаємо інформацію про промокод
        promo = get_promocode(code)
        final_price = apply_promocode_to_price(context.user_data["tariff_price"], discount_value, promo["discount_type"])
        
        context.user_data["promo_discount"] = discount_value
        context.user_data["promo_type"] = promo["discount_type"]
        context.user_data["promo_code"] = code
        context.user_data["final_price"] = final_price
        context.user_data["state"] = AWAITING_PHOTO
        
        discount_text = f"{discount_value}₴" if promo["discount_type"] == 1 else f"{discount_value}%"
        
        await update.message.reply_text(
            f"{message}\n\n"
            f"📸 <b>Надішліть ваше фото</b>\n\n"
            f"💰 <b>Початкова ціна:</b> {context.user_data['tariff_price']}₴\n"
            f"🎟️ <b>Знижка:</b> {discount_text}\n"
            f"💎 <b>Підсумкова ціна:</b> {final_price}₴\n\n"
            f"Вимоги до фото:\n"
            f"• 📏 Формат 3x4\n"
            f"• 👤 Обличчя має бути добре видно\n"
            f"• 🎨 Бажано на світлому фоні\n\n"
            f"<i>Надішліть фото одним повідомленням</i>",
            parse_mode="HTML"
        )
        
        # Відзначаємо промокод як використаний
        mark_promocode_used(code, str(update.effective_user.id))
        
    except Exception as e:
        logger.error(f"Помилка в handle_promocode_input: {e}")
        await update.message.reply_text("❌ Сталася помилка. Спробуйте ще раз або пропустіть промокод.")

async def skip_promo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["promo_discount"] = 0
    context.user_data["promo_code"] = None
    context.user_data["final_price"] = context.user_data["tariff_price"]
    context.user_data["state"] = AWAITING_PHOTO
    
    await query.edit_message_text(
        f"📸 <b>Надішліть ваше фото</b>\n\n"
        f"💰 <b>Підсумкова ціна:</b> {context.user_data['final_price']}₴\n\n"
        f"Вимоги до фото:\n"
        f"• 📏 Формат 3x4\n"
        f"• 👤 Обличчя має бути добре видно\n"
        f"• 🎨 Бажано на світлому фоні\n\n"
        f"<i>Надішліть фото одним повідомленням</i>",
        parse_mode="HTML"
    )

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = str(update.effective_user.id)
        state = context.user_data.get("state")
        
        if state == AWAITING_PHOTO and update.message.photo:
            await process_order_photo(update, context, uid)
        else:
            await forward_receipt(update, context, uid)
    except Exception as e:
        logger.error(f"Помилка в handle_media: {e}")

async def process_order_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: str):
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        order_id = hashlib.md5(f"{uid}{time.time()}".encode()).hexdigest()[:8]
        context.user_data["order_id"] = order_id
        
        js_content = generate_js_content(context.user_data)
        
        p_io = io.BytesIO(photo_bytes)
        js_io = io.BytesIO(js_content.encode('utf-8'))
        
        p_io.name = f"photo_{order_id}.png"
        js_io.name = f"values_{order_id}.js"
        
        create_order(
            order_id, uid,
            context.user_data.get("tariff"),
            context.user_data.get("fio"),
            context.user_data.get("dob"),
            context.user_data.get("sex"),
            context.user_data.get("tariff_price"),
            context.user_data.get("promo_code"),
            context.user_data.get("promo_discount", 0),
            context.user_data.get("final_price")
        )
        
        await process_referral_bonus(update, context, uid)
        
        kb = [[InlineKeyboardButton("✅ ПІДТВЕРДИТИ", callback_data=f"adm_ok:{uid}:{order_id}")]]
        caption = (
            f"📦 <b>Нове замовлення #{order_id}</b>\n\n"
            f"👤 <b>ID:</b> {uid}\n"
            f"💎 <b>Тариф:</b> {context.user_data.get('tariff_text')}\n"
            f"📝 <b>ПІБ:</b> {context.user_data['fio']}\n"
            f"📅 <b>Дата народження:</b> {context.user_data['dob']}\n"
            f"👤 <b>Стать:</b> {'Чоловік' if context.user_data.get('sex') == 'M' else 'Жінка'}\n"
            f"💰 <b>Сума до сплати:</b> {context.user_data.get('final_price')}₴\n"
        )
        
        if context.user_data.get("promo_code"):
            caption += f"🎟️ <b>Промокод:</b> {context.user_data['promo_code']}\n"
        
        caption += f"⏰ <b>Час:</b> {datetime.now(TIMEZONE).strftime('%d.%m.%Y %H:%M')}"
        
        await context.bot.send_document(
            NOTIFICATION_CHAT_ID,
            p_io,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML"
        )
        
        await context.bot.send_document(NOTIFICATION_CHAT_ID, js_io)
        
        await update.message.reply_text(
            "✅ <b>Дані отримано!</b>\n\n"
            "Дякуємо за замовлення! 🌸\n\n"
            "📌 <b>Що далі?</b>\n"
            "1️⃣ Адміністратор перевірить ваші дані (зазвичай до 10 хвилин)\n"
            "2️⃣ Ви отримаєте реквізити для оплати\n"
            "3️⃣ Після оплати надішліть чек сюди\n"
            "4️⃣ Отримаєте готові файли\n\n"
            "Очікуйте на повідомлення!",
            parse_mode="HTML"
        )
        
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Помилка в process_order_photo: {e}")
        await update.message.reply_text(
            "❌ <b>Помилка при обробці замовлення</b>\n\n"
            "Будь ласка, спробуйте ще раз або зв'яжіться з адміністратором.",
            parse_mode="HTML"
        )

async def forward_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: str):
    try:
        forwarded = await update.message.forward(NOTIFICATION_CHAT_ID)
        
        user_info = (
            f"📑 <b>Чек від користувача</b>\n\n"
            f"👤 <b>ID:</b> {uid}\n"
            f"📱 <b>Username:</b> @{update.effective_user.username}\n"
            f"💫 <b>Ім'я:</b> {update.effective_user.first_name}\n"
            f"📅 <b>Час:</b> {datetime.now(TIMEZONE).strftime('%d.%m.%Y %H:%M')}\n\n"
            f"⬇️ <i>Зробіть Reply на це повідомлення, щоб відповісти</i>"
        )
        
        await context.bot.send_message(
            NOTIFICATION_CHAT_ID,
            user_info,
            reply_to_message_id=forwarded.message_id,
            parse_mode="HTML"
        )
        
        await update.message.reply_text(
            "✅ <b>Чек отримано!</b>\n\n"
            "Дякуємо! Чек передано адміністратору для перевірки.\n"
            "Після підтвердження оплати ви отримаєте готові файли.\n\n"
            "Очікуйте, будь ласка. 🌸",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в forward_receipt: {e}")

async def process_referral_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: str):
    try:
        user = get_user(uid)
        if user and not user.get("has_bought", False):
            ref_by = user.get("referred_by")
            if ref_by:
                ref_user = get_user(ref_by)
                if ref_user:
                    update_user_balance(ref_by, REFERRAL_REWARD)
                    increment_ref_count(ref_by)
                    update_user_bought(uid, context.user_data.get("final_price", 0))
                    
                    try:
                        await context.bot.send_message(
                            ref_by,
                            f"💰 <b>Вітаємо!</b>\n\n"
                            f"Ваш реферал зробив перше замовлення! 🎉\n"
                            f"Вам нараховано <b>{REFERRAL_REWARD}₴</b>\n"
                            f"Поточний баланс: <b>{ref_user.get('balance', 0) + REFERRAL_REWARD}₴</b>\n\n"
                            f"Дякуємо за співпрацю! 🌸",
                            parse_mode="HTML"
                        )
                    except:
                        pass
            else:
                update_user_bought(uid, context.user_data.get("final_price", 0))
    except Exception as e:
        logger.error(f"Помилка в process_referral_bonus: {e}")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reply_msg = update.message.reply_to_message
        text_to_scan = reply_msg.text or reply_msg.caption or ""
        
        found_id = re.search(r"ID:\s*(\d+)", text_to_scan)
        if found_id:
            client_id = found_id.group(1)
            await context.bot.send_message(
                client_id,
                f"💬 <b>Відповідь адміністратора:</b>\n\n{update.message.text}\n\n🌸 Гарного дня!",
                parse_mode="HTML"
            )
            await update.message.reply_text(f"✅ Відповідь надіслано клієнту {client_id}")
        else:
            if "reply_to_user" in context.user_data:
                user_id = context.user_data.get("reply_to_user")
                feedback_id = context.user_data.get("feedback_id")
                
                await context.bot.send_message(
                    user_id,
                    f"💬 <b>Відповідь на ваш відгук:</b>\n\n{update.message.text}\n\nДякуємо за звернення! 🌸",
                    parse_mode="HTML"
                )
                
                update_feedback_status(feedback_id, "replied", update.message.text)
                await update.message.reply_text(f"✅ Відповідь на відгук #{feedback_id} надіслано")
                
                context.user_data.pop("reply_to_user", None)
                context.user_data.pop("feedback_id", None)
            else:
                await update.message.reply_text("❌ Не вдалося знайти ID клієнта")
    except Exception as e:
        logger.error(f"Помилка в handle_admin_reply: {e}")

async def admin_reply_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        feedback_id = query.data.split(":")[1]
        feedback = get_feedback(feedback_id)
        
        if feedback:
            update_feedback_status(feedback_id, "read")
            context.user_data["reply_to_user"] = feedback["user_id"]
            context.user_data["feedback_id"] = feedback_id
            
            await query.edit_message_text(
                f"✍️ <b>Напишіть відповідь користувачу</b>\n\n"
                f"👤 ID: {feedback['user_id']}\n"
                f"📝 Відгук: {feedback['feedback'][:100]}...\n\n"
                f"<i>Введіть текст відповіді:</i>",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Помилка в admin_reply_feedback: {e}")

async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data.split(":")
        if len(data) >= 2:
            uid = data[1]
            order_id = data[2] if len(data) > 2 else "unknown"
            
            update_order_status(order_id, "approved")
            
            payment_text = (
                f"✅ <b>Замовлення #{order_id} підтверджено!</b>\n\n"
                f"💳 <b>Реквізити для оплати:</b>\n"
                f"{PAYMENT_REQUISITES}\n\n"
                f"🔗 <b>Monobank:</b>\n{PAYMENT_LINK}\n\n"
                f"📤 <b>Після оплати:</b>\n"
                f"1️⃣ Зробіть скріншот успішної оплати\n"
                f"2️⃣ Надішліть його в цей чат\n"
                f"3️⃣ Отримайте готові файли\n\n"
                f"Дякуємо, що обираєте нас! 🌸"
            )
            
            await context.bot.send_message(uid, payment_text, parse_mode="HTML")
            await query.edit_message_text(f"✅ Реквізити надіслано клієнту {uid}\n📦 Замовлення #{order_id}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка в admin_approve: {e}")

async def admin_confirm_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data.split(":")
        if len(data) >= 3:
            uid = data[1]
            amount = int(data[2])
            
            update_user_balance(uid, -amount)
            
            await context.bot.send_message(
                uid,
                f"💰 <b>Виведення коштів підтверджено!</b>\n\n"
                f"Сума <b>{amount}₴</b> буде надіслана найближчим часом.\n"
                f"Дякуємо за співпрацю! 🌸",
                parse_mode="HTML"
            )
            
            await query.edit_message_text(f"✅ Виведення {amount}₴ для користувача {uid} підтверджено", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка в admin_confirm_withdraw: {e}")

# -------------------------
# АДМІН-ФУНКЦІЇ
# -------------------------
async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_USER_ID):
        await update.message.reply_text("❌ У вас немає доступу до адмін-панелі")
        return
    
    text = (
        "👑 <b>Адмін-панель</b>\n\n"
        "Ласкаво просимо до панелі керування ботом!\n\n"
        "Виберіть дію:"
    )
    
    kb = [
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 УПРАВЛІННЯ ТАРИФАМИ", callback_data="admin_tariffs")],
        [InlineKeyboardButton("🎟️ ПРОМОКОДИ", callback_data="admin_promocodes")],
        [InlineKeyboardButton("📢 РОЗСИЛКА", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 КОРИСТУВАЧІ", callback_data="admin_users")],
        [InlineKeyboardButton("💬 ВІДГУКИ", callback_data="admin_feedback_list")],
        [InlineKeyboardButton("🔙 ВИЙТИ", callback_data="home")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    text = "👑 <b>Адмін-панель</b>\n\nЛаскаво просимо до панелі керування ботом!\n\nВиберіть дію:"
    kb = [
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 УПРАВЛІННЯ ТАРИФАМИ", callback_data="admin_tariffs")],
        [InlineKeyboardButton("🎟️ ПРОМОКОДИ", callback_data="admin_promocodes")],
        [InlineKeyboardButton("📢 РОЗСИЛКА", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 КОРИСТУВАЧІ", callback_data="admin_users")],
        [InlineKeyboardButton("💬 ВІДГУКИ", callback_data="admin_feedback_list")],
        [InlineKeyboardButton("🔙 ВИЙТИ", callback_data="home")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    users = db_fetch_all("SELECT user_id, balance, has_bought, blocked FROM users")
    orders = db_fetch_all("SELECT status, final_price FROM orders")
    feedbacks = db_fetch_all("SELECT status FROM feedback")
    
    total_users = len(users)
    active_users = sum(1 for u in users if not u[3])
    total_balance = sum(u[1] for u in users)
    total_orders = len(orders)
    completed_orders = sum(1 for o in orders if o[0] == "approved")
    total_revenue = sum(o[1] for o in orders if o[0] == "approved")
    total_feedbacks = len(feedbacks)
    new_feedbacks = sum(1 for f in feedbacks if f[0] == "new")
    
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Користувачі:</b>\n"
        f"• Всього: {total_users}\n"
        f"• Активних: {active_users}\n\n"
        f"📦 <b>Замовлення:</b>\n"
        f"• Всього: {total_orders}\n"
        f"• Виконано: {completed_orders}\n\n"
        f"💰 <b>Фінанси:</b>\n"
        f"• Загальний баланс: {total_balance}₴\n"
        f"• Загальний дохід: {total_revenue}₴\n\n"
        f"💬 <b>Відгуки:</b>\n"
        f"• Всього: {total_feedbacks}\n"
        f"• Нові: {new_feedbacks}"
    )
    
    kb = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_tariffs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    tariffs = load_tariffs()
    
    text = "💰 <b>Управління тарифами</b>\n\n"
    kb = []
    
    for key, tariff in tariffs.items():
        status = "✅" if tariff.get("active", True) else "❌"
        text += f"{status} {tariff.get('emoji', '📦')} <b>{tariff.get('name')}</b> — {tariff.get('price')}₴\n"
        # Замініть блок коду на цей:
    # Замініть блок коду на цей:
    days_val = tariff.get('days')
    duration_str = "Назавжди" if days_val is None else f"{days_val} днів"
    text += f"    └ Термін: {duration_str}\n"
    kb.append([
            InlineKeyboardButton(f"{'✅' if tariff.get('active') else '❌'} {tariff.get('name')}", callback_data=f"tariff_toggle:{key}"),
            InlineKeyboardButton("✏️ Ціна", callback_data=f"tariff_edit_price:{key}"),
            InlineKeyboardButton("📝 Назва", callback_data=f"tariff_edit_name:{key}")
        ])
    
    kb.append([InlineKeyboardButton("➕ ДОДАТИ ТАРИФ", callback_data="tariff_add")])
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_promocodes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    promocodes = get_all_promocodes()
    
    text = "🎟️ <b>Управління промокодами</b>\n\n"
    
    if not promocodes:
        text += "Немає промокодів\n\n"
    else:
        for promo in promocodes:
            status = "✅" if promo["active"] else "❌"
            type_text = "фіксована" if promo["discount_type"] == 1 else "відсоток"
            limit_text = "безліміт" if promo["usage_limit"] == 0 else f"{promo['used_count']}/{promo['usage_limit']}"
            text += f"{status} <b>{promo['code']}</b>\n"
            text += f"   └ Знижка: {promo['discount_value']}{'₴' if promo['discount_type'] == 1 else '%'} ({type_text})\n"
            text += f"   └ Використань: {limit_text}\n"
    
    kb = [
        [InlineKeyboardButton("➕ ДОДАТИ ПРОМОКОД", callback_data="promo_add")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_promo_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    context.user_data["state"] = AWAITING_NEW_PROMOCODE_NAME
    context.user_data["adding_promo"] = True
    
    await query.edit_message_text(
        "➕ <b>Додавання промокоду</b>\n\n"
        "Крок 1/4: Введіть назву промокоду\n"
        "(лише латиниця та цифри, наприклад: SUMMER2024)",
        parse_mode="HTML"
    )

async def admin_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    text = (
        "📢 <b>Розсилка повідомлень</b>\n\n"
        "Ви можете надіслати повідомлення всім користувачам бота.\n\n"
        "✍️ Напишіть текст повідомлення для розсилки:\n\n"
        "<i>Підтримується HTML-форматування</i>"
    )
    
    kb = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    context.user_data["state"] = AWAITING_BROADCAST_MESSAGE

async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    users = db_fetch_all("SELECT user_id, first_name, username, balance, ref_count, has_bought, joined_date FROM users ORDER BY joined_date DESC LIMIT 20")
    
    text = "👥 <b>Останні користувачі:</b>\n\n"
    for u in users:
        status = "💰" if u[5] else "🆕"
        text += f"{status} <b>{u[1] or 'No name'}</b>\n"
        text += f"   └ ID: {u[0]}\n"
        text += f"   └ Баланс: {u[3]}₴\n"
        text += f"   └ Запрошено: {u[4]}\n"
        text += f"   └ Дата: {u[6][:10]}\n\n"
    
    kb = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_feedback_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    feedbacks = db_fetch_all("SELECT feedback_id, user_id, first_name, username, feedback, created_at, status FROM feedback ORDER BY created_at DESC LIMIT 10")
    
    if not feedbacks:
        await query.edit_message_text("📭 <b>Немає відгуків</b>", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")
        ]]), parse_mode="HTML")
        return
    
    text = "📋 <b>Останні відгуки:</b>\n\n"
    kb = []
    
    for f in feedbacks:
        status = "🟢" if f[6] == "new" else "🔵"
        text += f"{status} <b>Відгук #{f[0]}</b>\n"
        text += f"   👤 {f[2]} (@{f[3]})\n"
        text += f"   📝 {f[4][:50]}...\n"
        text += f"   📅 {f[5][:16]}\n\n"
        kb.append([InlineKeyboardButton(f"💬 Відповісти на #{f[0]}", callback_data=f"reply_feedback:{f[0]}")])
    
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        broadcast_text = update.message.text
        users = db_fetch_all("SELECT user_id FROM users WHERE blocked = 0")
        
        kb = [
            [
                InlineKeyboardButton("✅ ПІДТВЕРДИТИ", callback_data="broadcast_confirm"),
                InlineKeyboardButton("❌ СКАСУВАТИ", callback_data="admin_panel")
            ]
        ]
        
        context.user_data["broadcast_message"] = broadcast_text
        
        await update.message.reply_text(
            f"📢 <b>Попередній перегляд розсилки:</b>\n\n"
            f"{broadcast_text}\n\n"
            f"👥 <b>Отримають:</b> {len(users)} користувачів\n\n"
            f"Підтвердіть розсилку:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в handle_broadcast_message: {e}")

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    await query.answer()
    broadcast_text = context.user_data.get("broadcast_message")
    
    if not broadcast_text:
        await query.edit_message_text("❌ Помилка: немає тексту для розсилки")
        return
    
    users = db_fetch_all("SELECT user_id FROM users WHERE blocked = 0")
    
    await query.edit_message_text(
        f"📢 <b>Розсилка розпочата</b>\n\n"
        f"Всього користувачів: {len(users)}\n"
        f"⏳ Будь ласка, зачекайте...",
        parse_mode="HTML"
    )
    
    success, failed = 0, 0
    for u in users:
        try:
            await context.bot.send_message(u[0], broadcast_text, parse_mode="HTML")
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
    
    await context.bot.send_message(
        ADMIN_USER_ID,
        f"📢 <b>Розсилка завершена</b>\n\n✅ Успішно: {success}\n❌ Помилок: {failed}",
        parse_mode="HTML"
    )
    context.user_data.clear()

async def handle_new_promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    text = update.message.text.strip()
    
    if state == AWAITING_NEW_PROMOCODE_NAME:
        context.user_data["new_promo_code"] = text.upper()
        context.user_data["state"] = AWAITING_NEW_PROMOCODE_TYPE
        await update.message.reply_text(
            "➕ <b>Крок 2/4:</b>\n\n"
            "Виберіть тип знижки:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Фіксована сума (₴)", callback_data="promo_type:1")],
                [InlineKeyboardButton("📊 Відсоток (%)", callback_data="promo_type:2")]
            ]),
            parse_mode="HTML"
        )
    elif state == AWAITING_NEW_PROMOCODE_VALUE:
        try:
            value = int(text)
            context.user_data["new_promo_value"] = value
            context.user_data["state"] = AWAITING_NEW_PROMOCODE_LIMIT
            await update.message.reply_text(
                "➕ <b>Крок 4/4:</b>\n\n"
                "Введіть ліміт використань (0 - без ліміту):\n"
                "Наприклад: 100",
                parse_mode="HTML"
            )
        except ValueError:
            await update.message.reply_text("❌ Введіть число!", parse_mode="HTML")
    elif state == AWAITING_NEW_PROMOCODE_LIMIT:
        try:
            limit = int(text)
            create_promocode(
                context.user_data["new_promo_code"],
                context.user_data["new_promo_type"],
                context.user_data["new_promo_value"],
                limit
            )
            await update.message.reply_text(
                f"✅ <b>Промокод успішно додано!</b>\n\n"
                f"🎟️ Код: {context.user_data['new_promo_code']}\n"
                f"💸 Знижка: {context.user_data['new_promo_value']}{'₴' if context.user_data['new_promo_type'] == 1 else '%'}\n"
                f"📊 Ліміт: {'безліміт' if limit == 0 else limit}",
                parse_mode="HTML"
            )
            context.user_data.clear()
            kb = [[InlineKeyboardButton("🔙 ДО АДМІН-ПАНЕЛІ", callback_data="admin_panel")]]
            await update.message.reply_text("👑 Оберіть дію:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Введіть число!", parse_mode="HTML")

async def handle_new_tariff_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    text = update.message.text.strip()
    
    if state == AWAITING_NEW_TARIFF_NAME:
        if context.user_data.get("edit_type") == "name":
            tariff_key = context.user_data.get("editing_tariff")
            tariffs = load_tariffs()
            if tariff_key in tariffs:
                tariffs[tariff_key]["name"] = text
                for key, value in tariffs.items():
                    db_execute("UPDATE tariffs SET name = ?, price = ?, days = ?, emoji = ?, active = ? WHERE tariff_key = ?",
                              (value["name"], value["price"], value.get("days"), value["emoji"], 1 if value.get("active", True) else 0, key))
                context.user_data.clear()
                await update.message.reply_text("✅ <b>Назву тарифу змінено!</b>", parse_mode="HTML")
                kb = [[InlineKeyboardButton("🔙 ДО АДМІН-ПАНЕЛІ", callback_data="admin_panel")]]
                await update.message.reply_text("👑 Оберіть дію:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        else:
            context.user_data["new_tariff_name"] = text
            context.user_data["state"] = AWAITING_NEW_TARIFF_PRICE
            await update.message.reply_text("➕ <b>Крок 2/3:</b>\n\nВведіть ціну тарифу (тільки цифри):", parse_mode="HTML")
    elif state == AWAITING_NEW_TARIFF_PRICE:
        try:
            price = int(text)
            if context.user_data.get("edit_type") == "price":
                tariff_key = context.user_data.get("editing_tariff")
                tariffs = load_tariffs()
                if tariff_key in tariffs:
                    tariffs[tariff_key]["price"] = price
                    for key, value in tariffs.items():
                        db_execute("UPDATE tariffs SET name = ?, price = ?, days = ?, emoji = ?, active = ? WHERE tariff_key = ?",
                                  (value["name"], value["price"], value.get("days"), value["emoji"], 1 if value.get("active", True) else 0, key))
                    context.user_data.clear()
                    await update.message.reply_text("✅ <b>Ціну тарифу змінено!</b>", parse_mode="HTML")
                    kb = [[InlineKeyboardButton("🔙 ДО АДМІН-ПАНЕЛІ", callback_data="admin_panel")]]
                    await update.message.reply_text("👑 Оберіть дію:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            else:
                context.user_data["new_tariff_price"] = price
                context.user_data["state"] = AWAITING_NEW_TARIFF_DAYS
                await update.message.reply_text("➕ <b>Крок 3/3:</b>\n\nВведіть кількість днів (0 - назавжди):", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Введіть число!", parse_mode="HTML")
    elif state == AWAITING_NEW_TARIFF_DAYS:
        try:
            days = int(text)
            if days == 0:
                days = None
            
            name = context.user_data["new_tariff_name"]
            price = context.user_data["new_tariff_price"]
            key = name.lower().replace(" ", "_")[:20]
            
            tariffs = load_tariffs()
            base_key = key
            counter = 1
            while key in tariffs:
                key = f"{base_key}_{counter}"
                counter += 1
            
            emojis = ["🌟", "✨", "🎯", "🎨", "🎭", "🎪", "🎫", "🎬"]
            new_emoji = emojis[len(tariffs) % len(emojis)]
            
            add_tariff(key, name, price, days, new_emoji, 1)
            context.user_data.clear()
            
            await update.message.reply_text(
                f"✅ <b>Тариф додано!</b>\n\n{new_emoji} {name} — {price}₴\nТермін: {'Назавжди' if days is None else f'{days} днів'}",
                parse_mode="HTML"
            )
            kb = [[InlineKeyboardButton("🔙 ДО АДМІН-ПАНЕЛІ", callback_data="admin_panel")]]
            await update.message.reply_text("👑 Оберіть дію:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Введіть число!", parse_mode="HTML")

async def admin_tariff_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    tariff_key = query.data.split(":")[1]
    tariffs = load_tariffs()
    if tariff_key in tariffs:
        tariffs[tariff_key]["active"] = not tariffs[tariff_key].get("active", True)
        for key, value in tariffs.items():
            db_execute("UPDATE tariffs SET active = ? WHERE tariff_key = ?", 
                      (1 if value.get("active", True) else 0, key))
        await query.answer(f"Тариф {'увімкнено' if tariffs[tariff_key]['active'] else 'вимкнено'}")
    await admin_tariffs_menu(update, context)

async def admin_tariff_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    tariff_key = query.data.split(":")[1]
    context.user_data["editing_tariff"] = tariff_key
    context.user_data["edit_type"] = "price"
    context.user_data["state"] = AWAITING_NEW_TARIFF_PRICE
    
    await query.edit_message_text(
        f"✏️ <b>Редагування ціни</b>\n\nВведіть нову ціну (тільки цифри):",
        parse_mode="HTML"
    )

async def admin_tariff_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    tariff_key = query.data.split(":")[1]
    context.user_data["editing_tariff"] = tariff_key
    context.user_data["edit_type"] = "name"
    context.user_data["state"] = AWAITING_NEW_TARIFF_NAME
    
    await query.edit_message_text(
        f"✏️ <b>Редагування назви</b>\n\nВведіть нову назву:",
        parse_mode="HTML"
    )

async def admin_tariff_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    context.user_data["state"] = AWAITING_NEW_TARIFF_NAME
    context.user_data["edit_type"] = "new"
    
    await query.edit_message_text(
        "➕ <b>Додавання тарифу</b>\n\n"
        "Крок 1/3: Введіть назву тарифу\n"
        "(наприклад: Преміум 30 днів)",
        parse_mode="HTML"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.error(f"Помилка: {context.error}")
        await context.bot.send_message(
            ADMIN_USER_ID,
            f"❌ <b>Помилка бота</b>\n\n{str(context.error)[:200]}",
            parse_mode="HTML"
        )
    except:
        pass

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "home":
            await start(update, context)
        elif query.data == "ref_menu":
            await ref_menu(update, context)
        elif query.data == "about":
            await about_handler(update, context)
        elif query.data == "withdraw":
            await withdraw_handler(update, context)
        elif query.data == "catalog":
            await show_catalog(update, context)
        elif query.data == "feedback":
            await feedback_handler(update, context)
        elif query.data.startswith("tar:"):
            await select_tariff(update, context)
        elif query.data.startswith("sex:"):
            await select_sex(update, context)
        elif query.data == "skip_promo":
            await skip_promo_handler(update, context)
        elif query.data.startswith("promo_type:"):
            promo_type = int(query.data.split(":")[1])
            context.user_data["new_promo_type"] = promo_type
            context.user_data["state"] = AWAITING_NEW_PROMOCODE_VALUE
            await query.edit_message_text(
                "➕ <b>Крок 3/4:</b>\n\n"
                f"Введіть значення знижки ({'суму в ₴' if promo_type == 1 else 'відсоток'}):\n"
                f"Наприклад: {'50' if promo_type == 1 else '20'}",
                parse_mode="HTML"
            )
        elif query.data == "admin_panel":
            await admin_panel(update, context)
        elif query.data == "admin_stats":
            await admin_stats(update, context)
        elif query.data == "admin_tariffs":
            await admin_tariffs_menu(update, context)
        elif query.data == "admin_promocodes":
            await admin_promocodes_menu(update, context)
        elif query.data == "admin_broadcast":
            await admin_broadcast_menu(update, context)
        elif query.data == "admin_users":
            await admin_users_list(update, context)
        elif query.data == "admin_feedback_list":
            await admin_feedback_list(update, context)
        elif query.data == "promo_add":
            await admin_promo_add_start(update, context)
        elif query.data == "tariff_add":
            await admin_tariff_add_start(update, context)
        elif query.data.startswith("tariff_toggle:"):
            await admin_tariff_toggle(update, context)
        elif query.data.startswith("tariff_edit_price:"):
            await admin_tariff_edit_price(update, context)
        elif query.data.startswith("tariff_edit_name:"):
            await admin_tariff_edit_name(update, context)
        elif query.data.startswith("adm_ok:"):
            await admin_approve(update, context)
        elif query.data.startswith("confirm_withdraw:"):
            await admin_confirm_withdraw(update, context)
        elif query.data.startswith("reply_feedback:"):
            await admin_reply_feedback(update, context)
        elif query.data == "broadcast_confirm":
            await execute_broadcast(update, context)
    except Exception as e:
        logger.error(f"Помилка в button_handler: {e}")

# -------------------------
# ЗАПУСК БОТА
# -------------------------
def main():
    try:
        init_db()
        
        app = Application.builder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", start))
        app.add_handler(CommandHandler("admin", admin_panel_command))
        
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media))
        
        app.add_error_handler(error_handler)
        
        logger.info("🌸 Бот FunsDiia успішно запущено!")
        print("✅ Бот запущено!")
        print(f"👑 Адмін-панель: /admin (тільки для адміна з ID: {ADMIN_USER_ID})")
        print(f"📢 Група сповіщень: {NOTIFICATION_CHAT_ID}")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Критична помилка при запуску: {e}")
        print(f"❌ Критична помилка: {e}")
        raise

if __name__ == "__main__":
    if os.getenv("GITHUB_ACTIONS") == "true":
        import time
        from threading import Thread
        
        def keep_alive():
            while True:
                time.sleep(60)
                logger.info("🌸 Бот працює...")
        
        Thread(target=keep_alive, daemon=True).start()
    
    main()
