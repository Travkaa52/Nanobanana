import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_connection():
    """Тест подключения к Aiven PostgreSQL"""
    db_url = os.getenv("DATABASE_URL")
    print(f"Подключение к: {db_url}")
    
    try:
        conn = await asyncpg.connect(db_url)
        print("✅ Успешное подключение к базе данных!")
        
        # Тестовый запрос
        result = await conn.fetchval("SELECT version()")
        print(f"Версия PostgreSQL: {result}")
        
        await conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())