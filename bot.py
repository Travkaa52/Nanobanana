import os
import asyncio
import logging
import random
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

# Настройка
logging.basicConfig(level=logging.INFO)
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()

# Файл статистики
STATS_FILE = "army_war_stats.json"

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

game_stats = load_stats()
active_duels = {}  # Активные пошаговые бои
waiting_players = []  # Очередь поиска

# --- Системные функции ---

def get_user(user_id):
    uid = str(user_id)
    if uid not in game_stats:
        game_stats[uid] = {
            "money": 1000,
            "manpower": 100,  # Это твоё ХП (численность армии)
            "tanks": 0,
            "wins": 0,
            "power_lvl": 1
        }
    return game_stats[uid]

# --- Основное меню и База ---

@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    save_stats(game_stats)
    kb = [
        [types.InlineKeyboardButton(text="⚔️ Найти противника", callback_data="find_battle")],
        [types.InlineKeyboardButton(text="🏰 Моя База (Армия)", callback_data="my_base")],
        [types.InlineKeyboardButton(text="💰 Сбор налогов", callback_data="get_money")]
    ]
    await message.answer(
        "🎖 **WAR FIGHT: ARMY EDITION**\n\n"
        "Управляй численностью войск и побеждай в пошаговых битвах!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data == "my_base")
async def show_base(callback: types.CallbackQuery):
    u = get_user(callback.from_user.id)
    text = (
        f"🏰 **ВАША БАЗА**\n\n"
        f"💰 Бюджет: {u['money']}$\n"
        f"🪖 Армия: {u['manpower']} солдат (Твоё ХП)\n"
        f"🚜 Танки: {u['tanks']} ед. (+ к урону)\n"
        f"🔬 Технологии: Lvl {u['power_lvl']}"
    )
    kb = [[types.InlineKeyboardButton(text="🪖 Нанять 20 солдат (200$)", callback_data="buy_man")],
          [types.InlineKeyboardButton(text="🚜 Купить танк (500$)", callback_data="buy_tank")],
          [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]]
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

# --- Логика Пошагового Боя ---

async def start_duel(p1_id, p2_id):
    duel_id = f"{p1_id}_{p2_id}"
    p1 = get_user(p1_id)
    p2 = get_user(p2_id)
    
    duel_data = {
        "p1": p1_id, "p2": p2_id,
        "p1_hp": p1['manpower'], "p2_hp": p2['manpower'], # ХП = численность солдат
        "p1_tanks": p1['tanks'], "p2_tanks": p2['tanks'],
        "turn": p1_id,
        "round": 1
    }
    
    active_duels[p1_id] = duel_data
    active_duels[p2_id] = duel_data
    
    for pid in [p1_id, p2_id]:
        await bot.send_message(pid, "⚔️ **БОЙ НАЧАЛСЯ!**\nВаша армия столкнулась с врагом.")
        await send_turn_menu(pid)

async def send_turn_menu(user_id):
    duel = active_duels.get(user_id)
    if not duel: return
    
    is_my_turn = (duel['turn'] == user_id)
    opponent_id = duel['p2'] if user_id == duel['p1'] else duel['p1']
    
    # Полоски "здоровья" (армии)
    my_hp = duel['p1_hp'] if user_id == duel['p1'] else duel['p2_hp']
    op_hp = duel['p2_hp'] if user_id == duel['p1'] else duel['p1_hp']
    
    status = f"🪖 Твоя армия: {my_hp}\n🎖 Армия врага: {op_hp}\n\n"
    
    if is_my_turn:
        kb = [
            [types.InlineKeyboardButton(text="🎯 Огонь из всех орудий", callback_data="war_shoot")],
            [types.InlineKeyboardButton(text="💣 Арт-обстрел", callback_data="war_artillery")],
            [types.InlineKeyboardButton(text="🛡 Окопаться", callback_data="war_cover")]
        ]
        await bot.send_message(user_id, status + "🚩 **ТВОЙ ХОД:**", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await bot.send_message(user_id, status + "⏳ Ожидаем хода противника...")

@dp.callback_query(F.data.startswith("war_"))
async def handle_battle_turn(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_duels: return
    
    duel = active_duels[user_id]
    if duel['turn'] != user_id:
        return await callback.answer("Сейчас не твой ход!", show_alert=True)
    
    op_id = duel['p2'] if user_id == duel['p1'] else duel['p1']
    action = callback.data.split("_")[1]
    
    # Расчет урона на основе техники
    my_tanks = duel['p1_tanks'] if user_id == duel['p1'] else duel['p2_tanks']
    base_dmg = random.randint(15, 25) + (my_tanks * 5)
    
    if action == "shoot":
        damage = base_dmg
        msg = f"💥 Вы провели атаку! Враг потерял {damage} солдат."
    elif action == "artillery":
        if random.random() > 0.4:
            damage = int(base_dmg * 1.8)
            msg = f"🚀 ПРЯМОЕ ПОПАДАНИЕ! Арт-обстрел уничтожил {damage} солдат!"
        else:
            damage = 0
            msg = "💨 Промах! Снаряды упали в молоко."
    else: # cover
        damage = 0
        msg = "🛡 Вы приказали войскам окопаться. В следующем ходу потери будут меньше."

    # Применяем урон
    if user_id == duel['p1']: duel['p2_hp'] -= damage
    else: duel['p1_hp'] -= damage
    
    await callback.message.edit_text(msg)
    
    # Проверка на конец боя
    if duel['p1_hp'] <= 0 or duel['p2_hp'] <= 0:
        await finish_war(duel)
    else:
        duel['turn'] = op_id
        await send_turn_menu(user_id)
        await send_turn_menu(op_id)

async def finish_war(duel):
    p1_id, p2_id = duel['p1'], duel['p2']
    winner_id = p1_id if duel['p2_hp'] <= 0 else p2_id
    loser_id = p2_id if winner_id == p1_id else p1_id
    
    # Обновляем реальную статистику (потери солдат остаются!)
    w = get_user(winner_id)
    l = get_user(loser_id)
    
    w['manpower'] = duel['p1_hp'] if winner_id == p1_id else duel['p2_hp']
    l['manpower'] = 0 # Проигравший теряет всё
    
    w['wins'] += 1
    w['money'] += 500
    
    save_stats(game_stats)
    
    await bot.send_message(winner_id, "🏆 **ПОБЕДА!**\nВы захватили территорию врага и получили 500$.")
    await bot.send_message(loser_id, "💔 **ПОРАЖЕНИЕ...**\nВаша армия полностью уничтожена. Нужно нанимать новых солдат.")
    
    del active_duels[p1_id]
    del active_duels[p2_id]

# --- Очередь и Экономика ---

@dp.callback_query(F.data == "find_battle")
async def find_battle(callback: types.CallbackQuery):
    uid = callback.from_user.id
    u = get_user(uid)
    if u['manpower'] <= 0:
        return await callback.answer("У тебя нет армии! Найми солдат на базе.", show_alert=True)
    
    if uid not in waiting_players:
        waiting_players.append(uid)
    
    if len(waiting_players) >= 2:
        p1 = waiting_players.pop(0)
        p2 = waiting_players.pop(0)
        await start_duel(p1, p2)
    else:
        await callback.message.edit_text("🔍 Поиск противника...")

@dp.callback_query(F.data == "buy_man")
async def buy_man(callback: types.CallbackQuery):
    u = get_user(callback.from_user.id)
    if u['money'] >= 200:
        u['money'] -= 200
        u['manpower'] += 20
        save_stats(game_stats)
        await callback.answer("🪖 Пехота нанята!")
        await show_base(callback)
    else:
        await callback.answer("Мало денег!", show_alert=True)

@dp.callback_query(F.data == "get_money")
async def get_money(callback: types.CallbackQuery):
    u = get_user(callback.from_user.id)
    reward = random.randint(100, 200)
    u['money'] += reward
    save_stats(game_stats)
    await callback.answer(f"💰 Собрано {reward}$")

@dp.callback_query(F.data == "to_main")
async def to_main(callback: types.CallbackQuery):
    await start(callback.message)

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
