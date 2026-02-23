import os
import json
import aiosqlite
from typing import Any, Dict, Optional, Tuple

DB_PATH = os.getenv("DB_PATH", "/var/data/app.db")


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")

        # USERS
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            free_credits INTEGER NOT NULL DEFAULT 999999,
            pro_credits INTEGER NOT NULL DEFAULT 0
        )
        """)

        # JOBS
        await db.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            type TEXT,
            model TEXT,
            prompt TEXT,
            status TEXT DEFAULT 'pending',
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # LOGS
        await db.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            meta_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        await db.commit()


async def db_fetchone(db: aiosqlite.Connection, sql: str, params: Tuple[Any, ...] = ()):
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return row


async def get_or_create_user(tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(
            db,
            "SELECT tg_id, free_credits, pro_credits FROM users WHERE tg_id=?",
            (tg_id,)
        )

        if row:
            return {
                "tg_id": row[0],
                "free_credits": row[1],
                "pro_credits": row[2]
            }

        await db.execute(
            "INSERT INTO users(tg_id, free_credits, pro_credits) VALUES (?,?,?)",
            (tg_id, 999999, 0)
        )
        await db.commit()

        return {
            "tg_id": tg_id,
            "free_credits": 999999,
            "pro_credits": 0
        }


async def consume_credit(tg_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(
            db,
            "SELECT free_credits, pro_credits FROM users WHERE tg_id=?",
            (tg_id,)
        )

        if not row:
            await db.execute(
                "INSERT INTO users(tg_id, free_credits, pro_credits) VALUES (?,?,?)",
                (tg_id, 999999, 0)
            )
            await db.commit()

        return True
