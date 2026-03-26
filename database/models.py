# database/models.py
"""SQL схемы"""

SCHEMAS = {
    'users': """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            name TEXT,
            username TEXT,
            balance INT DEFAULT 0,
            referrer BIGINT,
            refs INT DEFAULT 0,
            bought BOOL DEFAULT FALSE,
            joined TIMESTAMP,
            spent INT DEFAULT 0,
            lang TEXT DEFAULT 'uk',
            blocked BOOL DEFAULT FALSE,
            tariff TEXT DEFAULT 'free',
            tariff_start TIMESTAMP,
            tariff_end TIMESTAMP
        )
    """,
    
    'orders': """
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_id BIGINT REFERENCES users(id),
            tariff TEXT,
            fio TEXT,
            dob TEXT,
            sex TEXT,
            price INT,
            promo TEXT,
            discount INT DEFAULT 0,
            final INT,
            created TIMESTAMP,
            status TEXT DEFAULT 'pending'
        )
    """,
    
    'promocodes': """
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            type TEXT,
            value INT,
            max_uses INT DEFAULT 1,
            used INT DEFAULT 0,
            active BOOL DEFAULT TRUE,
            expires TIMESTAMP
        )
    """,
    
    'user_promos': """
        CREATE TABLE IF NOT EXISTS user_promos (
            user_id BIGINT REFERENCES users(id),
            promo_code TEXT REFERENCES promocodes(code),
            used_at TIMESTAMP,
            PRIMARY KEY (user_id, promo_code)
        )
    """
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_users_tariff ON users(tariff)",
    "CREATE INDEX IF NOT EXISTS idx_users_tariff_end ON users(tariff_end)",
    "CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_promos_code ON promocodes(code)"
]

DEFAULT_TARIFFS = """
    INSERT INTO tariffs (key, name, price, days) VALUES
        ('day1', '🌙 1 день', 20, 1),
        ('day30', '📅 30 днів', 70, 30),
        ('day90', '🌿 90 днів', 150, 90),
        ('day180', '🌟 180 днів', 190, 180),
        ('forever', '💎 Назавжди', 250, NULL)
    ON CONFLICT DO NOTHING
"""
