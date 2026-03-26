# bot_main.py
import os
import logging
import asyncio
import asyncpg
import hashlib
import time
import random
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID", "5423792783"))
NOTIFY_CHAT = int(os.getenv("NOTIFICATION_CHAT_ID", "-1002003419071"))
BOT_NAME = os.getenv("BOT_USERNAME", "FunsDiia_bot")
DATABASE_URL = os.getenv("DATABASE_URL")

REFERRAL_BONUS = 19
MIN_WITHDRAW = 50
PAYMENT = "💳 Картка: 5355573250476310\n👤 Отримувач: SenseBank"
PAYMENT_LINK = "https://send.monobank.ua/jar/6R3gd9Ew8w"

TARIFFS = {
    "1_day": {"name": "🌙 1 день", "price": 20, "days": 1},
    "30_days": {"name": "📅 30 днів", "price": 70, "days": 30},
    "90_days": {"name": "🌿 90 днів", "price": 150, "days": 90},
    "180_days": {"name": "🌟 180 днів", "price": 190, "days": 180},
    "forever": {"name": "💎 Назавжди", "price": 250, "days": None}
}

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
_pool = None

async def get_db():
    global _pool
    if not _pool:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool

async def init_db():
    pool = await get_db()
    async with pool.acquire() as conn:
        # Таблица пользователей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                username TEXT,
                balance INT DEFAULT 0,
                referrer BIGINT,
                refs INT DEFAULT 0,
                bought BOOL DEFAULT FALSE,
                joined TIMESTAMP,
                tariff TEXT DEFAULT 'free',
                tariff_expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Таблица заказов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                tariff TEXT,
                fio TEXT,
                dob TEXT,
                sex TEXT,
                price INT,
                promo_code TEXT,
                discount INT DEFAULT 0,
                final_price INT,
                created_at TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Таблица промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount_type TEXT,
                discount_value INT,
                max_uses INT DEFAULT 1,
                used INT DEFAULT 0,
                active BOOL DEFAULT TRUE,
                expires_at TIMESTAMP
            )
        ''')
        
        # Таблица активаций промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_promos (
                user_id BIGINT REFERENCES users(user_id),
                promo_code TEXT REFERENCES promocodes(code),
                used_at TIMESTAMP,
                PRIMARY KEY (user_id, promo_code)
            )
        ''')
        
        # Добавляем тестовый промокод
        await conn.execute('''
            INSERT INTO promocodes (code, discount_type, discount_value, max_uses, active) 
            VALUES ('WELCOME10', 'percentage', 10, 100, true)
            ON CONFLICT (code) DO NOTHING
        ''')
        
    logger.info("✅ База данных готова")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_tariff(key, data):
    days = "безстроково" if data['days'] is None else f"{data['days']} дн."
    return f"{data['name']} — {data['price']}₴ ({days})"

def validate_dob(text):
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
        return False
    try:
        day, month, year = map(int, text.split('.'))
        return 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2024
    except:
        return False

def calc_discount(price, value, type_):
    if type_ == 'fixed':
        return max(0, price - value)
    return int(price * (100 - value) / 100)

def gen_id():
    return hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:8]

# ========== ЗАПРОСЫ К БАЗЕ ==========
async def get_user(uid):
    pool = await get_db()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", uid)

async def create_user(uid, name, username, referrer=None):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, name, username, referrer, joined, tariff) VALUES ($1, $2, $3, $4, $5, 'free')",
            uid, name, username, referrer, datetime.now()
        )

async def update_balance(uid, amount):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, uid)

async def add_ref_bonus(uid):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET refs = refs + 1 WHERE user_id = $1", uid)
        await conn.execute("UPDATE users SET balance = balance + 19 WHERE user_id = $1", uid)

