import os, json, asyncio
from typing import Optional, Dict, Any

import httpx
import aiosqlite
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL", "").rstrip("/")) or "https://guurenko-ai.onrender.com"

APIFREE_API_KEY = os.getenv("APIFREE_API_KEY", "")
APIFREE_BASE_URL = os.getenv("APIFREE_BASE_URL", "https://api.skycoding.ai").rstrip("/")
APIFREE_HTTP_TIMEOUT_SEC = int(os.getenv("APIFREE_HTTP_TIMEOUT_SEC", "180"))

DEFAULT_CHAT_MODEL = os.getenv("DEFAULT_CHAT_MODEL", "openai/gpt-5.2")
GROK_CHAT_MODEL = os.getenv("GROK_CHAT_MODEL", "xai/grok-4")

DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "google/nano-banana-pro")
DEFAULT_VIDEO_MODEL = os.getenv("DEFAULT_VIDEO_MODEL", "klingai/kling-v2.6/pro/image-to-video")
DEFAULT_MUSIC_MODEL = os.getenv("DEFAULT_MUSIC_MODEL", "mureka-ai/mureka-v8/generate-song")

DB_PATH = os.getenv("DB_PATH", "/var/data/app.db")

app = FastAPI(title="Guurenko AI", version="1.0.0")

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")
app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")

# --- DB helpers
async def db_fetchone(db: aiosqlite.Connection, sql: str, params: tuple = ()):
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return row

async def db_fetchall(db: aiosqlite.Connection, sql: str, params: tuple = ()):
    cur = await db.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()
    return rows

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
          tg_id INTEGER PRIMARY KEY,
          free_credits INTEGER DEFAULT 50,
          pro_credits INTEGER DEFAULT 0,
          created_at TEXT DEFAULT (datetime('now')),
          updated_at TEXT DEFAULT (datetime('now'))
        )""")
        cols = await db_fetchall(db, "PRAGMA table_info(users)")
        existing = {c[1] for c in cols}
        if "free_credits" not in existing:
            await db.execute("ALTER TABLE users ADD COLUMN free_credits INTEGER DEFAULT 50")
        if "pro_credits" not in existing:
            await db.execute("ALTER TABLE users ADD COLUMN pro_credits INTEGER DEFAULT 0")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS jobs(
          job_id TEXT PRIMARY KEY,
          tg_id INTEGER,
          kind TEXT NOT NULL,
          status TEXT NOT NULL,
          model TEXT,
          request_json TEXT,
          result_json TEXT,
          error_text TEXT,
          created_at TEXT DEFAULT (datetime('now')),
          updated_at TEXT DEFAULT (datetime('now'))
        )""")
        await db.commit()

async def get_or_create_user(tg_id: int) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(db, "SELECT tg_id, free_credits, pro_credits FROM users WHERE tg_id=?", (tg_id,))
        if row:
            return {"tg_id": row[0], "free_credits": row[1], "pro_credits": row[2]}
        await db.execute("INSERT INTO users(tg_id, free_credits, pro_credits) VALUES (?,?,?)", (tg_id, 50, 0))
        await db.commit()
        return {"tg_id": tg_id, "free_credits": 50, "pro_credits": 0}

async def consume_credit(tg_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(db, "SELECT free_credits, pro_credits FROM users WHERE tg_id=?", (tg_id,))
        if not row:
            await get_or_create_user(tg_id)
            row = await db_fetchone(db, "SELECT free_credits, pro_credits FROM users WHERE tg_id=?", (tg_id,))
        free_credits, pro_credits = int(row[0] or 0), int(row[1] or 0)
        if pro_credits > 0:
            await db.execute("UPDATE users SET pro_credits=pro_credits-1, updated_at=datetime('now') WHERE tg_id=?", (tg_id,))
            await db.commit()
            return True
        if free_credits > 0:
            await db.execute("UPDATE users SET free_credits=free_credits-1, updated_at=datetime('now') WHERE tg_id=?", (tg_id,))
            await db.commit()
            return True
        return False

# --- API Free (generic)
async def apifree_post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not APIFREE_API_KEY:
        raise HTTPException(status_code=500, detail="APIFREE_API_KEY не задан")
    url = f"{APIFREE_BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {APIFREE_API_KEY}"}
    timeout = httpx.Timeout(APIFREE_HTTP_TIMEOUT_SEC)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=data.get("error") or data.get("message") or data)
    return data

