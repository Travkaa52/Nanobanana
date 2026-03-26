# setup_db.py
import asyncio
from database.db import connect, execute
from database.models import SCHEMAS, INDEXES, DEFAULT_TARIFFS

async def setup():
    await connect()
    
    for name, sql in SCHEMAS.items():
        await execute(sql)
        print(f"✅ {name}")
    
    for idx in INDEXES:
        await execute(idx)
    
    print("✅ Индексы созданы")
    await execute(DEFAULT_TARIFFS)
    print("✅ Тарифы добавлены")
    
    print("🎉 База готова!")

if __name__ == "__main__":
    asyncio.run(setup())
