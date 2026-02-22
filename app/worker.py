import json
import aiosqlite
from app.db import DB_PATH, log
from app.queue import dequeue
from app.telegram import tg_send_message, tg_send_photo, tg_send_video, tg_send_audio
from app.services.chat import run_chat
from app.services.image import run_image
from app.services.video import run_video
from app.services.music import run_music

async def _update_job(job_id: int, **fields):
    sets = []
    params = []
    for k, v in fields.items():
        sets.append(f"{k}=?")
        params.append(v)
    params.append(job_id)

    sql = f"UPDATE jobs SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, params)
        await db.commit()

async def _get_job(job_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, tg_id, type, model, prompt, payload_json FROM jobs WHERE id=?", (job_id,))
        row = await cur.fetchone()
        await cur.close()
        return row

async def worker_loop():
    await log("info", "worker started")
    while True:
        job_id = await dequeue()
        try:
            row = await _get_job(job_id)
            if not row:
                continue

            _, tg_id, jtype, model, prompt, payload_json = row
            await _update_job(job_id, status="running")

            payload = {}
            if payload_json:
                try:
                    payload = json.loads(payload_json)
                except Exception:
                    payload = {}

            # RUN
            if jtype == "chat":
                result = await run_chat(model, prompt)
                await _update_job(job_id, status="done", result_json=json.dumps(result, ensure_ascii=False))
                await tg_send_message(int(tg_id), result.get("text") or "Готово ✅")

            elif jtype == "image":
                result = await run_image(model, prompt)
                await _update_job(job_id, status="done", result_json=json.dumps(result, ensure_ascii=False))
                await tg_send_photo(int(tg_id), result["url"], caption="Готово ✅")

            elif jtype == "video":
                result = await run_video(model, prompt)
                await _update_job(job_id, status="done", result_json=json.dumps(result, ensure_ascii=False))
                await tg_send_video(int(tg_id), result["url"], caption="Готово ✅")

            elif jtype == "music":
                lyrics = payload.get("lyrics") or prompt
                style = payload.get("style")
                result = await run_music(model, lyrics, style)
                await _update_job(job_id, status="done", result_json=json.dumps(result, ensure_ascii=False))
                await tg_send_audio(int(tg_id), result["url"], caption="Готово ✅")

            else:
                await _update_job(job_id, status="error", error=f"unknown job type: {jtype}")
                await tg_send_message(int(tg_id), "Ошибка: неизвестный тип задачи")

        except Exception as e:
            await log("error", "worker error", {"job_id": job_id, "err": str(e)})
            try:
                await _update_job(job_id, status="error", error=str(e))
            except Exception:
                pass
