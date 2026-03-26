# handlers/order.py
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.settings import STATE, NOTIFY_CHAT, PAYMENT, PAYMENT_LINK
from database.queries import *
from utils.helpers import *
from utils.generators import *
import logging

logger = logging.getLogger(__name__)

# ========== SELECT TARIFF ==========
async def select_tariff(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tariff_key = query.data.split(":")[1]
    
    if tariff_key not in TARIFFS:
        await query.answer("Тариф не знайдено")
        return
    
    ctx.user_data['tariff'] = tariff_key
    ctx.user_data['price'] = TARIFFS[tariff_key]['price']
    ctx.user_data['days'] = TARIFFS[tariff_key]['days']
    ctx.user_data['state'] = STATE['FIO']
    
    await query.edit_message_text(
        f"📝 Введіть ПІБ (українською)\n"
        f"Наприклад: Іванов Іван Іванович"
    )

# ========== PROCESS ORDER ==========
async def process_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = ctx.user_data.get('state')
    
    if state == STATE['FIO']:
        fio = update.message.text.strip()
        if len(fio.split()) < 2:
            await update.message.reply_text("❌ Введіть повне ПІБ")
            return
        ctx.user_data['fio'] = fio
        ctx.user_data['state'] = STATE['DOB']
        await update.message.reply_text("📅 Введіть дату народження (ДД.ММ.РРРР)")
    
    elif state == STATE['DOB']:
        if not validate_dob(update.message.text):
            await update.message.reply_text("❌ Невірний формат. Приклад: 01.01.1990")
            return
        ctx.user_data['dob'] = update.message.text
        ctx.user_data['state'] = STATE['SEX']
        
        buttons = [[
            InlineKeyboardButton("Чоловік ♂️", callback_data="sex:M"),
            InlineKeyboardButton("Жінка ♀️", callback_data="sex:W")
        ]]
        await update.message.reply_text("👤 Виберіть стать:", reply_markup=InlineKeyboardMarkup(buttons))
    
    elif state == STATE['PROMO']:
        await handle_promo(update, ctx)
    
    elif state == STATE['PHOTO']:
        await handle_photo(update, ctx, uid)

async def handle_sex(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ctx.user_data['sex'] = query.data.split(":")[1]
    ctx.user_data['state'] = STATE['PROMO']
    
    await query.edit_message_text(
        "🎟️ Введіть промокод або натисніть ПРОПУСТИТИ",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭️ ПРОПУСТИТИ", callback_data="skip_promo")
        ]])
    )

async def handle_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    uid = update.effective_user.id
    
    success, msg, promo = await use_promo(code, uid)
    
    if not success:
        await update.message.reply_text(f"{msg}\nСпробуйте інший:")
        return
    
    ctx.user_data['promo'] = code
    ctx.user_data['discount'] = promo['value']
    ctx.user_data['final'] = calculate_discount(ctx.user_data['price'], promo['value'], promo['type'])
    ctx.user_data['state'] = STATE['PHOTO']
    
    await update.message.reply_text(
        f"{msg}\n\n"
        f"📸 Надішліть фото 3x4\n"
        f"💰 Ціна: {ctx.user_data['price']}₴ → {ctx.user_data['final']}₴"
    )

async def skip_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ctx.user_data['final'] = ctx.user_data['price']
    ctx.user_data['state'] = STATE['PHOTO']
    
    await query.edit_message_text("📸 Надішліть фото 3x4")

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE, uid: int):
    try:
        photo = await update.message.photo[-1].get_file()
        photo_bytes = await photo.download_as_bytearray()
        
        order_id = generate_id()
        js = generate_js(ctx.user_data)
        
        # Сохраняем заказ
        await create_order(
            order_id, uid,
            ctx.user_data['tariff'],
            ctx.user_data['fio'],
            ctx.user_data['dob'],
            ctx.user_data['sex'],
            ctx.user_data['price'],
            ctx.user_data.get('promo'),
            ctx.user_data.get('discount', 0),
            ctx.user_data['final']
        )
        
        # Бонус рефералу
        user = await get_user(uid)
        if user and not user['bought'] and user['referrer']:
            await add_ref_bonus(user['referrer'])
        
        # Отправляем админу
        await ctx.bot.send_photo(
            NOTIFY_CHAT,
            io.BytesIO(photo_bytes),
            caption=(
                f"📦 Замовлення #{order_id}\n"
                f"👤 {uid}\n"
                f"💎 {ctx.user_data['tariff']}\n"
                f"💰 {ctx.user_data['final']}₴"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ ПІДТВЕРДИТИ", callback_data=f"approve:{uid}:{order_id}")
            ]])
        )
        
        await ctx.bot.send_document(NOTIFY_CHAT, io.BytesIO(js.encode()), filename=f"{order_id}.js")
        
        await update.message.reply_text(
            "✅ Замовлення прийнято!\n"
            "Очікуйте підтвердження адміністратора."
        )
        
        ctx.user_data.clear()
        
    except Exception as e:
        logger.error(f"Order error: {e}")
        await update.message.reply_text("❌ Помилка. Спробуйте ще раз")
