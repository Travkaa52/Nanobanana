# handlers.py
import os
import logging
import io
import re
import time
import hashlib
import asyncio
from datetime import datetime
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Импортируем функции из db
from db import (
    get_user, create_user, update_user_balance, update_user_bought,
    increment_ref_count, buy_tariff, get_user_tariff_info, is_tariff_active,
    create_promocode, get_promocode, check_promocode_valid, apply_promocode,
    create_order_async, update_order_status_async, get_order_async,
    fetch_query, execute_query
)

# Импортируем конфигурацию
from config import (
    ADMIN_USER_ID, NOTIFICATION_CHAT_ID, TIMEZONE, BOT_USERNAME,
    REFERRAL_REWARD, PAYMENT_REQUISITES, PAYMENT_LINK,
    AWAITING_FIO, AWAITING_DOB, AWAITING_SEX, AWAITING_PROMOCODE,
    AWAITING_PHOTO, AWAITING_FEEDBACK, AWAITING_NEW_TARIFF_NAME,
    AWAITING_NEW_TARIFF_PRICE, AWAITING_NEW_TARIFF_DAYS,
    AWAITING_BROADCAST_MESSAGE, AWAITING_NEW_PROMOCODE_NAME,
    AWAITING_NEW_PROMOCODE_TYPE, AWAITING_NEW_PROMOCODE_VALUE,
    AWAITING_NEW_PROMOCODE_LIMIT
)

# Импортируем вспомогательные функции
from utils import (
    load_tariffs_sync, format_tariff_text, apply_promocode_to_price,
    generate_js_content
)

logger = logging.getLogger(__name__)

# -------------------------
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = str(update.effective_user.id)
        
        # Проверяем активность тарифа
        is_active = await is_tariff_active(uid)
        if not is_active:
            user = await get_user(uid)
            if user and user.get("has_bought", False):
                text = (
                    f"⏰ <b>Ваш тариф закінчився</b>\n\n"
                    f"🌸 Шановний(а) {update.effective_user.first_name},\n\n"
                    f"Термін дії вашого тарифу минув. Щоб продовжити користуватися ботом, будь ласка, оформіть нове замовлення.\n\n"
                    f"🛍️ <b>Перейти до каталогу тарифів:</b>\n\n"
                    f"Чекаємо на вас! 🌸"
                )
                kb = [[InlineKeyboardButton("🛍️ КАТАЛОГ ТАРИФІВ", callback_data="catalog")]]
                await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
                return
        
        user = await get_user(uid)
        
        ref_by = None
        if context.args and context.args[0]:
            potential_ref = context.args[0]
            if potential_ref != uid:
                ref_by = potential_ref
        
        if not user:
            await create_user(uid, update.effective_user.username, update.effective_user.first_name, ref_by)
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
        
        # Показываем информацию о тарифе
        tariff_info = await get_user_tariff_info(uid)
        
        kb = [
            [InlineKeyboardButton("🛍️ КАТАЛОГ ТАРИФІВ", callback_data="catalog")],
            [InlineKeyboardButton("👥 РЕФЕРАЛЬНА ПРОГРАМА", callback_data="ref_menu")],
            [InlineKeyboardButton("💬 ЗВОРОТНИЙ ЗВ'ЯЗОК", callback_data="feedback")],
            [InlineKeyboardButton("ℹ️ ПРО НАС", callback_data="about")]
        ]
        
        # Добавляем информацию о тарифе в меню
        if tariff_info["is_active"]:
            if tariff_info["days_left"] == -1:
                tariff_text = "💎 Безстроковий тариф"
            else:
                tariff_text = f"📅 Активний тариф: {tariff_info['days_left']} дн."
            kb.insert(0, [InlineKeyboardButton(tariff_text, callback_data="tariff_info")])
        
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