def models_payload():
    return {
      "chat": [
        {"id": DEFAULT_CHAT_MODEL, "title": f"GPT ({DEFAULT_CHAT_MODEL})", "is_default": True},
        {"id": GROK_CHAT_MODEL, "title": f"Grok ({GROK_CHAT_MODEL})", "is_default": False},
      ],
      "image": [{"id": DEFAULT_IMAGE_MODEL, "title": f"Nano Banana ({DEFAULT_IMAGE_MODEL})", "is_default": True}],
      "video": [{"id": DEFAULT_VIDEO_MODEL, "title": f"Kling ({DEFAULT_VIDEO_MODEL})", "is_default": True}],
      "music": [{"id": DEFAULT_MUSIC_MODEL, "title": f"Mureka ({DEFAULT_MUSIC_MODEL})", "is_default": True}],
    }

# --- Telegram
async def tg_api(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не задан")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}

async def tg_send_job_result(chat_id: int, kind: str, result: Dict[str, Any]):
    url = result.get("url")
    await tg_api("sendMessage", {"chat_id": chat_id, "text": f"✅ Готово: {kind}\n{url or ''}".strip()})
    if not url:
        return
    try:
        if kind == "image":
            await tg_api("sendPhoto", {"chat_id": chat_id, "photo": url})
        elif kind == "video":
            await tg_api("sendVideo", {"chat_id": chat_id, "video": url})
        elif kind == "music":
            res = await tg_api("sendAudio", {"chat_id": chat_id, "audio": url})
            if not res.get("ok"):
                await tg_api("sendDocument", {"chat_id": chat_id, "document": url})
    except Exception:
        pass

# --- Jobs queue
def new_job_id() -> str:
    import time, random
    return f"{int(time.time()*1000)}{random.randint(1000,9999)}"

async def enqueue_job(tg_id: Optional[int], kind: str, model: str, request_data: Dict[str, Any]) -> str:
    job_id = new_job_id()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
          "INSERT INTO jobs(job_id,tg_id,kind,status,model,request_json) VALUES(?,?,?,?,?,?)",
          (job_id, tg_id, kind, "queued", model, json.dumps(request_data, ensure_ascii=False))
        )
        await db.commit()
    return job_id

async def set_job(job_id: str, status: str, result: Optional[Dict[str, Any]] = None, error_text: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
          "UPDATE jobs SET status=?, result_json=?, error_text=?, updated_at=datetime('now') WHERE job_id=?",
          (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error_text, job_id)
        )
        await db.commit()

async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(db, "SELECT job_id,tg_id,kind,status,model,request_json,result_json,error_text FROM jobs WHERE job_id=?", (job_id,))
        if not row:
            return None
        return {
          "job_id": row[0], "tg_id": row[1], "kind": row[2], "status": row[3], "model": row[4],
          "request": json.loads(row[5] or "{}"),
          "result": json.loads(row[6] or "{}") if row[6] else None,
          "error": row[7]
        }

async def claim_next_job() -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db_fetchone(db, "SELECT job_id FROM jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1")
        if not row:
            return None
        job_id = row[0]
        await db.execute("UPDATE jobs SET status='running', updated_at=datetime('now') WHERE job_id=?", (job_id,))
        await db.commit()
    return await get_job(job_id)