async def buy_tariff(uid, tariff, days):
    pool = await get_db()
    async with pool.acquire() as conn:
        expires = datetime.now() + timedelta(days=days) if days else None
        await conn.execute(
            "UPDATE users SET tariff = $1, tariff_expires_at = $2, bought = TRUE WHERE user_id = $3",
            tariff, expires, uid
        )

async def is_tariff_active(uid):
    user = await get_user(uid)
    if not user or user['tariff'] == 'free':
        return False
    if user['tariff_expires_at'] is None:
        return True
    return user['tariff_expires_at'] > datetime.now()

async def create_order(oid, uid, tariff, fio, dob, sex, price, promo, discount, final):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO orders (order_id, user_id, tariff, fio, dob, sex, price, promo_code, discount, final_price, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
            oid, uid, tariff, fio, dob, sex, price, promo, discount, final, datetime.now()
        )

async def update_order(oid, status):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE orders SET status = $1 WHERE order_id = $2", status, oid)

async def get_promo(code):
    pool = await get_db()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM promocodes WHERE code = $1 AND active = TRUE", code.upper())

async def use_promo(code, uid):
    promo = await get_promo(code)
    if not promo:
        return False, "❌ Промокод не знайдено"
    if promo['expires_at'] and promo['expires_at'] < datetime.now():
        return False, "❌ Термін дії минув"
    if promo['max_uses'] > 0 and promo['used'] >= promo['max_uses']:
        return False, "❌ Ліміт вичерпано"
    
    pool = await get_db()
    async with pool.acquire() as conn:
        used = await conn.fetchrow("SELECT 1 FROM user_promos WHERE user_id = $1 AND promo_code = $2", uid, code)
        if used:
            return False, "❌ Ви вже використовували цей промокод"
        
        await conn.execute("UPDATE promocodes SET used = used + 1 WHERE code = $1", code)
        await conn.execute("INSERT INTO user_promos (user_id, promo_code, used_at) VALUES ($1, $2, $3)", uid, code, datetime.now())
    
    return True, f"✅ Промокод {code} активовано!", promo

async def fetch_all(query, *args):
    pool = await get_db()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    username = update.effective_user.username
    
    user = await get_user(uid)
    
    ref = None
    if ctx.args and ctx.args[0].isdigit() and int(ctx.args[0]) != uid:
        ref = int(ctx.args[0])
    
    if not user:
        await create_user(uid, name, username, ref)
        if ref:
            try:
                await ctx.bot.send_message(ref, f"👋 {name} приєднався за вашим посиланням!")
            except:
                pass
    
    if user and user['tariff'] != 'free' and not await is_tariff_active(uid):
        await update.message.reply_text(
            "⏰ Ваш тариф закінчився. Оформіть нове замовлення.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍️ КАТАЛОГ", callback_data="catalog")
            ]])
        )
        return
    
    buttons = [
        [InlineKeyboardButton("🛍️ КАТАЛОГ", callback_data="catalog")],
        [InlineKeyboardButton("👥 РЕФЕРАЛИ", callback_data="ref")],
        [InlineKeyboardButton("ℹ️ ПРО НАС", callback_data="about")]
    ]
    if uid == ADMIN_ID:
        buttons.append([InlineKeyboardButton("👑 АДМІН", callback_data="admin")])
    
    await update.message.reply_text(
        f"🌸 Вітаю, {name}!\n\nFunsDiia — генерація документів.\nОберіть розділ 👇",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def catalog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    buttons = []
    for key, t in TARIFFS.items():
        buttons.append([InlineKeyboardButton(format_tariff(key, t), callback_data=f"tariff:{key}")])
    buttons.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="home")])
    
    text = "🛍️ Наші тарифи:\n\n" + "\n".join([format_tariff(k, t) for k, t in TARIFFS.items()])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def about(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "ℹ️ Про бота\n\nГенерація документів.\nШвидко, якісно.\n\n📞 @admin",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 НАЗАД", callback_data="home")
        ]])
    )

