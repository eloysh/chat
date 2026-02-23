import os
import time
import json
import asyncio
from typing import Any, Dict, Optional, Tuple, List

import httpx


APIFREE_BASE_URL = (os.getenv("APIFREE_BASE_URL") or "https://api.apifree.ai").rstrip("/")
APIFREE_MODEL_BASE_URL = (os.getenv("APIFREE_MODEL_BASE_URL") or "https://api.skycoding.ai").rstrip("/")
APIFREE_API_KEY = (os.getenv("APIFREE_API_KEY") or "").strip()

HTTP_TIMEOUT = float(os.getenv("APIFREE_HTTP_TIMEOUT_SEC") or "180")


class APIFreeError(RuntimeError):
    pass


def _auth_headers() -> Dict[str, str]:
    if not APIFREE_API_KEY:
        return {}
    return {"Authorization": f"Bearer {APIFREE_API_KEY}"}


async def _request_json(
    method: str,
    url: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    timeout_s: float = HTTP_TIMEOUT,
) -> Tuple[int, Dict[str, Any], str]:
    """
    Возвращает: (status_code, json_dict_or_empty, raw_text)
    """
    async with httpx.AsyncClient(timeout=timeout_s, headers=_auth_headers()) as client:
        r = await client.request(method, url, json=payload)

    txt = r.text or ""
    try:
        data = r.json() if txt else {}
    except Exception:
        data = {}

    return r.status_code, data, txt


# --- (опционально) кэш моделей ---
_models_cache: Optional[List[Dict[str, Any]]] = None
_models_cache_ts: float = 0.0
MODELS_CACHE_TTL_SEC = 300.0  # 5 минут


async def list_models(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    GET https://api.apifree.ai/v1/models
    """
    global _models_cache, _models_cache_ts

    now = time.time()
    if (not force_refresh) and _models_cache and (now - _models_cache_ts) < MODELS_CACHE_TTL_SEC:
        return _models_cache

    url = f"{APIFREE_BASE_URL}/v1/models"
    code, data, txt = await _request_json("GET", url, payload=None)

    if code != 200:
        raise APIFreeError(f"list_models failed: {code} {txt[:3000]}")

    models = data.get("models") or []
    if not isinstance(models, list):
        raise APIFreeError(f"list_models unexpected response: {txt[:3000]}")

    _models_cache = models
    _models_cache_ts = now
    return models


async def get_model_url(endpoint_id: str) -> str:
    """
    Возвращает абсолютный model_url.
    Пытаемся найти endpoint_id в /v1/models (чтобы не гадать), но если не нашли —
    просто строим по MODEL_BASE: https://api.skycoding.ai/v1/model/{endpoint_id}
    """
    try:
        models = await list_models(force_refresh=False)
        for m in models:
            if m.get("endpoint_id") == endpoint_id:
                meta = m.get("metadata") or {}
                model_url = meta.get("model_url")
                if model_url:
                    return str(model_url)
    except Exception:
        # если список моделей временно недоступен — fallback ниже
        pass

    return f"{APIFREE_MODEL_BASE_URL}/v1/model/{endpoint_id.lstrip('/')}"


def _extract_task_id(data: Dict[str, Any]) -> Optional[str]:
    for k in ("task_id", "job_id", "id", "taskId", "jobId"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _extract_status_url(data: Dict[str, Any]) -> Optional[str]:
    for k in ("status_url", "poll_url", "result_url", "task_url"):
        v = data.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def _looks_like_final_result(data: Dict[str, Any]) -> bool:
    # Частые поля результата
    keys = set(data.keys())
    if keys.intersection({"output", "result", "data", "image_url", "video_url", "audio_url"}):
        return True

    # Иногда бывает structure: {"data":[{"url": "..."}]}
    d = data.get("data")
    if isinstance(d, list) and d and isinstance(d[0], dict) and ("url" in d[0] or "file_url" in d[0]):
        return True

    return False


async def run_model(
    endpoint_id: str,
    payload: Dict[str, Any],
    *,
    request_timeout_s: float = HTTP_TIMEOUT,
    max_wait_s: float = 1800.0,
    poll_every_s: float = 3.0,
) -> Dict[str, Any]:
    """
    1) POST на model_url (skyCoding)
    2) Если сразу результат — вернуть
    3) Если вернулся task_id — poll GET на статус
    """
    model_url = await get_model_url(endpoint_id)

    code, data, txt = await _request_json("POST", model_url, payload=payload, timeout_s=request_timeout_s)
    if code < 200 or code >= 300:
        raise APIFreeError(f"Model POST failed [{code}] {model_url}: {txt[:4000]}")

    if not isinstance(data, dict) or not data:
        # вернули не JSON или пусто
        return {"raw": txt, "model_url": model_url}

    # Если готово сразу
    if _looks_like_final_result(data):
        data["_model_url"] = model_url
        return data

    # Ищем задачу
    task_id = _extract_task_id(data)
    status_url = _extract_status_url(data)

    if not task_id and not status_url:
        # Не похоже на async — вернём как есть
        data["_model_url"] = model_url
        return data

    # Собираем варианты урлов статуса
    candidates: List[str] = []
    if status_url:
        candidates.append(status_url)

    if task_id:
        # самые частые у провайдеров пути статуса
        candidates += [
            f"{APIFREE_MODEL_BASE_URL}/v1/task/{task_id}",
            f"{APIFREE_MODEL_BASE_URL}/v1/tasks/{task_id}",
            f"{APIFREE_MODEL_BASE_URL}/v1/job/{task_id}",
            f"{APIFREE_MODEL_BASE_URL}/v1/jobs/{task_id}",
            f"{APIFREE_MODEL_BASE_URL}/v1/result/{task_id}",
            f"{APIFREE_MODEL_BASE_URL}/v1/results/{task_id}",
        ]

    deadline = asyncio.get_event_loop().time() + max_wait_s

    last_err: Optional[str] = None
    while asyncio.get_event_loop().time() < deadline:
        for u in candidates:
            try:
                scode, sdata, stxt = await _request_json("GET", u, payload=None, timeout_s=60.0)
            except Exception as e:
                last_err = str(e)
                continue

            if scode == 404:
                continue
            if scode < 200 or scode >= 300:
                last_err = f"{scode} {stxt[:500]}"
                continue

            if isinstance(sdata, dict) and sdata:
                st = str(sdata.get("status") or sdata.get("state") or "").lower()

                if st in ("failed", "error", "canceled", "cancelled"):
                    raise APIFreeError(f"Task failed: {json.dumps(sdata, ensure_ascii=False)[:4000]}")

                if _looks_like_final_result(sdata) or st in ("succeeded", "success", "done", "completed", "finished"):
                    sdata["_model_url"] = model_url
                    sdata["_status_url"] = u
                    return sdata

        await asyncio.sleep(poll_every_s)

    raise APIFreeError(f"Task polling timeout. last_err={last_err} initial={json.dumps(data, ensure_ascii=False)[:1500]}")
