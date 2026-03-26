# handlers/admin.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.settings import ADMIN_ID, NOTIFY_CHAT
from database.queries import *
import logging

logger = logging.getLogger(__name__)

# ========== ADMIN PANEL ==========
async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    buttons = [
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton("🎟️ ПРОМОКОДИ", callback_data="promos")],
        [InlineKeyboardButton("📢 РОЗСИЛКА", callback_data="broadcast")],
        [InlineKeyboardButton("👥 КОРИСТУВАЧІ", callback_data="users")],
        [InlineKeyboardButton("🔙 ВИЙТИ", callback_data="home")]
    ]
    
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(
            "👑 Адмін-панель",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await update.message.reply_text(
            "👑 Адмін-панель",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ========== STATS ==========
async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Доступ заборонено")
        return
    
    users = await fetch("SELECT id, balance, bought, blocked FROM users")
    orders = await fetch("SELECT status, final FROM orders")
    
    text = (
        f"📊 Статистика\n\n"
        f"👥 Користувачі: {len(users)}\n"
        f"💰 Баланс: {sum(u['balance'] for u in users)}₴\n"
        f"📦 Замовлень: {len(orders)}\n"
        f"✅ Виконано: {sum(1 for o in orders if o['status'] == 'approved')}\n"
        f"💵 Дохід: {sum(o['final'] for o in orders if o['status'] == 'approved')}₴"
    )
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 НАЗАД", callback_data="admin")
        ]])
    )

# ========== APPROVE ORDER ==========
async def approve_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, uid, order_id = query.data.split(":")
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Доступ заборонено")
        return
    
    order = await fetchone("SELECT * FROM orders WHERE id = $1", order_id)
    if not order:
        await query.answer("Замовлення не знайдено")
        return
    
    # Активируем тариф
    tariff = TARIFFS.get(order['tariff'], {})
    await buy_tariff(int(uid), order['tariff'], tariff.get('days'))
    await update_order(order_id, 'approved')
    
    # Отправляем реквизиты
    await ctx.bot.send_message(
        int(uid),
        f"✅ Замовлення підтверджено!\n\n"
        f"💳 Реквізити:\n{PAYMENT}\n\n"
        f"🔗 Monobank:\n{PAYMENT_LINK}\n\n"
        f"Після оплати надішліть чек."
    )
    
    await query.edit_message_text(f"✅ Замовлення #{order_id} підтверджено")
