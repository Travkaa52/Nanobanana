# setup_db.py
import asyncio
import asyncpg
import os
import sys

async def setup_database():
    """Создание таблиц в PostgreSQL"""
    
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("❌ DATABASE_URL не найден")
        sys.exit(1)
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Подключение к БД установлено")
        
        # Создаем таблицу пользователей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                username TEXT,
                balance INT DEFAULT 0,
                referrer BIGINT,
                refs INT DEFAULT 0,
                bought BOOL DEFAULT FALSE,
                joined TIMESTAMP,
                spent INT DEFAULT 0,
                tariff TEXT DEFAULT 'free',
                tariff_start TIMESTAMP,
                tariff_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        print("✅ Таблица users создана")
        
        # Создаем таблицу заказов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                tariff TEXT,
                fio TEXT,
                dob TEXT,
                sex TEXT,
                price INT,
                promo_code TEXT,
                discount_amount INT DEFAULT 0,
                final_price INT,
                created_at TIMESTAMP,
                status TEXT DEFAULT 'pending',
                approved_at TIMESTAMP
            )
        ''')
        print("✅ Таблица orders создана")
        
        # Создаем таблицу отзывов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                username TEXT,
                first_name TEXT,
                feedback TEXT,
                created_at TIMESTAMP,
                status TEXT DEFAULT 'new',
                replied_at TIMESTAMP,
                admin_reply TEXT
            )
        ''')
        print("✅ Таблица feedback создана")
        
        # Создаем таблицу тарифов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tariffs (
                tariff_key TEXT PRIMARY KEY,
                name TEXT,
                price INTEGER,
                days INTEGER,
                emoji TEXT,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        print("✅ Таблица tariffs создана")
        
        # Создаем таблицу промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount_type TEXT,
                discount_value INTEGER,
                max_activations INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                expires_at TIMESTAMP,
                tariff_name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        print("✅ Таблица promocodes создана")
        
        # Создаем таблицу активаций промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_promocodes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                promo_code TEXT REFERENCES promocodes(code) ON DELETE CASCADE,
                used_at TIMESTAMP,
                UNIQUE(user_id, promo_code)
            )
        ''')
        print("✅ Таблица user_promocodes создана")
        
        # Создаем индексы
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_tariff ON users(tariff)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_tariff_end ON users(tariff_end)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_promocodes_code ON promocodes(code)')
        print("✅ Индексы созданы")
        
        # Добавляем дефолтные тарифы
        await conn.execute('''
            INSERT INTO tariffs (tariff_key, name, price, days, emoji, active) VALUES
                ('1_day', '🌙 1 день', 20, 1, '🌙', true),
                ('30_days', '📅 30 днів', 70, 30, '📅', true),
                ('90_days', '🌿 90 днів', 150, 90, '🌿', true),
                ('180_days', '🌟 180 днів', 190, 180, '🌟', true),
                ('forever', '💎 Назавжди', 250, NULL, '💎', true)
            ON CONFLICT (tariff_key) DO NOTHING
        ''')
        print("✅ Дефолтные тарифы добавлены")
        
        # Добавляем тестовый промокод
        await conn.execute('''
            INSERT INTO promocodes (code, discount_type, discount_value, max_activations, is_active) 
            VALUES ('WELCOME10', 'percentage', 10, 100, true)
            ON CONFLICT (code) DO NOTHING
        ''')
        print("✅ Тестовый промокод добавлен")
        
        await conn.close()
        print("\n🎉 База данных успешно инициализирована!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(setup_database())