async def referral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    uid = update.effective_user.id
    user = await get_user(uid)
    link = f"https://t.me/{BOT_NAME}?start={uid}"
    
    text = (
        f"👥 Реферальна програма\n\n"
        f"💰 Бонус: {REFERRAL_BONUS}₴ за друга\n"
        f"📊 Запрошено: {user['refs'] if user else 0}\n"
        f"💳 Баланс: {user['balance'] if user else 0}₴\n\n"
        f"🔗 Ваше посилання:\n<code>{link}</code>"
    )
    
    buttons = [
        [InlineKeyboardButton("💰 ВИВЕСТИ", callback_data="withdraw")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="home")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user or user['balance'] < MIN_WITHDRAW:
        await query.edit_message_text(
            f"❌ Мінімум {MIN_WITHDRAW}₴. Ваш баланс: {user['balance'] if user else 0}₴",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 НАЗАД", callback_data="ref")
            ]])
        )
        return
    
    await ctx.bot.send_message(
        NOTIFY_CHAT,
        f"💰 Запит на виведення\n👤 {update.effective_user.first_name}\n🆔 {uid}\n💳 {user['balance']}₴",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ ПІДТВЕРДИТИ", callback_data=f"withdraw_ok:{uid}:{user['balance']}")
        ]])
    )
    
    await query.edit_message_text(
        "✅ Запит відправлено!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 НАЗАД", callback_data="ref")
        ]])
    )

async def select_tariff(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tariff_key = query.data.split(":")[1]
    
    if tariff_key not in TARIFFS:
        await query.answer("Тариф не знайдено")
        return
    
    ctx.user_data['tariff'] = tariff_key
    ctx.user_data['price'] = TARIFFS[tariff_key]['price']
    ctx.user_data['days'] = TARIFFS[tariff_key]['days']
    ctx.user_data['state'] = 'fio'
    
    await query.edit_message_text("📝 Введіть ПІБ (українською)\nНаприклад: Іванов Іван Іванович")

async def process_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = ctx.user_data.get('state')
    
    if state == 'fio':
        fio = update.message.text.strip()
        if len(fio.split()) < 2:
            await update.message.reply_text("❌ Введіть повне ПІБ")
            return
        ctx.user_data['fio'] = fio
        ctx.user_data['state'] = 'dob'
        await update.message.reply_text("📅 Введіть дату народження (ДД.ММ.РРРР)")
    
    elif state == 'dob':
        if not validate_dob(update.message.text):
            await update.message.reply_text("❌ Невірний формат. Приклад: 01.01.1990")
            return
        ctx.user_data['dob'] = update.message.text
        ctx.user_data['state'] = 'sex'
        
        buttons = [[
            InlineKeyboardButton("Чоловік ♂️", callback_data="sex:M"),
            InlineKeyboardButton("Жінка ♀️", callback_data="sex:W")
        ]]
        await update.message.reply_text("👤 Виберіть стать:", reply_markup=InlineKeyboardMarkup(buttons))
    
    elif state == 'promo':
        code = update.message.text.strip().upper()
        success, msg, promo = await use_promo(code, uid)
        
        if not success:
            await update.message.reply_text(f"{msg}\nСпробуйте інший:")
            return
        
        ctx.user_data['promo'] = code
        ctx.user_data['discount'] = promo['discount_value']
        ctx.user_data['final'] = calc_discount(ctx.user_data['price'], promo['discount_value'], promo['discount_type'])
        ctx.user_data['state'] = 'photo'
        
        await update.message.reply_text(
            f"{msg}\n\n📸 Надішліть фото 3x4\n💰 {ctx.user_data['price']}₴ → {ctx.user_data['final']}₴"
        )
    
    elif state == 'photo' and update.message.photo:
        try:
            photo = await update.message.photo[-1].get_file()
            photo_bytes = await photo.download_as_bytearray()
            order_id = gen_id()
            
            await create_order(
                order_id, uid, ctx.user_data['tariff'], ctx.user_data['fio'],
                ctx.user_data['dob'], ctx.user_data['sex'], ctx.user_data['price'],
                ctx.user_data.get('promo'), ctx.user_data.get('discount', 0), ctx.user_data['final']
            )
            
            user = await get_user(uid)
            if user and not user['bought'] and user['referrer']:
                await add_ref_bonus(user['referrer'])
            
            from io import BytesIO
            await ctx.bot.send_photo(
                NOTIFY_CHAT,
                BytesIO(photo_bytes),
                caption=f"📦 Замовлення #{order_id}\n👤 {uid}\n💎 {ctx.user_data['tariff']}\n💰 {ctx.user_data['final']}₴",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ ПІДТВЕРДИТИ", callback_data=f"approve:{uid}:{order_id}")
                ]])
            )
            
            js = f"// Generated\nvar fio = \"{ctx.user_data['fio']}\";\nvar birth = \"{ctx.user_data['dob']}\";"
            await ctx.bot.send_document(NOTIFY_CHAT, BytesIO(js.encode()), filename=f"{order_id}.js")
            
            await update.message.reply_text("✅ Замовлення прийнято! Очікуйте підтвердження.")
            ctx.user_data.clear()
            
        except Exception as e:
            logger.error(f"Order error: {e}")
            await update.message.reply_text("❌ Помилка. Спробуйте ще раз")

