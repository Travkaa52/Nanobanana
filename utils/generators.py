# utils/generators.py
import random
from datetime import datetime, timedelta
from config.settings import TIMEZONE

def generate_rnokpp():
    return ''.join(str(random.randint(0, 9)) for _ in range(10))

def generate_passport():
    return ''.join(str(random.randint(0, 9)) for _ in range(9))

def generate_uznr():
    return f"{random.randint(1990, 2010)}0128-{random.randint(10000, 99999)}"

def generate_prava():
    return f"AUX{random.randint(100000, 999999)}"

def generate_zagran():
    return f"FX{random.randint(100000, 999999)}"

def generate_address():
    districts = ["Харківський", "Чугуївський", "Ізюмський"]
    cities = ["м. Харків", "м. Чугуїв", "м. Мерефа"]
    streets = ["Гарібальді", "Сумська", "Пушкінська"]
    return f"Харківська обл., {random.choice(districts)} р-н {random.choice(cities)}, вул. {random.choice(streets)}"

def generate_js(data: dict) -> str:
    """Сгенерировать JS файл"""
    date = datetime.now(TIMEZONE)
    return f"""// Generated: {date.strftime("%d.%m.%Y")}
var fio = "{data['fio']}";
var birth = "{data['dob']}";
var sex = "{'Ч' if data['sex'] == 'M' else 'Ж'}";
var rnokpp = "{generate_rnokpp()}";
var pass_num = "{generate_passport()}";
var uznr = "{generate_uznr()}";
var prava = "{generate_prava()}";
var zagran = "{generate_zagran()}";
var address = "{generate_address()}";
"""
