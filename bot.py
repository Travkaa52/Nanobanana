import os, asyncio, logging, random, json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()

# --- КОНСТАНТЫ ИГРЫ ---
STATS_FILE = "ultimate_war_stats.json"
EPOCHS = {
    1: {"name": "🛡 Эпоха Ополчения", "bonus": 1.0, "req": 0},
    2: {"name": "⚙️ Индустриальная Эра", "bonus": 1.5, "req": 5000},
    3: {"name": "⚛️ Атомный Век", "bonus": 2.2, "req": 20000}
}

# --- СИСТЕМА ДАННЫХ ---
def load_stats():
    return json.load(open(STATS_FILE, 'r', encoding='utf-8')) if os.path.exists(STATS_FILE) else {}

def save_stats(stats):
    json.dump(stats, open(STATS_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

game_stats = load_stats()
active_duels = {}
waiting_players = []

def get_user(user_id):
    uid = str(user_id)
    if uid not in game_stats:
        game_stats[uid] = {
            "money": 2000, "manpower": 200, "tanks": 0, "planes": 0,
            "nukes": 0, "territory": 1, "wins": 0, "epoch": 1,
            "prestige": 0, "last_event": ""
        }
    return game_stats[uid]

# --- ИНТЕРФЕЙС ШТАБА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    u = get_user(message.from_user.id)
    save_stats(game_stats)
    kb = [
        [types.InlineKeyboardButton(text="⚔️ НАЧАТЬ ВТОРЖЕНИЕ", callback_data="war_find")],
        [types.InlineKeyboardButton(text="🏬 ВОЕННЫЙ РЫНОК", callback_data="market_open")],
        [types.InlineKeyboardButton(text="🔬 ТЕХНОЛОГИИ", callback_data="tech_open")],
        [types.InlineKeyboardButton(text="💰 НАЛОГИ И ИВЕНТЫ", callback_data="collect")]
    ]
    await message.answer(
        f"🎖 **ГЛАВНОКОМАНДУЮЩИЙ {message.from_user.first_name.upper()}**\n\n"
        f"🌐 Текущая Эра: {EPOCHS[u['epoch']]['name']}\n"
        f"🚩 Владения: {u['territory']} регионов\n"
        f"💵 Казна: {u['money']}$\n"
        f"🪖 Мобилизация: {u['manpower']} чел.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data == "market_open")
async def open_market(callback: types.CallbackQuery):
    u = get_user(callback.from_user.id)
    kb = [
        [types.InlineKeyboardButton(text="🪖 Нанять Дивизию (500$)", callback_data="buy_unit_man")],
        [types.InlineKeyboardButton(text="🚜 Бронетанковый полк (1500$)", callback_data="buy_unit_tank")],
        [types.InlineKeyboardButton(text="✈️ Звено истребителей (5000$)", callback_data="buy_unit_plane")],
        [types.InlineKeyboardButton(text="☢️ ЯДЕРНАЯ БОЕГОЛОВКА (50000$)", callback_data="buy_unit_nuke")],
        [types.InlineKeyboardButton(text="⬅️ В ШТАБ", callback_data="back")]
    ]
    await callback.message.edit_text("🏬 **ЧЕРНЫЙ РЫНОК ВООРУЖЕНИЯ**", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

# --- СИСТЕМА ТАКТИЧЕСКОГО БОЯ ---

async def start_battle(p1_id, p2_id):
    p1, p2 = get_user(p1_id), get_user(p2_id)
    duel = {
        "p1": p1_id, "p2": p2_id,
        "p1_hp": p1['manpower'], "p2_hp": p2['manpower'],
        "p1_tanks": p1['tanks'], "p2_tanks": p2['tanks'],
        "p1_nukes": p1['nukes'],
        "turn": p1_id, "p1_shield": False, "p2_shield": False
    }
    active_duels[p1_id] = active_duels[p2_id] = duel
    for pid in [p1_id, p2_id]:
        await bot.send_message(pid, "🚨 **ВОЙНА ОБЪЯВЛЕНА!** Выводите войска на позиции.")
        await battle_menu(pid)

async def battle_menu(uid):
    d = active_duels[uid]
    my_hp = d['p1_hp'] if uid == d['p1'] else d['p2_hp']
    en_hp = d['p2_hp'] if uid == d['p1'] else d['p1_hp']
    
    status = f"🪖 Ваша армия: `{my_hp}` | 🎯 Армия врага: `{en_hp}`\n"
    if d['turn'] == uid:
        kb = [
            [types.InlineKeyboardButton(text="🔫 ОБЫЧНАЯ АТАКА", callback_data="atk_normal")],
            [types.InlineKeyboardButton(text="🚜 ТАНКОВЫЙ ПРОРЫВ", callback_data="atk_tank")],
            [types.InlineKeyboardButton(text="🛡 УКРЕПРАЙОН", callback_data="atk_def")]
        ]
        if (uid == d['p1'] and d['p1_nukes'] > 0):
             kb.append([types.InlineKeyboardButton(text="☢️ ЯДЕРНЫЙ УДАР", callback_data="atk_nuke")])
        
        await bot.send_message(uid, status + "🚩 **ВАШ ПРИКАЗ, ГЕНЕРАЛ?**", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await bot.send_message(uid, status + "⏳ Враг перегруппировывает силы...")

@dp.callback_query(F.data.startswith("atk_"))
async def handle_atk(callback: types.CallbackQuery):
    uid = callback.from_user.id
    d = active_duels.get(uid)
    if not d or d['turn'] != uid: return

    target = d['p2'] if uid == d['p1'] else d['p1']
    u = get_user(uid)
    act = callback.data.split("_")[1]
    
    dmg = random.randint(20, 40) * EPOCHS[u['epoch']]['bonus']
    msg = ""

    if act == "normal":
        msg = f"🪖 Пехота пошла в атаку! Нанесено {int(dmg)} урона."
    elif act == "tank":
        dmg = (dmg + (d['p1_tanks' if uid == d['p1'] else 'p2_tanks'] * 15))
        msg = f"🚜 Танки раздавили оборону! Нанесено {int(dmg)} урона."
    elif act == "def":
        d['p1_shield' if uid == d['p1'] else 'p2_shield'] = True
        dmg = 0
        msg = "🛡 Вы заняли глухую оборону. Урон снижен."
    elif act == "nuke":
        dmg = 5000; u['nukes'] -= 1
        msg = "☢️ ГРИБ НА ГОРИЗОНТЕ! Вы испепелили армию врага!"

    # Защита
    if d['p1_shield' if target == d['p1'] else 'p2_shield'] and dmg > 0:
        dmg //= 3; d['p1_shield' if target == d['p1'] else 'p2_shield'] = False

    if uid == d['p1']: d['p2_hp'] -= dmg
    else: d['p1_hp'] -= dmg

    await callback.message.edit_text(msg)
    
    if d['p1_hp'] <= 0 or d['p2_hp'] <= 0:
        await end_game(d)
    else:
        d['turn'] = target
        await battle_menu(uid); await battle_menu(target)

async def end_game(d):
    win_id = d['p1'] if d['p2_hp'] <= 0 else d['p2']
    lose_id = d['p2'] if win_id == d['p1'] else d['p1']
    w, l = get_user(win_id), get_user(lose_id)
    
    w['money'] += 5000; w['territory'] += 1; w['wins'] += 1
    l['manpower'] = 0; l['territory'] = max(1, l['territory'] - 1)
    
    save_stats(game_stats)
    await bot.send_message(win_id, "🏆 **ПОБЕДА!** Вы захватили регион и 5000$.")
    await bot.send_message(lose_id, "💀 **КРАХ.** Армия уничтожена, регион потерян.")
    active_duels.pop(win_id); active_duels.pop(lose_id)

# --- ЭКОНОМИКА И ИВЕНТЫ ---

@dp.callback_query(F.data == "collect")
async def collect_logic(callback: types.CallbackQuery):
    u = get_user(callback.from_user.id)
    income = (u['territory'] * 500)
    
    # Случайный ивент
    events = [
        ("💎 Найдены алмазы!", 2000), 
        ("📉 Кризис в стране!", -1000), 
        ("🎖 Патриотический подъем!", 500)
    ]
    ev_text, ev_cash = random.choice(events)
    u['money'] += (income + ev_cash)
    save_stats(game_stats)
    
    await callback.answer(f"💰 Доход: {income}$\n🎭 Ивент: {ev_text} ({ev_cash}$)", show_alert=True)
    await cmd_start(callback.message)

@dp.callback_query(F.data == "back")
async def back(c: types.CallbackQuery): await cmd_start(c.message)

# --- ЗАПУСК ---
async def main():
    if not os.path.exists(STATS_FILE): save_stats({})
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
