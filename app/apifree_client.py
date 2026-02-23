import os
import json
import asyncio
from typing import Any, Dict, Optional, Tuple

import httpx

APIFREE_BASE_URL = (os.getenv("APIFREE_BASE_URL") or "https://api.apifree.ai").rstrip("/")
APIFREE_API_KEY = (os.getenv("APIFREE_API_KEY") or "").strip()

# Если у тебя в /v1/models endpoint_id вида: "google/nano-banana-pro"
# то вызовы обычно идут на: POST {APIFREE_BASE_URL}/v1/model/{endpoint_id}
MODEL_CALL_PREFIXES = [
    "/v1",   # самый вероятный для api.apifree.ai
    "",      # на случай если у тебя уже base_url содержит /v1
]

DEFAULT_TIMEOUT = float(os.getenv("APIFREE_HTTP_TIMEOUT_SEC") or "180")

class APIFreeError(RuntimeError):
    pass


def _auth_headers() -> Dict[str, str]:
    if not APIFREE_API_KEY:
        return {}
    return {"Authorization": f"Bearer {APIFREE_API_KEY}"}


async def _post_json(url: str, payload: Dict[str, Any], timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s, headers=_auth_headers()) as client:
        return await client.post(url, json=payload)


async def apifree_post_json(
    path: str,
    payload: Dict[str, Any],
    timeout_s: float = DEFAULT_TIMEOUT,
) -> Tuple[str, httpx.Response]:
    """
    POST JSON на APIFree, перебирая префиксы.
    Возвращает (final_url, response).
    """
    path = path.lstrip("/")  # "model/<endpoint_id>" или "tasks/<id>"
    last_err: Optional[str] = None

    for pref in MODEL_CALL_PREFIXES:
        url = f"{APIFREE_BASE_URL}{pref}/{path}".replace("//v1/", "/v1/")
        try:
            r = await _post_json(url, payload, timeout_s)
        except Exception as e:
            raise APIFreeError(f"APIFREE request failed: {e}") from e

        if r.status_code == 404:
            last_err = f"404 at {url}"
            continue

        return url, r

    raise APIFreeError(f"APIFREE endpoint not found (404). Last: {last_err}")


def _extract_task_id(data: Dict[str, Any]) -> Optional[str]:
    return (
        data.get("task_id")
        or data.get("taskId")
        or data.get("job_id")
        or data.get("jobId")
        or data.get("id")
    )


def _looks_like_result(data: Dict[str, Any]) -> bool:
    # Частые ключи результата у прокси/провайдеров
    result_keys = ("result", "output", "data", "audio_url", "image_url", "video_url", "url", "urls")
    return any(k in data for k in result_keys)


def _status_value(data: Dict[str, Any]) -> str:
    return str(data.get("status") or data.get("state") or "").lower().strip()


async def apifree_post_with_optional_polling(
    endpoint_id: str,
    payload: Dict[str, Any],
    *,
    request_timeout_s: float = DEFAULT_TIMEOUT,
    max_wait_s: float = 1200.0,
    poll_every_s: float = 3.0,
) -> Dict[str, Any]:
    """
    Универсальная функция под APIFree:
    POST /v1/model/{endpoint_id}
    - если результат сразу → вернуть
    - если вернули task/job id → поллить /v1/tasks/{id} (и запасные варианты)
    """

    # 1) стартуем задачу
    call_path = f"model/{endpoint_id}"
    final_url, r = await apifree_post_json(call_path, payload, timeout_s=request_timeout_s)

    if r.status_code < 200 or r.status_code >= 300:
        raise APIFreeError(f"APIFREE {r.status_code} for {final_url}: {r.text}")

    try:
        data = r.json()
    except Exception:
        return {"raw": r.text, "url": final_url}

    if not isinstance(data, dict):
        return {"data": data, "url": final_url}

    if _looks_like_result(data):
        return data

    task_id = _extract_task_id(data)
    if not task_id:
        # нет результата и нет id — вернем как есть, чтобы увидеть формат
        return data

    # 2) поллинг
    status_paths = [
        f"tasks/{task_id}",
        f"task/{task_id}",
        f"jobs/{task_id}",
        f"job/{task_id}",
        f"results/{task_id}",
        f"result/{task_id}",
        # иногда провайдеры кладут в model/<endpoint_id>/tasks/<id>
        f"model/{endpoint_id}/tasks/{task_id}",
    ]

    deadline = asyncio.get_event_loop().time() + max_wait_s
    last_status: Optional[Dict[str, Any]] = None

    while asyncio.get_event_loop().time() < deadline:
        for sp in status_paths:
            try:
                status_url, sr = await apifree_post_json(sp, {}, timeout_s=30.0)
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

            if not isinstance(sdata, dict):
                continue

            last_status = sdata

            if _looks_like_result(sdata):
                return sdata

            st = _status_value(sdata)
            if st in ("succeeded", "success", "done", "completed", "finished"):
                return sdata
            if st in ("failed", "error", "canceled", "cancelled"):
                raise APIFreeError(f"APIFREE task failed: {json.dumps(sdata, ensure_ascii=False)}")

        await asyncio.sleep(poll_every_s)

    # таймаут — вернем последний статус, чтобы ты видела что происходит
    return {"status": "timeout", "last_status": last_status, "task_id": task_id}
