# utils.py
import random
from datetime import datetime, timedelta
from config import TIMEZONE

def load_tariffs_sync() -> dict:
    """Синхронная загрузка тарифов"""
    return {
        "1_day": {"name": "🌙 1 день", "price": 20, "days": 1, "emoji": "🌙", "active": True},
        "30_days": {"name": "📅 30 днів", "price": 70, "days": 30, "emoji": "📅", "active": True},
        "90_days": {"name": "🌿 90 днів", "price": 150, "days": 90, "emoji": "🌿", "active": True},
        "180_days": {"name": "🌟 180 днів", "price": 190, "days": 180, "emoji": "🌟", "active": True},
        "forever": {"name": "💎 Назавжди", "price": 250, "days": None, "emoji": "💎", "active": True}
    }

def format_tariff_text(tariff_key: str, tariff_data: dict) -> str:
    return f"{tariff_data.get('emoji', '📦')} {tariff_data.get('name', tariff_key)} — {tariff_data.get('price', 0)}₴"

def apply_promocode_to_price(price: int, discount_value: int, discount_type: int) -> int:
    if discount_type == 1 or discount_type == "fixed":
        return max(0, price - discount_value)
    else:
        return int(price * (100 - discount_value) / 100)

def generate_js_content(data: dict) -> str:
    """Генерация JS контента (ваша существующая функция)"""
    try:
        rnokpp = "".join(str(random.randint(0, 9)) for _ in range(10))
        pass_num = "".join(str(random.randint(0, 9)) for _ in range(9))
        year = random.randint(1990, 2010)
        uznr = f"{year}0128-{random.randint(10000, 99999)}"
        prava_num = f"AUX{random.randint(100000, 999999)}"
        zagran_num = f"FX{random.randint(100000, 999999)}"
        
        districts = ["Харківський", "Чугуївський", "Ізюмський", "Лозівський", "Богодухівський"]
        cities = ["м. Харків", "м. Чугуїв", "м. Мерефа", "м. Люботин", "смт Пісочин"]
        streets = ["Гарібальді", "Сумська", "Пушкінська", "Полтавський Шлях", "пр. Науки", "Клочківська"]
        
        district = random.choice(districts)
        city = random.choice(cities)
        street = random.choice(streets)
        building = random.randint(1, 150)
        apartment = random.randint(1, 250)
        bank_addr = f"Харківська область, {district} район {city}, вул. {street}, буд. {building}, кв. {apartment}"

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