async def run_job(job: Dict[str, Any]) -> Dict[str, Any]:
    kind = job["kind"]; model = job["model"]; req = job["request"] or {}
    if kind == "image":
        data = await apifree_post("/v1/images/generations", {"model": model, "prompt": req.get("prompt","")})
        url = None
        if isinstance(data.get("data"), list) and data["data"]:
            url = data["data"][0].get("url")
        url = data.get("url") or url
        return {"url": url, "raw": data}
    if kind == "video":
        data = await apifree_post("/v1/videos/generations", {"model": model, "prompt": req.get("prompt","")})
        return {"url": data.get("url"), "raw": data}
    if kind == "music":
        payload = {"model": model, "lyrics": req.get("lyrics","")}
        if req.get("style"): payload["style"] = req["style"]
        data = await apifree_post("/v1/music/generations", payload)
        return {"url": data.get("url"), "raw": data}
    raise HTTPException(status_code=400, detail="Unknown job kind")

_worker: Optional[asyncio.Task] = None

async def worker_loop():
    while True:
        job = await claim_next_job()
        if not job:
            await asyncio.sleep(1.2); continue
        try:
            result = await run_job(job)
            await set_job(job["job_id"], "done", result=result)
            if job.get("tg_id"):
                await tg_send_job_result(int(job["tg_id"]), job["kind"], result)
        except HTTPException as e:
            await set_job(job["job_id"], "error", error_text=str(e.detail))
        except Exception as e:
            await set_job(job["job_id"], "error", error_text=str(e))

@app.on_event("startup")
async def startup():
    await init_db()
    global _worker
    if _worker is None:
        _worker = asyncio.create_task(worker_loop())

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h3>Guurenko AI Backend</h3><p><a href='/webapp/'>Open Mini App</a></p>"

@app.get("/health")
async def health():
    return "OK"

@app.get("/api/models")
async def api_models():
    return models_payload()

@app.get("/api/me")
async def api_me(tg_id: str):
    try: tg_int = int(tg_id)
    except Exception: raise HTTPException(status_code=400, detail="tg_id должен быть числом")
    return await get_or_create_user(tg_int)

@app.post("/api/chat")
async def api_chat(body: Dict[str, Any] = Body(default={})):
    message = (body or {}).get("message","").strip()
    tg_id = (body or {}).get("tg_id")
    model = (body or {}).get("model") or DEFAULT_CHAT_MODEL
    if not message:
        raise HTTPException(status_code=400, detail="message пустой")
    if tg_id is not None:
        ok = await consume_credit(int(tg_id))
        if not ok:
            raise HTTPException(status_code=402, detail="Нет кредитов")
    data = await apifree_post("/v1/chat/completions", {"model": model, "messages":[{"role":"user","content":message}]})
    text = None
    try: text = data["choices"][0]["message"]["content"]
    except Exception: pass
    return {"model": model, "text": text, "raw": data}

@app.post("/api/chat/submit")
async def api_chat_compat(body: Dict[str, Any] = Body(default={})):
    return await api_chat(body)

@app.post("/api/image/submit")
async def api_image_submit(body: Dict[str, Any] = Body(default={})):
    prompt = (body or {}).get("prompt","").strip()
    model = (body or {}).get("model") or DEFAULT_IMAGE_MODEL
    tg_id = (body or {}).get("tg_id")
    if not prompt: raise HTTPException(status_code=400, detail="prompt пустой")
    if tg_id is not None:
        ok = await consume_credit(int(tg_id))
        if not ok: raise HTTPException(status_code=402, detail="Нет кредитов")
    job_id = await enqueue_job(int(tg_id) if tg_id is not None else None, "image", model, {"prompt": prompt})
    return {"job_id": job_id}

@app.get("/api/image/result/{job_id}")
async def api_image_result(job_id: str):
    job = await get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="job not found")
    if job["kind"] != "image": raise HTTPException(status_code=400, detail="wrong kind")
    if job["status"] == "done": return {"status":"done","url":(job["result"] or {}).get("url"),"raw":job["result"]}
    if job["status"] == "error": return {"status":"error","error":job["error"]}
    return {"status": job["status"]}

