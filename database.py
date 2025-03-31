import os

import asyncpg
from asyncpg import create_pool

POSTGRES_URI = os.getenv("POSTGRESURL")
DB_USER = os.getenv("DATABASE_USER")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD")

async def get_db():
    try:
        conn = await asyncpg.connect(
            dsn=POSTGRES_URI,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10  # Установите таймаут 10 секунд
        )
        print("Успешное подключение к PostgreSQL!")
        return conn
    except Exception as e:
        raise