async def tariff_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик информации о тарифе"""
    query = update.callback_query
    await query.answer()
    
    uid = str(update.effective_user.id)
    tariff_info = await get_user_tariff_info(uid)
    
    if not tariff_info["is_active"]:
        text = (
            "❌ <b>У вас немає активного тарифу</b>\n\n"
            "Оформіть замовлення в каталозі, щоб отримати доступ до послуг бота."
        )
        kb = [[InlineKeyboardButton("🛍️ КАТАЛОГ", callback_data="catalog")]]
    else:
        if tariff_info["days_left"] == -1:
            text = (
                f"💎 <b>Ваш тариф</b>\n\n"
                f"📦 <b>Тариф:</b> {tariff_info['tariff']}\n"
                f"♾️ <b>Термін дії:</b> Безстроково\n"
                f"📅 <b>Активовано:</b> {tariff_info['purchase_date'].strftime('%d.%m.%Y') if tariff_info['purchase_date'] else 'невідомо'}\n\n"
                f"Дякуємо, що обираєте FunsDiia! 🌸"
            )
        else:
            text = (
                f"📅 <b>Ваш тариф</b>\n\n"
                f"📦 <b>Тариф:</b> {tariff_info['tariff']}\n"
                f"📅 <b>Активовано:</b> {tariff_info['purchase_date'].strftime('%d.%m.%Y') if tariff_info['purchase_date'] else 'невідомо'}\n"
                f"⏰ <b>Закінчується:</b> {tariff_info['expires_at'].strftime('%d.%m.%Y')}\n"
                f"📊 <b>Залишилось днів:</b> {tariff_info['days_left']}\n\n"
            )
            
            if tariff_info["days_left"] <= 3:
                text += "⚠️ <b>Увага!</b> Ваш тариф скоро закінчиться! Рекомендуємо продовжити його заздалегідь.\n\n"
        
        text += "Дякуємо, що обираєте FunsDiia! 🌸"
        kb = [[InlineKeyboardButton("🛍️ ПРОДОВЖИТИ ТАРИФ", callback_data="catalog")]]
    
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="home")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

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
        
        # Сохраняем отзыв в базу данных (используем прямые запросы)
        query = """
            INSERT INTO feedback (feedback_id, user_id, username, first_name, feedback, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        await execute_query(query, feedback_id, int(uid), update.effective_user.username, 
                           update.effective_user.first_name, feedback_text, datetime.now())
        
        kb = [[InlineKeyboardButton("✍️ ВІДПОВІСТИ", callback_data=f"reply_feedback:{feedback_id}")]]
        admin_message = (
            f"💬 <b>Новий відгук #{feedback_id}</b>\n\n"
            f"👤 <b>Від:</b> {update.effective_user.first_name}\n"
            f"📱 <b>Username:</b> @{update.effective_user.username}\n"
            f"🆔 <b>ID:</b> {uid}\n"
            f"📅 <b>Час:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
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
        user = await get_user(uid) or {"balance": 0, "ref_count": 0}
        
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
    user = await get_user(uid)
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
        f"📅 <b>Час:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}",
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
    tariffs = load_tariffs_sync()
    active_tariffs = {k: v for k, v in tariffs.items() if v.get("active", True)}
    
    uid = str(update.effective_user.id)
    has_active_tariff = await is_tariff_active(uid)
    
    kb = []
    for key, tariff in active_tariffs.items():
        if has_active_tariff and tariff.get('days') is not None:
            button_text = f"🔄 {format_tariff_text(key, tariff)} (ПРОДОВЖЕННЯ)"
        else:
            button_text = format_tariff_text(key, tariff)
        kb.append([InlineKeyboardButton(button_text, callback_data=f"tar:{key}")])
    
    kb.append([InlineKeyboardButton("🔙 НАЗАД", callback_data="home")])
    
    text = "🛍️ <b>Наші тарифи</b>\n\nОберіть відповідний пакет:\n\n"
    for key, tariff in active_tariffs.items():
        days_text = "безстроково" if tariff.get('days') is None else f"{tariff.get('days')} днів"
        text += f"{tariff.get('emoji', '📦')} <b>{tariff.get('name')}</b> — {tariff.get('price')}₴ ({days_text})\n"
    
    if has_active_tariff:
        text += "\n🔄 <b>Для продовження тарифу</b> оберіть будь-який тариф з позначкою (ПРОДОВЖЕННЯ).\n"
    
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
    tariffs = load_tariffs_sync()
    active_tariffs = {k: v for k, v in tariffs.items() if v.get("active", True)}
    
    if tariff_key in active_tariffs:
        tariff = active_tariffs[tariff_key]
        context.user_data["tariff"] = tariff_key
        context.user_data["tariff_price"] = tariff["price"]
        context.user_data["tariff_text"] = format_tariff_text(tariff_key, tariff)
        context.user_data["tariff_days"] = tariff.get("days")
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
        if update.effective_chat.id == NOTIFICATION_CHAT_ID and update.message.reply_to_message:
            await handle_admin_reply(update, context)
            return

        state = context.user_data.get("state")
        
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
            pass
        
        elif state == AWAITING_FEEDBACK:
            await handle_feedback_message(update, context)
        
        elif state == AWAITING_BROADCAST_MESSAGE:
            await handle_broadcast_message(update, context)
        
        elif state in [AWAITING_NEW_TARIFF_NAME, AWAITING_NEW_TARIFF_PRICE, AWAITING_NEW_TARIFF_DAYS]:
            await handle_new_tariff_input(update, context)
        
        elif state in [AWAITING_NEW_PROMOCODE_NAME, AWAITING_NEW_PROMOCODE_TYPE, 
                       AWAITING_NEW_PROMOCODE_VALUE, AWAITING_NEW_PROMOCODE_LIMIT]:
            await handle_new_promo_input(update, context)
        
        else:
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
        uid = str(update.effective_user.id)
        
        success, message, result = await apply_promocode(code, uid)
        
        if not success:
            await update.message.reply_text(
                f"{message}\n\n"
                f"🎟️ Спробуйте інший промокод або натисніть «ПРОПУСТИТИ»:",
                parse_mode="HTML"
            )
            return
        
        if result.get("free_tariff"):
            await update.message.reply_text(
                f"{message}\n\n"
                f"🎉 <b>Вітаємо!</b> Ви отримали безкоштовний тариф <b>«{result['tariff']}»</b>!\n\n"
                f"Тепер ви можете користуватися ботом без обмежень! 🌸",
                parse_mode="HTML"
            )
            context.user_data.clear()
            return
        
        final_price = apply_promocode_to_price(
            context.user_data["tariff_price"], 
            result["discount_value"], 
            1 if result["discount_type"] == "fixed" else 2
        )
        
        context.user_data["promo_discount"] = result["discount_value"]
        context.user_data["promo_type"] = 1 if result["discount_type"] == "fixed" else 2
        context.user_data["promo_code"] = code
        context.user_data["final_price"] = final_price
        context.user_data["state"] = AWAITING_PHOTO
        
        discount_text = f"{result['discount_value']}₴" if result["discount_type"] == "fixed" else f"{result['discount_value']}%"
        
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
        
        # Создаем заказ в PostgreSQL
        await create_order_async(
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
        
        caption += f"⏰ <b>Час:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
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
            f"📅 <b>Час:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
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
        user = await get_user(uid)
        if user and not user.get("has_bought", False):
            ref_by = user.get("referred_by")
            if ref_by:
                ref_user = await get_user(str(ref_by))
                if ref_user:
                    await update_user_balance(str(ref_by), REFERRAL_REWARD)
                    await increment_ref_count(str(ref_by))
                    await update_user_bought(uid, context.user_data.get("final_price", 0))
                    
                    try:
                        await context.bot.send_message(
                            str(ref_by),
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
                await update_user_bought(uid, context.user_data.get("final_price", 0))
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
                
                # Обновляем статус отзыва
                query = "UPDATE feedback SET status = 'replied', replied_at = $1, admin_reply = $2 WHERE feedback_id = $3"
                await execute_query(query, datetime.now(), update.message.text, feedback_id)
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
        
        # Получаем отзыв из базы
        row = await fetch_query("SELECT user_id, feedback FROM feedback WHERE feedback_id = $1", feedback_id)
        if row:
            context.user_data["reply_to_user"] = row[0][0]
            context.user_data["feedback_id"] = feedback_id
            
            await query.edit_message_text(
                f"✍️ <b>Напишіть відповідь користувачу</b>\n\n"
                f"👤 ID: {row[0][0]}\n"
                f"📝 Відгук: {row[0][1][:100]}...\n\n"
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
            
            # Получаем заказ и активируем тариф
            order = await get_order_async(order_id)
            if order:
                tariff_key = order["tariff"]
                tariff_days = None
                # Получаем длительность тарифа из конфига
                tariffs = load_tariffs_sync()
                if tariff_key in tariffs:
                    tariff_days = tariffs[tariff_key].get("days")
                
                # Активируем тариф для пользователя
                await buy_tariff(uid, tariff_key, tariff_days)
                logger.info(f"Тариф {tariff_key} активирован для {uid}")
            
            await update_order_status_async(order_id, "approved")
            
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
            
            await update_user_balance(uid, -amount)
            
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
    
    users = await fetch_query("SELECT user_id, balance, has_bought, blocked FROM users")
    orders = await fetch_query("SELECT status, final_price FROM orders")
    
    total_users = len(users)
    active_users = sum(1 for u in users if not u[3])
    total_balance = sum(u[1] for u in users)
    total_orders = len(orders)
    completed_orders = sum(1 for o in orders if o[0] == "approved")
    total_revenue = sum(o[1] for o in orders if o[0] == "approved")
    
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
        f"• Загальний дохід: {total_revenue}₴\n"
    )
    
    kb = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_tariffs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    tariffs = load_tariffs_sync()
    
    text = "💰 <b>Управління тарифами</b>\n\n"
    kb = []
    
    for key, tariff in tariffs.items():
        status = "✅" if tariff.get("active", True) else "❌"
        days_val = tariff.get('days')
        duration_str = "Назавжди" if days_val is None else f"{days_val} днів"
        text += f"{status} {tariff.get('emoji', '📦')} <b>{tariff.get('name')}</b> — {tariff.get('price')}₴ ({duration_str})\n"
        kb.append([
            InlineKeyboardButton(f"{'✅' if tariff.get('active') else '❌'} {tariff.get('name')[:15]}", callback_data=f"tariff_toggle:{key}"),
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
    
    promocodes = await fetch_query("""
        SELECT code, discount_type, discount_value, max_activations, used_count, is_active, created_at
        FROM promocodes ORDER BY created_at DESC
    """)
    
    text = "🎟️ <b>Управління промокодами</b>\n\n"
    
    if not promocodes:
        text += "Немає промокодів\n\n"
    else:
        for promo in promocodes:
            status = "✅" if promo[5] else "❌"
            type_text = "фіксована" if promo[1] == "fixed" else "відсоток"
            limit_text = "безліміт" if promo[3] == 0 else f"{promo[4]}/{promo[3]}"
            text += f"{status} <b>{promo[0]}</b>\n"
            text += f"   └ Знижка: {promo[2]}{'₴' if promo[1] == 'fixed' else '%'} ({type_text})\n"
            text += f"   └ Використань: {limit_text}\n\n"
    
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
    
    users = await fetch_query("""
        SELECT user_id, first_name, username, balance, ref_count, has_bought, joined_date 
        FROM users ORDER BY joined_date DESC LIMIT 20
    """)
    
    text = "👥 <b>Останні користувачі:</b>\n\n"
    for u in users:
        status = "💰" if u[5] else "🆕"
        text += f"{status} <b>{u[1] or 'No name'}</b>\n"
        text += f"   └ ID: {u[0]}\n"
        text += f"   └ Баланс: {u[3]}₴\n"
        text += f"   └ Запрошено: {u[4]}\n"
        text += f"   └ Дата: {u[6][:10] if u[6] else 'невідомо'}\n\n"
    
    kb = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_feedback_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    feedbacks = await fetch_query("""
        SELECT feedback_id, user_id, first_name, username, feedback, created_at, status 
        FROM feedback ORDER BY created_at DESC LIMIT 10
    """)
    
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
        users = await fetch_query("SELECT user_id FROM users WHERE blocked = FALSE")
        
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
    
    users = await fetch_query("SELECT user_id FROM users WHERE blocked = FALSE")
    
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
            await asyncio.sleep(0.05)
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
                [InlineKeyboardButton("💰 Фіксована сума (₴)", callback_data="promo_type:fixed")],
                [InlineKeyboardButton("📊 Відсоток (%)", callback_data="promo_type:percentage")],
                [InlineKeyboardButton("🎁 Безкоштовний тариф", callback_data="promo_type:free")]
            ]),
            parse_mode="HTML"
        )
    elif state == AWAITING_NEW_PROMOCODE_TYPE:
        # Это приходит через callback, а не через текст
        pass
    elif state == AWAITING_NEW_PROMOCODE_VALUE:
        try:
            value = int(text)
            context.user_data["new_promo_value"] = value
            context.user_data["state"] = AWAITING_NEW_PROMOCODE_LIMIT
            await update.message.reply_text(
                "➕ <b>Крок 4/4:</b>\n\n"
                "Введіть ліміт активацій (0 - без ліміту):\n"
                "Наприклад: 100",
                parse_mode="HTML"
            )
        except ValueError:
            await update.message.reply_text("❌ Введіть число!", parse_mode="HTML")
    elif state == AWAITING_NEW_PROMOCODE_LIMIT:
        try:
            limit = int(text)
            code = context.user_data["new_promo_code"]
            promo_type = context.user_data.get("new_promo_type", "fixed")
            value = context.user_data.get("new_promo_value", 0)
            
            await create_promocode(code, promo_type, value, limit, None, None)
            
            await update.message.reply_text(
                f"✅ <b>Промокод успішно додано!</b>\n\n"
                f"🎟️ Код: {code}\n"
                f"💸 Знижка: {value}{'₴' if promo_type == 'fixed' else '%'}\n"
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
        context.user_data["new_tariff_name"] = text
        context.user_data["state"] = AWAITING_NEW_TARIFF_PRICE
        await update.message.reply_text(
            "➕ <b>Крок 2/3:</b>\n\nВведіть ціну тарифу (тільки цифри):",
            parse_mode="HTML"
        )
    elif state == AWAITING_NEW_TARIFF_PRICE:
        try:
            price = int(text)
            context.user_data["new_tariff_price"] = price
            context.user_data["state"] = AWAITING_NEW_TARIFF_DAYS
            await update.message.reply_text(
                "➕ <b>Крок 3/3:</b>\n\nВведіть кількість днів (0 - назавжди):",
                parse_mode="HTML"
            )
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
            
            tariffs = load_tariffs_sync()
            base_key = key
            counter = 1
            while key in tariffs:
                key = f"{base_key}_{counter}"
                counter += 1
            
            emojis = ["🌟", "✨", "🎯", "🎨", "🎭", "🎪", "🎫", "🎬"]
            new_emoji = emojis[len(tariffs) % len(emojis)]
            
            # Сохраняем тариф в базу
            query = """
                INSERT INTO tariffs (tariff_key, name, price, days, emoji, active)
                VALUES ($1, $2, $3, $4, $5, $6)
            """
            await execute_query(query, key, name, price, days, new_emoji, True)
            
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
    # Временно показываем уведомление
    await query.answer(f"Функція в розробці", show_alert=True)

async def admin_tariff_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    await query.answer("Функція в розробці", show_alert=True)

async def admin_tariff_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_USER_ID):
        await query.answer("❌ У вас немає доступу", show_alert=True)
        return
    
    await query.answer("Функція в розробці", show_alert=True)

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
        elif query.data == "tariff_info":
            await tariff_info_handler(update, context)
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
            promo_type = query.data.split(":")[1]
            context.user_data["new_promo_type"] = promo_type
            if promo_type == "free":
                context.user_data["state"] = AWAITING_NEW_PROMOCODE_VALUE
                await query.edit_message_text(
                    "➕ <b>Крок 3/4:</b>\n\n"
                    "Введіть назву безкоштовного тарифу:",
                    parse_mode="HTML"
                )
            else:
                context.user_data["state"] = AWAITING_NEW_PROMOCODE_VALUE
                await query.edit_message_text(
                    "➕ <b>Крок 3/4:</b>\n\n"
                    f"Введіть значення знижки ({'суму в ₴' if promo_type == 'fixed' else 'відсоток'}):\n"
                    f"Наприклад: {'50' if promo_type == 'fixed' else '20'}",
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