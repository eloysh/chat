import os
import json
import aiosqlite
from typing import Any, Dict, Optional, Tuple

DB_PATH = os.getenv("DB_PATH", "/var/data/app.db")

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")

        # users
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY
        )
        """)

        # jobs
        await db.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            type TEXT NOT NULL,             -- chat|image|video|music
            status TEXT NOT NULL,           -- queued|running|done|error
            model TEXT,
            prompt TEXT,
            payload_json TEXT,
            result_json TEXT,
            error TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """)

        # logs
        await db.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            meta_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        # ---- миграции колонок users ----
        cols = await _table_columns(db, "users")
        if "free_credits" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN free_credits INTEGER NOT NULL DEFAULT 999999;")
        if "pro_credits" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN pro_credits INTEGER NOT NULL DEFAULT 0;")

        await db.commit()

async def _table_columns(db: aiosqlite.Connection, table: str):
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return {r[1] for r in rows}  # name

async def log(level: str, message: str, meta: Optional[Dict[str, Any]] = None):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO logs(level, message, meta_json) VALUES (?,?,?)",
                (level, message, json.dumps(meta or {}, ensure_ascii=False)),
            )
            await db.commit()
    except Exception:
        pass

async def db_fetchone(db: aiosqlite.Connection, sql: str, params: Tuple[Any, ...] = ()):
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return row

async def get_or_create_user(tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(db, "SELECT tg_id, free_credits, pro_credits FROM users WHERE tg_id=?", (tg_id,))
        if row:
            return {"tg_id": row[0], "free_credits": row[1], "pro_credits": row[2]}

        await db.execute("INSERT INTO users(tg_id, free_credits, pro_credits) VALUES (?,?,?)", (tg_id, 999999, 0))
        await db.commit()
        return {"tg_id": tg_id, "free_credits": 999999, "pro_credits": 0}

async def consume_credit(tg_id: int) -> bool:
    """
    Сейчас делаем максимально просто: бесплатные кредиты "безлимит" (чтобы не блокировало работу).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(db, "SELECT free_credits, pro_credits FROM users WHERE tg_id=?", (tg_id,))
        if not row:
            await db.execute("INSERT INTO users(tg_id, free_credits, pro_credits) VALUES (?,?,?)", (tg_id, 999999, 0))
            await db.commit()
            return True
        return True
