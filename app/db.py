import os
import json
import aiosqlite
from typing import Any, Dict, Optional, Tuple, Set

DB_PATH = os.getenv("DB_PATH", "/var/data/app.db")


# ---------- helpers ----------

async def _table_columns(db: aiosqlite.Connection, table: str) -> Set[str]:
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    await cur.close()
    return {r[1] for r in rows}  # column name


async def db_fetchone(db: aiosqlite.Connection, sql: str, params: Tuple[Any, ...] = ()):
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return row


async def log(level: str, message: str, meta: Optional[Dict[str, Any]] = None):
    """
    Безопасный логгер в SQLite. Никогда не валит приложение.
    """
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                meta_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """)
            await db.execute(
                "INSERT INTO logs(level, message, meta_json) VALUES (?,?,?)",
                (level, message, json.dumps(meta or {}, ensure_ascii=False)),
            )
            await db.commit()
    except Exception:
        pass


# ---------- init / migrations ----------

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")

        # USERS (сразу с кредитами)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            free_credits INTEGER NOT NULL DEFAULT 999999,
            pro_credits INTEGER NOT NULL DEFAULT 0
        )
        """)

        # JOBS (совместимо с main.py)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            type TEXT,
            status TEXT DEFAULT 'queued',
            model TEXT,
            prompt TEXT,
            payload_json TEXT,
            result_json TEXT,
            error TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        # на всякий: если таблица была создана раньше без колонок — добавим миграциями
        # users migrations
        ucols = await _table_columns(db, "users")
        if "free_credits" not in ucols:
            await db.execute("ALTER TABLE users ADD COLUMN free_credits INTEGER NOT NULL DEFAULT 999999;")
        if "pro_credits" not in ucols:
            await db.execute("ALTER TABLE users ADD COLUMN pro_credits INTEGER NOT NULL DEFAULT 0;")

        # jobs migrations
        jcols = await _table_columns(db, "jobs")
        if "tg_id" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN tg_id INTEGER;")
        if "type" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN type TEXT;")
        if "status" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT 'queued';")
        if "model" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN model TEXT;")
        if "prompt" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN prompt TEXT;")
        if "payload_json" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN payload_json TEXT;")
        if "result_json" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN result_json TEXT;")
        if "error" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN error TEXT;")
        if "created_at" not in jcols:
            await db.execute("ALTER TABLE jobs ADD COLUMN created_at TEXT DEFAULT (datetime('now'));")

        await db.commit()


# ---------- app functions ----------

async def get_or_create_user(tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(
            db,
            "SELECT tg_id, free_credits, pro_credits FROM users WHERE tg_id=?",
            (int(tg_id),),
        )
        if row:
            return {"tg_id": row[0], "free_credits": row[1], "pro_credits": row[2]}

        await db.execute(
            "INSERT INTO users(tg_id, free_credits, pro_credits) VALUES (?,?,?)",
            (int(tg_id), 999999, 0),
        )
        await db.commit()
        return {"tg_id": int(tg_id), "free_credits": 999999, "pro_credits": 0}


async def consume_credit(tg_id: int) -> bool:
    """
    Пока делаем 'безлимит', чтобы ничего не блокировало.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(
            db,
            "SELECT free_credits, pro_credits FROM users WHERE tg_id=?",
            (int(tg_id),),
        )
        if not row:
            await db.execute(
                "INSERT INTO users(tg_id, free_credits, pro_credits) VALUES (?,?,?)",
                (int(tg_id), 999999, 0),
            )
            await db.commit()
        return True
