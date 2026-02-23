import os
import json
import asyncio
from typing import Any, Dict, Optional, Tuple

import httpx

APIFREE_BASE_URL = (os.getenv("APIFREE_BASE_URL") or "https://www.apifree.ai").rstrip("/")
APIFREE_API_KEY = os.getenv("APIFREE_API_KEY", "").strip()

# Мы не знаем точно, какой префикс у твоего провайдера (у тебя 404 на /model/...).
# Поэтому пробуем несколько вариантов.
PREFIXES_TO_TRY = [
    "",          # https://.../model/...
    "/api",      # https://.../api/model/...
    "/v1",       # https://.../v1/model/...
    "/api/v1",   # https://.../api/v1/model/...
]

class APIFreeError(RuntimeError):
    pass

def _auth_headers() -> Dict[str, str]:
    if not APIFREE_API_KEY:
        return {}
    return {"Authorization": f"Bearer {APIFREE_API_KEY}"}

async def apifree_post_json(
    path: str,
    payload: Dict[str, Any],
    timeout_s: float = 120.0,
) -> Tuple[str, httpx.Response]:
    """
    POST JSON на APIFREE, автоматически перебирая префиксы.
    Возвращает (final_url, response).

    Если везде 404 — поднимаем APIFreeError.
    """
    path = path.lstrip("/")  # "model/xxx/yyy"
    last_404: Optional[str] = None

    async with httpx.AsyncClient(timeout=timeout_s, headers=_auth_headers()) as client:
        for pref in PREFIXES_TO_TRY:
            url = f"{APIFREE_BASE_URL}{pref}/{path}"
            try:
                r = await client.post(url, json=payload)
            except Exception as e:
                # проблемы сети/SSL/timeout — это не 404, сразу отдаём наверх
                raise APIFreeError(f"APIFREE request failed: {e}") from e

            if r.status_code == 404:
                last_404 = url
                continue

            return url, r

    raise APIFreeError(
        f"APIFREE endpoint not found (404). Last tried: {last_404}. "
        f"Check APIFREE_BASE_URL and endpoint path."
    )

async def apifree_post_with_optional_polling(
    path: str,
    payload: Dict[str, Any],
    *,
    request_timeout_s: float = 120.0,
    max_wait_s: float = 1200.0,
    poll_every_s: float = 3.0,
) -> Dict[str, Any]:
    """
    Универсальный режим:
    1) Делает POST.
    2) Если ответ сразу содержит результат — возвращаем.
    3) Если ответ содержит task_id/job_id/id — пытаемся поллить статус.

    ВАЖНО: пути статуса у разных провайдеров разные. Ниже — “умная” попытка.
    Если у APIFREE другой путь — просто скажи, и я подстрою под их реальный формат.
    """
    final_url, r = await apifree_post_json(path, payload, timeout_s=request_timeout_s)

    # Если не 2xx — отдаём текст ошибки (чтобы было видно, что именно не так)
    if r.status_code < 200 or r.status_code >= 300:
        raise APIFreeError(
            f"APIFREE {r.status_code} for {final_url}: {r.text}"
        )

    # Пытаемся распарсить JSON
    try:
        data = r.json()
    except Exception:
        # если вернули не JSON, возвращаем как raw
        return {"raw": r.text, "url": final_url}

    # Если это уже готовый результат
    if isinstance(data, dict):
        # частые варианты
        if any(k in data for k in ("result", "output", "data", "audio_url", "image_url", "video_url")):
            return data

        # частые ID поля
        task_id = data.get("task_id") or data.get("job_id") or data.get("id") or data.get("taskId") or data.get("jobId")
        if task_id:
            # пробуем поллить стандартные “угадываемые” пути статуса
            status_paths = [
                f"task/{task_id}",
                f"tasks/{task_id}",
                f"job/{task_id}",
                f"jobs/{task_id}",
                f"result/{task_id}",
                f"results/{task_id}",
                # иногда статус висит в /model/.../tasks/{id}
                f"{path.rstrip('/')}/tasks/{task_id}",
                f"{path.rstrip('/')}/task/{task_id}",
            ]

            deadline = asyncio.get_event_loop().time() + max_wait_s
            while asyncio.get_event_loop().time() < deadline:
                for sp in status_paths:
                    try:
                        _, sr = await apifree_post_json(
                            sp,
                            payload={},  # часто статус GET, но на некоторых прокси — POST; если у тебя GET — скажешь, заменю
                            timeout_s=30.0,
                        )
                    except APIFreeError:
                        continue

                    if sr.status_code == 404:
                        continue
                    if sr.status_code < 200 or sr.status_code >= 300:
                        continue

                    try:
                        sdata = sr.json()
                    except Exception:
                        continue

                    # Признаки готовности
                    st = (sdata.get("status") or sdata.get("state") or "").lower()
                    if st in ("succeeded", "success", "done", "completed", "finished"):
                        return sdata
                    if st in ("failed", "error"):
                        raise APIFreeError(f"APIFREE task failed: {json.dumps(sdata, ensure_ascii=False)}")

                    # если уже появились url
                    if any(k in sdata for k in ("result", "output", "audio_url", "image_url", "video_url")):
                        return sdata

                await asyncio.sleep(poll_every_s)

            raise APIFreeError(f"APIFREE task timeout after {max_wait_s}s, task_id={task_id}, first={data}")

    return data
