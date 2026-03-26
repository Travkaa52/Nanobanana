import aiosqlite
from config import Config

async def init_db():
    async with aiosqlite.connect(Config.DB_PATH) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0,
                ref_by INTEGER,
                is_banned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица тарифов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tariffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price REAL,
                days INTEGER
            )
        """)
        # Таблица заказов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tariff_id INTEGER,
                status TEXT DEFAULT 'pending',
                fio TEXT,
                dob TEXT,
                sex TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица транзакций
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Заполнение тарифов по умолчанию
        async with db.execute("SELECT COUNT(*) FROM tariffs") as cursor:
            if (await cursor.fetchone())[0] == 0:
                tariffs = [
                    ('1 день', 20.0, 1),
                    ('30 днів', 70.0, 30),
                    ('90 днів', 150.0, 90),
                    ('180 днів', 190.0, 180),
                    ('Назавжди', 250.0, 9999)
                ]
                await db.executemany("INSERT INTO tariffs (name, price, days) VALUES (?, ?, ?)", tariffs)
        
        await db.commit()