import json
import asyncio
import aiosqlite

from app.db import DB_PATH, log
from app.queue import dequeue
from app.telegram import tg_send_message, tg_send_photo, tg_send_video, tg_send_audio

from app.services.chat import run_chat
from app.services.image import run_image
from app.services.video import run_video
from app.services.music import run_music


# --------- helpers ---------

def _json_dumps(x) -> str:
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return json.dumps({"raw": str(x)}, ensure_ascii=False)

def _pick_url(result: dict, kind: str) -> str | None:
    """
    Универсально вытаскиваем ссылку из ответа.
    kind: "image" | "video" | "audio"
    """
    if not isinstance(result, dict):
        return None

    # Самые частые ключи
    direct_keys = {
        "image": ["url", "image_url", "image", "output_url", "result_url"],
        "video": ["url", "video_url", "video", "output_url", "result_url"],
        "audio": ["url", "audio_url", "audio", "output_url", "result_url"],
    }

    for k in direct_keys.get(kind, []):
        v = result.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v

    # Если результат вложенный: result/output/data
    for container_key in ("result", "output", "data"):
        v = result.get(container_key)
        if isinstance(v, dict):
            for k in direct_keys.get(kind, []):
                vv = v.get(k)
                if isinstance(vv, str) and vv.startswith("http"):
                    return vv
        if isinstance(v, list) and v:
            # иногда список ссылок
            vv = v[0]
            if isinstance(vv, str) and vv.startswith("http"):
                return vv
            if isinstance(vv, dict):
                for k in direct_keys.get(kind, []):
                    vvv = vv.get(k)
                    if isinstance(vvv, str) and vvv.startswith("http"):
                        return vvv

    return None


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
        cur = await db.execute(
            "SELECT id, tg_id, type, model, prompt, payload_json FROM jobs WHERE id=?",
            (job_id,),
        )
        row = await cur.fetchone()
        await cur.close()
        return row


# --------- worker loop ---------

async def worker_loop():
    await log("info", "worker started")

    while True:
        job_id = await dequeue()
        if not job_id:
            await asyncio.sleep(0.2)
            continue

        try:
            row = await _get_job(job_id)
            if not row:
                continue

            _, tg_id, jtype, model, prompt, payload_json = row
            tg_id = int(tg_id)

            await _update_job(job_id, status="running", error=None)

            payload = {}
            if payload_json:
                try:
                    payload = json.loads(payload_json)
                except Exception:
                    payload = {}

            # ВАЖНО: всегда проставляем prompt в payload, чтобы сервисы были единообразны
            if "prompt" not in payload and prompt:
                payload["prompt"] = prompt

            # -------- RUN --------
            if jtype == "chat":
                # chat сейчас проще: model + текст
                result = await run_chat(model, prompt)
                await _update_job(job_id, status="done", result_json=_json_dumps(result))

                text = None
                if isinstance(result, dict):
                    text = result.get("text") or result.get("message")
                await tg_send_message(tg_id, text or "Готово ✅")

            elif jtype == "image":
                # image: model + payload dict
                result = await run_image(model, payload)
                await _update_job(job_id, status="done", result_json=_json_dumps(result))

                url = _pick_url(result, "image")
                if not url:
                    raise RuntimeError(f"Image result has no URL. Result: {result}")

                await tg_send_photo(tg_id, url, caption="Готово ✅")

            elif jtype == "video":
                result = await run_video(model, payload)
                await _update_job(job_id, status="done", result_json=_json_dumps(result))

                url = _pick_url(result, "video")
                if not url:
                    raise RuntimeError(f"Video result has no URL. Result: {result}")

                await tg_send_video(tg_id, url, caption="Готово ✅")

            elif jtype == "music":
                # music: model + payload dict (lyrics/style)
                # подстрахуем:
                if "lyrics" not in payload:
                    payload["lyrics"] = payload.get("prompt") or prompt or ""
                result = await run_music(model, payload)
                await _update_job(job_id, status="done", result_json=_json_dumps(result))

                url = _pick_url(result, "audio")
                if not url:
                    raise RuntimeError(f"Audio result has no URL. Result: {result}")

                await tg_send_audio(tg_id, url, caption="Готово ✅")

            else:
                await _update_job(job_id, status="error", error=f"unknown job type: {jtype}")
                await tg_send_message(tg_id, "Ошибка: неизвестный тип задачи")

        except Exception as e:
            await log("error", "worker error", {"job_id": job_id, "err": str(e)})
            try:
                await _update_job(job_id, status="error", error=str(e))
            except Exception:
                pass
            try:
                await tg_send_message(int(row[1]) if row else tg_id, f"Ошибка: {e}")
            except Exception:
                pass
