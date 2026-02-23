from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncpg

from src.settings import PROJECT_ROOT, settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=settings.database_url)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def run_migrations() -> None:
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Ensure _migrations table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id          SERIAL PRIMARY KEY,
                name        TEXT UNIQUE NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        # Get already-applied migrations
        applied = {
            row["name"]
            for row in await conn.fetch("SELECT name FROM _migrations")
        }

        # Find and sort migration files
        migrations_dir = PROJECT_ROOT / "migrations"
        sql_files = sorted(migrations_dir.glob("*.sql"))

        for sql_file in sql_files:
            if sql_file.name in applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO _migrations (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
                sql_file.name,
            )


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    pool = await get_pool()
    return await pool.fetchrow(query, *args)


async def fetchval(query: str, *args: Any) -> Any:
    pool = await get_pool()
    return await pool.fetchval(query, *args)


async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    return await pool.execute(query, *args)
