# database/db.py
import asyncpg
import os
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)
_pool: Optional[asyncpg.Pool] = None

DATABASE_URL = os.getenv("DATABASE_URL")

async def connect():
    """Создать пул соединений"""
    global _pool
    if not _pool:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL не задан")
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=60
        )
        logger.info("✅ Пул соединений создан")
    return _pool

async def close():
    """Закрыть пул"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Пул закрыт")

async def execute(query: str, *args) -> str:
    """Выполнить запрос"""
    pool = await connect()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch(query: str, *args) -> List[Dict]:
    """Получить список записей"""
    pool = await connect()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]

async def fetchone(query: str, *args) -> Optional[Dict]:
    """Получить одну запись"""
    pool = await connect()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None
