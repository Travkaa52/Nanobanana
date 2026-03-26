# database/models.py
"""SQL схемы для создания таблиц"""

SCHEMAS = {
    'users': """
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
            lang TEXT DEFAULT 'uk',
            blocked BOOL DEFAULT FALSE,
            tariff TEXT DEFAULT 'free',
            tariff_start TIMESTAMP,
            tariff_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """,
    
    'orders': """
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
    """,
    
    'feedback': """
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
    """,
    
    'tariffs': """
        CREATE TABLE IF NOT EXISTS tariffs (
            tariff_key TEXT PRIMARY KEY,
            name TEXT,
            price INTEGER,
            days INTEGER,
            emoji TEXT,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """,
    
    'promocodes': """
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
    """,
    
    'user_promocodes': """
        CREATE TABLE IF NOT EXISTS user_promocodes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            promo_code TEXT REFERENCES promocodes(code) ON DELETE CASCADE,
            used_at TIMESTAMP,
            UNIQUE(user_id, promo_code)
        )
    """
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_users_tariff ON users(tariff)",
    "CREATE INDEX IF NOT EXISTS idx_users_tariff_end ON users(tariff_end)",
    "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_promocodes_code ON promocodes(code)",
    "CREATE INDEX IF NOT EXISTS idx_promocodes_active ON promocodes(is_active)"
]

DEFAULT_TARIFFS = """
    INSERT INTO tariffs (tariff_key, name, price, days, emoji, active) VALUES
        ('1_day', '🌙 1 день', 20, 1, '🌙', true),
        ('30_days', '📅 30 днів', 70, 30, '📅', true),
        ('90_days', '🌿 90 днів', 150, 90, '🌿', true),
        ('180_days', '🌟 180 днів', 190, 180, '🌟', true),
        ('forever', '💎 Назавжди', 250, NULL, '💎', true)
    ON CONFLICT (tariff_key) DO NOTHING
"""
