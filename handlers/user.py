# handlers/user.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.settings import ADMIN_ID, REFERRAL_BONUS, MIN_WITHDRAW
from database.queries import *
from utils.helpers import *
from utils.generators import *
import logging

logger = logging.getLogger(__name__)

# ========== START ==========
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    username = update.effective_user.username
    
    user = await get_user(uid)
    
    # Реферальная ссылка
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
    
    # Проверка тарифа
    if user and user['tariff'] != 'free' and not await is_tariff_active(uid):
        await update.message.reply_text(
            "⏰ Ваш тариф закінчився. Оформіть нове замовлення.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍️ КАТАЛОГ", callback_data="catalog")
            ]])
        )
        return
    
    # Кнопки
    buttons = [
        [InlineKeyboardButton("🛍️ КАТАЛОГ", callback_data="catalog")],
        [InlineKeyboardButton("👥 РЕФЕРАЛИ", callback_data="ref")],
        [InlineKeyboardButton("💬 ВІДГУК", callback_data="feedback")],
        [InlineKeyboardButton("ℹ️ ПРО НАС", callback_data="about")]
    ]
    
    if uid == ADMIN_ID:
        buttons.append([InlineKeyboardButton("👑 АДМІН", callback_data="admin")])
    
    await update.message.reply_text(
        f"🌸 Вітаю, {name}!\n\n"
        "FunsDiia — генерація документів.\n"
        "Оберіть розділ 👇",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ========== CATALOG ==========
async def catalog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    buttons = []
    for key, t in TARIFFS.items():
        buttons.append([InlineKeyboardButton(format_tariff(key, t), callback_data=f"tariff:{key}")])
    buttons.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="home")])
    
    await query.edit_message_text(
        "🛍️ Наші тарифи:\n\n"
        + "\n".join([format_tariff(k, t) for k, t in TARIFFS.items()]),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ========== REFERRAL ==========
async def referral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    uid = update.effective_user.id
    user = await get_user(uid)
    link = f"https://t.me/{BOT_NAME}?start={uid}"
    
    text = (
        f"👥 Реферальна програма\n\n"
        f"💰 Бонус: {REFERRAL_BONUS}₴ за друга\n"
        f"📊 Запрошено: {user['refs']}\n"
        f"💳 Баланс: {user['balance']}₴\n\n"
        f"🔗 Ваше посилання:\n<code>{link}</code>"
    )
    
    buttons = [
        [InlineKeyboardButton("💰 ВИВЕСТИ", callback_data="withdraw")],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data="home")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# ========== WITHDRAW ==========
async def withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if user['balance'] < MIN_WITHDRAW:
        await query.edit_message_text(
            f"❌ Мінімум {MIN_WITHDRAW}₴. Ваш баланс: {user['balance']}₴",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 НАЗАД", callback_data="ref")
            ]])
        )
        return
    
    await ctx.bot.send_message(
        NOTIFY_CHAT,
        f"💰 Запит на виведення\n"
        f"👤 {update.effective_user.first_name}\n"
        f"🆔 {uid}\n"
        f"💳 {user['balance']}₴",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ ПІДТВЕРДИТИ", callback_data=f"withdraw_ok:{uid}:{user['balance']}")
        ]])
    )
    
    await query.edit_message_text(
        "✅ Запит відправлено! Очікуйте.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 НАЗАД", callback_data="ref")
        ]])
    )
