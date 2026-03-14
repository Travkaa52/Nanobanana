import os
import json
import logging
import io
import random
import re
import pytz
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)

# -------------------------
# НАСТРОЙКИ
# -------------------------
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "-1002003419071"))
TIMEZONE = pytz.timezone("Europe/Kyiv")
BOT_USERNAME = "FunsDiia_bot" # ЗАМЕНИ НА ЮЗЕРНЕЙМ СВОЕГО БОТА

USERS_FILE = "users_data.json"
REFERRAL_REWARD = 19

PAYMENT_REQUISITES = "💳 Картка:5355573250476310 \n👤 SenseBank."
PAYMENT_LINK = "https://send.monobank.ua/jar/6R3gd9Ew8w"

AWAITING_FIO, AWAITING_DOB, AWAITING_SEX, AWAITING_PHOTO = "FIO", "DOB", "SEX", "PHOTO"

TARIFFS = {
    "1_day": {"text": "1 день — 20₴"},
    "30_days": {"text": "30 днів — 70₴"},
    "90_days": {"text": "90 днів — 150₴"},
    "180_days": {"text": "180 днів — 190₴"},
    "forever": {"text": "Назавжди — 250₴"}
}

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# -------------------------
# БД ТА ГЕНЕРАЦИЯ
# -------------------------
def load_db(filename):
    if not os.path.exists(filename): return {}
    try:
        with open(filename, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_db(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_js_content(data: dict) -> str:
    rnokpp = "".join([str(random.randint(0, 9)) for _ in range(10)])
    pass_num = "".join([str(random.randint(0, 9)) for _ in range(9)])
    uznr = f"{random.randint(1990, 2010)}0128-{random.randint(10000, 99999)}"
    prava_num = f"AUX{random.randint(100000, 999999)}"
    zagran_num = f"FX{random.randint(100000, 999999)}"
    
    districts = ["Харківський", "Чугуївський", "Ізюмський", "Лозівський", "Богодухівський"]
    cities = ["м. Харків", "м. Чугуїв", "м. Мерефа", "м. Люботин", "смт Пісочин"]
    streets = ["Гарібальді", "Сумська", "Пушкінська", "Полтавський Шлях", "пр. Науки", "Клочківська"]
    bank_addr = f"Харківська область, {random.choice(districts)} район {random.choice(cities)} вул.{random.choice(streets)},буд. {random.randint(1,150)}, кв. {random.randint(1,250)}"

    u_sex = data.get("sex", "Ж")
    sex_ua, sex_en = ("Ч", "M") if u_sex == "M" else ("Ж", "W")
    date_now = datetime.now(TIMEZONE).strftime("%d.%m.%Y")
    date_out = (datetime.now(TIMEZONE) + timedelta(days=3650)).strftime("%d.%m.%Y")

    return f"""// values.js

// Основные данные 
var fio                = "{data.get('fio', '')}";
var fio_en             = "{data.get('dob', '')}";
var birth              = "{data.get('dob', '')}"; //дата рождения
var date_give          = "{date_now}"; //Дата видачи
var date_out           = "{date_out}"; // действителен до
var organ              = "0512"; //орган что выдал документ
var rnokpp             = "{rnokpp}"; //ИНН
var uznr               = "{uznr}"; //Номер записи
var pass_number        = "{pass_num}"; //номер паспорта

var registeredOn       = "20.09.1999"; //дата регистрации

// Прописка
var legalAdress        = "Харківська область"; //Место проживание
var live               = "Харківська область"; //Место рождение 
var bank_adress        = "{bank_addr}"; //Место жительства указано в банке

var sex                = "{sex_ua}";
var sex_en             = "{sex_en}";

// Данные для Прав
var rights_categories = "A, B"; //Категории
var prava_number      = "{prava_num}"; // номер прав
var prava_date_give   = "01.04.2022"; //Дата выдачи Прав
var prava_date_out    = "01.04.2032"; //Действителен ДО
var pravaOrgan        = "0512"; //орган который выдал

var university        = "ХНУ имени Каразина"; // Університет
var fakultet          = "Физико-технический"; // Факультет
var stepen_dip        = "Магістра";
var univer_dip        = "ХНУ имени Каразина";
var dayout_dip        = "01.07.2023";
var special_dip       = "Прикладная математика";
var number_dip        = "MT-545678";
var form              = "Очная";

// заграник
var zagran_number     = "{zagran_num}"; //номер загран
var dateGiveZ         = "18.11.2019"; //выдан загран
var dateOutZ          = "18.11.2029"; //коньчаеться загран

var student_number    = "2022154258";
var student_date_give = "01.09.2021";
var student_date_out  = "30.06.2025";

// Включение/выключение документов
var isRightsEnabled   = true;
var isZagranEnabled   = true;
var isDiplomaEnabled  = true;
var isStudyEnabled    = true;

// Пути к нужным фото
var photo_passport = "1.png"; 
var photo_rights   = "1.png"; 
var photo_students = "1.png"; 
var photo_zagran   = "1.png"; 

var signPng           = "sign.png"; //подпись
"""

# -------------------------
# ОБРАБОТЧИКИ
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    users = load_db(USERS_FILE)
    
    if uid not in users:
        # Просто сохраняем, кто привел, деньги НЕ начисляем
        ref_by = context.args[0] if context.args and context.args[0] != uid else None
        users[uid] = {
            "username": update.effective_user.username, 
            "balance": 0, 
            "referred_by": ref_by, 
            "ref_count": 0,
            "has_bought": False # Флаг первой покупки
        }
        save_db(USERS_FILE, users)

    kb = [[InlineKeyboardButton("🛍️ КАТАЛОГ ТАРИФІВ", callback_data="catalog")],
          [InlineKeyboardButton("👥 РЕФЕРАЛЬНА СИСТЕМА", callback_data="ref_menu")]]
    
    await update.effective_message.reply_text(
        "🚀 <b>Вітаємо у FunsDiia!</b>\nОбирай послугу або заробляй на рефералах.", 
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode="HTML"
    )

async def ref_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    users = load_db(USERS_FILE)
    u = users.get(uid, {"balance": 0, "ref_count": 0})
    
    ref_link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    text = (f"👥 <b>Реферальна програма</b>\n\n"
            f"💰 Бонус за покупку друга: <b>{REFERRAL_REWARD}₴</b>\n\n"
            f"📊 Статистика:\n— Запрошено: {u['ref_count']}\n"
            f"— Ваш баланс: <b>{u['balance']}₴</b>\n\n"
            f"🔗 Ваше посилання:\n<code>{ref_link}</code>")
    
    kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="home")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "home":
        await start(update, context)
    elif query.data == "ref_menu":
        await ref_menu(update, context)
    elif query.data == "catalog":
        kb = [[InlineKeyboardButton(v["text"], callback_data=f"tar:{k}")] for k, v in TARIFFS.items()]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="home")])
        await query.edit_message_text("💳 <b>Оберіть тариф:</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    elif query.data.startswith("tar:"):
        context.user_data["tariff"] = TARIFFS[query.data.split(":")[1]]["text"]
        context.user_data["state"] = AWAITING_FIO
        await query.edit_message_text("✍️ Введіть ваше <b>ПІБ</b>:")
    elif query.data.startswith("sex:"):
        context.user_data["sex"] = query.data.split(":")[1]
        context.user_data["state"] = AWAITING_PHOTO
        await query.edit_message_text("📸 Надішліть ваше <b>фото</b> (3х4):")
    elif query.data.startswith("adm_ok:"):
        uid = query.data.split(":")[1]
        await context.bot.send_message(uid, f"✅ Дані прийнято!\n\nРеквізити:\n<code>{PAYMENT_REQUISITES}</code>\n\nНадішліть чек сюди.", parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # REPLY АДМИНА
    if update.effective_chat.id == ADMIN_CHAT_ID and update.message.reply_to_message:
        reply_msg = update.message.reply_to_message
        text_to_scan = reply_msg.text or reply_msg.caption or ""
        found_id = re.search(r"ID:\s*(\d+)", text_to_scan)
        if found_id:
            client_id = found_id.group(1)
            await context.bot.send_message(client_id, f"🚀 <b>Доступ активовано!</b>\n\n{update.message.text}", parse_mode="HTML")
            await update.message.reply_text(f"✅ Отправлено клиенту {client_id}")
            return

    state = context.user_data.get("state")
    if state == AWAITING_FIO:
        context.user_data["fio"] = update.message.text
        context.user_data["state"] = AWAITING_DOB
        await update.message.reply_text("📅 Дата народження:")
    elif state == AWAITING_DOB:
        context.user_data["dob"] = update.message.text
        context.user_data["state"] = AWAITING_SEX
        kb = [[InlineKeyboardButton("Чоловік ♂️", callback_data="sex:M"), InlineKeyboardButton("Жінка ♀️", callback_data="sex:W")]]
        await update.message.reply_text("👤 Стать:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    uid = str(update.effective_user.id)

    if state == AWAITING_PHOTO and update.message.photo:
        # НАЧИСЛЕНИЕ БОНУСА ПРИГЛАСИВШЕМУ ПРИ ПЕРВОЙ ПОКУПКЕ
        users = load_db(USERS_FILE)
        if uid in users and not users[uid].get("has_bought", False):
            ref_by = users[uid].get("referred_by")
            if ref_by and ref_by in users:
                users[ref_by]["balance"] += REFERRAL_REWARD
                users[ref_by]["ref_count"] += 1
                try:
                    await context.bot.send_message(ref_by, f"💰 <b>Ваш реферал зробив замовлення!</b>\nВам нараховано <b>{REFERRAL_REWARD}₴</b>", parse_mode="HTML")
                except: pass
            users[uid]["has_bought"] = True # Помечаем, что покупка была
            save_db(USERS_FILE, users)

        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        p_io, js_io = io.BytesIO(photo_bytes), io.BytesIO(generate_js_content(context.user_data).encode())
        p_io.name, js_io.name = "1.png", "values.js"

        kb = [[InlineKeyboardButton("✅ Дати реквізити", callback_data=f"adm_ok:{uid}")]]
        caption = f"📦 <b>Замовлення ID: {uid}</b>\nТариф: {context.user_data.get('tariff')}\nПІБ: {context.user_data['fio']}"
        
        await context.bot.send_document(ADMIN_CHAT_ID, p_io, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        await context.bot.send_document(ADMIN_CHAT_ID, js_io)
        await update.message.reply_text("⏳ Очікуйте.")
        context.user_data.clear()
    else:
        await update.message.forward(ADMIN_CHAT_ID)
        await context.bot.send_message(ADMIN_CHAT_ID, f"📑 <b>Чек від ID: {uid}</b>\nЗробіть Reply посиланням.")
        await update.message.reply_text("⏳ Чек отримано.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media))
    app.run_polling()

if __name__ == "__main__":
    main()