@app.post("/api/video/submit")
async def api_video_submit(body: Dict[str, Any] = Body(default={})):
    prompt = (body or {}).get("prompt","").strip()
    model = (body or {}).get("model") or DEFAULT_VIDEO_MODEL
    tg_id = (body or {}).get("tg_id")
    if not prompt: raise HTTPException(status_code=400, detail="prompt пустой")
    if tg_id is not None:
        ok = await consume_credit(int(tg_id))
        if not ok: raise HTTPException(status_code=402, detail="Нет кредитов")
    job_id = await enqueue_job(int(tg_id) if tg_id is not None else None, "video", model, {"prompt": prompt})
    return {"job_id": job_id}

@app.get("/api/video/result/{job_id}")
async def api_video_result(job_id: str):
    job = await get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="job not found")
    if job["kind"] != "video": raise HTTPException(status_code=400, detail="wrong kind")
    if job["status"] == "done": return {"status":"done","url":(job["result"] or {}).get("url"),"raw":job["result"]}
    if job["status"] == "error": return {"status":"error","error":job["error"]}
    return {"status": job["status"]}

@app.post("/api/music/submit")
async def api_music_submit(body: Dict[str, Any] = Body(default={})):
    lyrics = (body or {}).get("lyrics","").strip()
    style = (body or {}).get("style")
    model = (body or {}).get("model") or DEFAULT_MUSIC_MODEL
    tg_id = (body or {}).get("tg_id")
    if not lyrics: raise HTTPException(status_code=400, detail="lyrics пустой")
    if tg_id is not None:
        ok = await consume_credit(int(tg_id))
        if not ok: raise HTTPException(status_code=402, detail="Нет кредитов")
    job_id = await enqueue_job(int(tg_id) if tg_id is not None else None, "music", model, {"lyrics": lyrics, "style": style})
    return {"job_id": job_id}

@app.get("/api/music/result/{job_id}")
async def api_music_result(job_id: str):
    job = await get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="job not found")
    if job["kind"] != "music": raise HTTPException(status_code=400, detail="wrong kind")
    if job["status"] == "done": return {"status":"done","url":(job["result"] or {}).get("url"),"raw":job["result"]}
    if job["status"] == "error": return {"status":"error","error":job["error"]}
    return {"status": job["status"]}

@app.post("/telegram/webhook/hook")
async def telegram_webhook_hook(req: Request):
    update = await req.json()
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not chat_id:
        return {"ok": True}

    if text.startswith("/start"):
        miniapp_url = f"{PUBLIC_BASE_URL}/webapp/"
        await tg_api("sendMessage", {
          "chat_id": chat_id,
          "text": "Открывай Mini App 👇",
          "reply_markup": {"inline_keyboard": [[{"text":"Открыть Mini App","web_app":{"url": miniapp_url}}]]}
        })
        return {"ok": True}

    # Async commands (no 690s waits)
    if text.startswith("/image "):
        prompt = text[len("/image "):].strip()
        if prompt:
            job_id = await enqueue_job(int(chat_id), "image", DEFAULT_IMAGE_MODEL, {"prompt": prompt})
            await tg_api("sendMessage", {"chat_id": chat_id, "text": f"🕒 Создала IMAGE-задачу: {job_id}. Жди результат здесь."})
        return {"ok": True}

    if text.startswith("/video "):
        prompt = text[len("/video "):].strip()
        if prompt:
            job_id = await enqueue_job(int(chat_id), "video", DEFAULT_VIDEO_MODEL, {"prompt": prompt})
            await tg_api("sendMessage", {"chat_id": chat_id, "text": f"🕒 Создала VIDEO-задачу: {job_id}. Жди результат здесь."})
        return {"ok": True}

    if text.startswith("/music "):
        lyrics = text[len("/music "):].strip()
        if lyrics:
            job_id = await enqueue_job(int(chat_id), "music", DEFAULT_MUSIC_MODEL, {"lyrics": lyrics})
            await tg_api("sendMessage", {"chat_id": chat_id, "text": f"🕒 Создала MUSIC-задачу: {job_id}. Жди результат здесь."})
        return {"ok": True}

    return {"ok": True}