async def handle_sex(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ctx.user_data['sex'] = query.data.split(":")[1]
    ctx.user_data['state'] = 'promo'
    
    await query.edit_message_text(
        "🎟️ Введіть промокод або натисніть ПРОПУСТИТИ",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭️ ПРОПУСТИТИ", callback_data="skip_promo")
        ]])
    )

async def skip_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ctx.user_data['final'] = ctx.user_data['price']
    ctx.user_data['state'] = 'photo'
    await query.edit_message_text("📸 Надішліть фото 3x4")

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    buttons = [
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton("🔙 ВИЙТИ", callback_data="home")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text("👑 Адмін-панель", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text("👑 Адмін-панель", reply_markup=InlineKeyboardMarkup(buttons))

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Доступ заборонено")
        return
    
    users = await fetch_all("SELECT user_id FROM users")
    orders = await fetch_all("SELECT status FROM orders")
    
    text = f"📊 Статистика\n\n👥 Користувачів: {len(users)}\n📦 Замовлень: {len(orders)}"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 НАЗАД", callback_data="admin")
    ]]))

async def approve_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, uid, order_id = query.data.split(":")
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Доступ заборонено")
        return
    
    tariff = TARIFFS.get('30_days', {})
    await buy_tariff(int(uid), '30_days', tariff.get('days'))
    await update_order(order_id, 'approved')
    
    await ctx.bot.send_message(int(uid), f"✅ Замовлення підтверджено!\n\n💳 Реквізити:\n{PAYMENT}\n\n🔗 {PAYMENT_LINK}")
    await query.edit_message_text(f"✅ Замовлення #{order_id} підтверджено")

async def home(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start(update, ctx)

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    handlers = {
        "home": home, "catalog": catalog, "about": about, "ref": referral,
        "withdraw": withdraw, "admin": admin_panel, "stats": stats,
        "skip_promo": skip_promo
    }
    
    if data.startswith("tariff:"):
        await select_tariff(update, ctx)
    elif data.startswith("sex:"):
        await handle_sex(update, ctx)
    elif data.startswith("approve:"):
        await approve_order(update, ctx)
    elif data in handlers:
        await handlers[data](update, ctx)
    else:
        await update.callback_query.answer()

async def error_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {ctx.error}")

# ========== ЗАПУСК ==========
async def main_async():
    await init_db()
    logger.info("🚀 Бот запущен")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, process_order))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_order))
    app.add_error_handler(error_handler)
    
    await app.run_polling()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
