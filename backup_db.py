# backup_db.py
import os
import json
import asyncpg
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def backup_database():
    """Создание бэкапа базы данных в JSON"""
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден")
        return
    
    try:
        conn = await asyncpg.connect(db_url)
        print("✅ Подключение к базе данных установлено")
        
        # Список таблиц для бэкапа
        tables = ['users', 'orders', 'feedback', 'tariffs', 'promocodes', 'user_promocodes']
        
        backup_data = {}
        
        for table in tables:
            try:
                rows = await conn.fetch(f"SELECT * FROM {table}")
                backup_data[table] = [dict(row) for row in rows]
                print(f"✅ Экспортировано {len(rows)} записей из {table}")
            except Exception as e:
                print(f"⚠️ Ошибка экспорта {table}: {e}")
                backup_data[table] = []
        
        # Сохраняем в JSON
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"database_backup_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"✅ Бэкап сохранен в {filename}")
        
        # Создаем SQL дамп
        sql_filename = f"database_backup_{timestamp}.sql"
        with open(sql_filename, 'w', encoding='utf-8') as f:
            for table, rows in backup_data.items():
                if rows:
                    f.write(f"\n-- Table: {table}\n")
                    for row in rows:
                        columns = ', '.join(row.keys())
                        values = []
                        for v in row.values():
                            if v is None:
                                values.append('NULL')
                            elif isinstance(v, str):
                                values.append(f"'{v.replace(chr(39), chr(39)+chr(39))}'")
                            elif isinstance(v, datetime):
                                values.append(f"'{v.isoformat()}'")
                            else:
                                values.append(str(v))
                        f.write(f"INSERT INTO {table} ({columns}) VALUES ({', '.join(values)});\n")
        
        print(f"✅ SQL дамп сохранен в {sql_filename}")
        
        await conn.close()
        
        # Выводим статистику
        print("\n📊 Статистика бэкапа:")
        for table, rows in backup_data.items():
            print(f"  {table}: {len(rows)} записей")
        
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")

if __name__ == "__main__":
    asyncio.run(backup_database())