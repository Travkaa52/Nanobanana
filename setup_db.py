import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def init_database():
    """Инициализация базы данных Aiven PostgreSQL"""
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в .env файле")
        return
    
    try:
        # Подключаемся к базе данных
        conn = await asyncpg.connect(db_url)
        print("✅ Подключение к базе данных установлено")
        
        # Создаем таблицу пользователей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                balance INTEGER DEFAULT 0,
                referred_by BIGINT,
                ref_count INTEGER DEFAULT 0,
                has_bought BOOLEAN DEFAULT FALSE,
                joined_date TIMESTAMP,
                total_spent INTEGER DEFAULT 0,
                language VARCHAR(10) DEFAULT 'uk',
                blocked BOOLEAN DEFAULT FALSE,
                tariff VARCHAR(50) DEFAULT 'free',
                tariff_purchase_date TIMESTAMP,
                tariff_expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        print("✅ Таблица users создана")
        
        # Создаем таблицу заказов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR(50) PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                tariff VARCHAR(50),
                fio VARCHAR(255),
                dob VARCHAR(20),
                sex VARCHAR(10),
                price INTEGER,
                promo_code VARCHAR(50),
                discount_amount INTEGER DEFAULT 0,
                final_price INTEGER,
                created_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending',
                approved_at TIMESTAMP
            )
        ''')
        print("✅ Таблица orders создана")
        
        # Создаем таблицу отзывов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id VARCHAR(50) PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                username VARCHAR(255),
                first_name VARCHAR(255),
                feedback TEXT,
                created_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'new',
                replied_at TIMESTAMP,
                admin_reply TEXT
            )
        ''')
        print("✅ Таблица feedback создана")
        
        # Создаем таблицу тарифов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tariffs (
                tariff_key VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100),
                price INTEGER,
                days INTEGER,
                emoji VARCHAR(10),
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        print("✅ Таблица tariffs создана")
        
        # Создаем таблицу промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) UNIQUE NOT NULL,
                discount_type VARCHAR(20) NOT NULL,
                discount_value INTEGER,
                max_activations INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                expires_at TIMESTAMP,
                tariff_name VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        print("✅ Таблица promocodes создана")
        
        # Создаем таблицу активаций промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_promocodes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                promo_code VARCHAR(50) REFERENCES promocodes(code) ON DELETE CASCADE,
                used_at TIMESTAMP,
                UNIQUE(user_id, promo_code)
            )
        ''')
        print("✅ Таблица user_promocodes создана")
        
        # Создаем индексы для оптимизации
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_tariff ON users(tariff)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_tariff_expires ON users(tariff_expires_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_promocodes_code ON promocodes(code)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_promocodes_expires ON promocodes(expires_at)')
        print("✅ Индексы созданы")
        
        # Создаем триггер для автоматического обновления updated_at
        await conn.execute('''
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ language 'plpgsql'
        ''')
        
        await conn.execute('''
            DROP TRIGGER IF EXISTS update_users_updated_at ON users;
            CREATE TRIGGER update_users_updated_at
                BEFORE UPDATE ON users
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
        ''')
        print("✅ Триггер обновления created_at создан")
        
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
        
        await conn.close()
        print("\n🎉 База данных успешно инициализирована!")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(init_database())