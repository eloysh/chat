import os
import json
import asyncio
import aiosqlite
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import httpx

from app.db import init_db, DB_PATH, log, get_or_create_user, consume_credit
from app.queue import enqueue
from app.models import get_models_catalog
from app.worker import worker_loop
from app.telegram import tg_send_message

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")

app = FastAPI(title="Guurenko Mini App Backend", version="1.0.0")

# ВАЖНО: не падаем если папки нет, а корректно
if os.path.isdir(WEBAPP_DIR):
    app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")

@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(worker_loop())
    await log("info", "startup ok", {"db": DB_PATH})

    # Авто setWebhook (можно отключить переменной)
    if os.getenv("AUTO_SET_WEBHOOK", "1") == "1" and BOT_TOKEN:
        try:
            base = PUBLIC_BASE_URL or ""
            if base:
                url = f"{base}/telegram/webhook/hook"
                async with httpx.AsyncClient(timeout=20) as client:
                    await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", params={"url": url})
                await log("info", "setWebhook", {"url": url})
        except Exception as e:
            await log("error", "setWebhook failed", {"err": str(e)})

@app.get("/health")
async def health():
    return "OK"

@app.get("/", response_class=HTMLResponse)
async def root():
    # редирект на miniapp
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/webapp/" />')

# ---------- Mini App API ----------

@app.get("/api/models")
async def api_models():
    return get_models_catalog()

@app.get("/api/me")
async def api_me(tg_id: int):
    u = await get_or_create_user(int(tg_id))
    return u

async def _create_job(tg_id: int, jtype: str, model: str, prompt: str, payload: Optional[Dict[str, Any]] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO jobs(tg_id, type, status, model, prompt, payload_json) VALUES (?,?,?,?,?,?)",
            (int(tg_id), jtype, "queued", model, prompt, json.dumps(payload or {}, ensure_ascii=False)),
        )
        await db.commit()
        job_id = cur.lastrowid
        await cur.close()
    await enqueue(job_id)
    return job_id

@app.post("/api/chat")
async def api_chat(body: Dict[str, Any] = Body(default={})):
    tg_id = int(body.get("tg_id") or 0)
    message = (body.get("message") or "").strip()
    model = (body.get("model") or "").strip()

    if not tg_id:
        raise HTTPException(400, "tg_id обязателен")
    if not message:
        raise HTTPException(400, "message пустой")

    ok = await consume_credit(tg_id)
    if not ok:
        raise HTTPException(402, "Недостаточно кредитов")

    job_id = await _create_job(tg_id, "chat", model, message)
    return {"job_id": job_id, "status": "queued"}

@app.post("/api/image/submit")
async def api_image_submit(body: Dict[str, Any] = Body(default={})):
    tg_id = int(body.get("tg_id") or 0)
    prompt = (body.get("prompt") or "").strip()
    model = (body.get("model") or "").strip()

    if not tg_id:
        raise HTTPException(400, "tg_id обязателен")
    if not prompt:
        raise HTTPException(400, "prompt пустой")

    ok = await consume_credit(tg_id)
    if not ok:
        raise HTTPException(402, "Недостаточно кредитов")

    job_id = await _create_job(tg_id, "image", model, prompt)
    return {"job_id": job_id, "status": "queued"}

@app.post("/api/video/submit")
async def api_video_submit(body: Dict[str, Any] = Body(default={})):
    tg_id = int(body.get("tg_id") or 0)
    prompt = (body.get("prompt") or "").strip()
    model = (body.get("model") or "").strip()

    if not tg_id:
        raise HTTPException(400, "tg_id обязателен")
    if not prompt:
        raise HTTPException(400, "prompt пустой")

    ok = await consume_credit(tg_id)
    if not ok:
        raise HTTPException(402, "Недостаточно кредитов")

    job_id = await _create_job(tg_id, "video", model, prompt)
    return {"job_id": job_id, "status": "queued"}

@app.post("/api/music/submit")
async def api_music_submit(body: Dict[str, Any] = Body(default={})):
    tg_id = int(body.get("tg_id") or 0)
    lyrics = (body.get("lyrics") or "").strip()
    style = (body.get("style") or "").strip() or None
    model = (body.get("model") or "").strip()

    if not tg_id:
        raise HTTPException(400, "tg_id обязателен")
    if not lyrics:
        raise HTTPException(400, "lyrics пустой")

    ok = await consume_credit(tg_id)
    if not ok:
        raise HTTPException(402, "Недостаточно кредитов")

    job_id = await _create_job(tg_id, "music", model, lyrics, payload={"lyrics": lyrics, "style": style})
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/job/{job_id}")
async def api_job(job_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, tg_id, type, status, model, prompt, result_json, error FROM jobs WHERE id=?",
            (int(job_id),),
        )
        row = await cur.fetchone()
        await cur.close()

    if not row:
        raise HTTPException(404, "job not found")

    result = None
    if row[6]:
        try:
            result = json.loads(row[6])
        except Exception:
            result = {"raw": row[6]}

    return {
        "id": row[0],
        "tg_id": row[1],
        "type": row[2],
        "status": row[3],
        "model": row[4],
        "prompt": row[5],
        "result": result,
        "error": row[7],
    }

# ---------- Telegram webhook ----------

@app.post("/telegram/webhook/hook")
async def telegram_webhook_hook(req: Request):
    update = await req.json()
    message = (update.get("message") or {})
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not chat_id:
        return {"ok": True}

    # /start
    if text.startswith("/start"):
        miniapp_url = (PUBLIC_BASE_URL or "").rstrip("/") + "/webapp/"
        if not miniapp_url.startswith("http"):
            miniapp_url = "https://guurenko-ai.onrender.com/webapp/"
        payload = {
            "chat_id": chat_id,
            "text": "Привет! Открывай Mini App 👇",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "Открыть Mini App", "web_app": {"url": miniapp_url}}
                ]]
            }
        }
        if BOT_TOKEN:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
        return {"ok": True}

    # быстрые команды в чате
    if text.startswith("/image "):
        prompt = text.replace("/image", "", 1).strip()
        jid = await _create_job(int(chat_id), "image", "", prompt)
        await tg_send_message(int(chat_id), f"✅ Принято. Генерирую изображение… (job {jid})")
        return {"ok": True}

    if text.startswith("/video "):
        prompt = text.replace("/video", "", 1).strip()
        jid = await _create_job(int(chat_id), "video", "", prompt)
        await tg_send_message(int(chat_id), f"✅ Принято. Генерирую видео… (job {jid})")
        return {"ok": True}

    if text.startswith("/music "):
        lyrics = text.replace("/music", "", 1).strip()
        jid = await _create_job(int(chat_id), "music", "", lyrics, payload={"lyrics": lyrics})
        await tg_send_message(int(chat_id), f"✅ Принято. Генерирую музыку… (job {jid})")
        return {"ok": True}

    if text.startswith("/chat "):
        msg = text.replace("/chat", "", 1).strip()
        jid = await _create_job(int(chat_id), "chat", "", msg)
        await tg_send_message(int(chat_id), f"✅ Принято. Думаю… (job {jid})")
        return {"ok": True}

    return {"ok": True}
