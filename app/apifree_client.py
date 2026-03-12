import os
import json
import asyncio
from typing import Any, Dict, Optional, Tuple

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

def _clean_endpoint_id(endpoint_id: str) -> str:
    s = (endpoint_id or "").strip().lstrip("/")
    for prefix in ("v1/model/", "model/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s

async def _request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None, timeout_s: float = HTTP_TIMEOUT):
    async with httpx.AsyncClient(timeout=timeout_s, headers=_auth_headers()) as client:
        r = await client.request(method, url, json=payload)

    txt = r.text or ""
    try:
        data = r.json() if txt else {}
    except Exception:
        data = {"raw": txt}
    return r.status_code, data, txt

async def list_models() -> Dict[str, Any]:
    url = f"{APIFREE_BASE_URL}/v1/models"
    code, data, txt = await _request_json("GET", url, None)
    if code != 200:
        raise APIFreeError(f"list_models failed [{code}]: {txt}")
    return data

async def chat_completion(model: str, message: str) -> Dict[str, Any]:
    url = f"{APIFREE_BASE_URL}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}]
    }
    code, data, txt = await _request_json("POST", url, payload)
    if code < 200 or code >= 300:
        raise APIFreeError(f"chat failed [{code}]: {txt}")
    return data

def _extract_task_id(data: Dict[str, Any]) -> Optional[str]:
    for k in ("task_id", "job_id", "id", "taskId", "jobId"):
        v = data.get(k)
        if v:
            return str(v)
    return None

def _is_final(data: Dict[str, Any]) -> bool:
    if any(k in data for k in ("result", "output", "audio_url", "image_url", "video_url", "url", "data")):
        return True
    d = data.get("data")
    if isinstance(d, list) and d and isinstance(d[0], dict) and ("url" in d[0] or "file_url" in d[0]):
        return True
    return False

async def model_submit(endpoint_id: str, payload: Dict[str, Any], timeout_s: float = HTTP_TIMEOUT) -> Dict[str, Any]:
    endpoint_id = _clean_endpoint_id(endpoint_id)
    url = f"{APIFREE_MODEL_BASE_URL}/v1/model/{endpoint_id}"
    code, data, txt = await _request_json("POST", url, payload, timeout_s=timeout_s)
    if code < 200 or code >= 300:
        raise APIFreeError(f"model submit failed [{code}] {url}: {txt}")
    if not isinstance(data, dict):
        return {"raw": txt}
    data["_model_url"] = url
    return data

async def model_poll(task_id: str, timeout_s: float = 30.0) -> Optional[Dict[str, Any]]:
    candidates = [
        f"{APIFREE_MODEL_BASE_URL}/v1/task/{task_id}",
        f"{APIFREE_MODEL_BASE_URL}/v1/tasks/{task_id}",
        f"{APIFREE_MODEL_BASE_URL}/v1/job/{task_id}",
        f"{APIFREE_MODEL_BASE_URL}/v1/jobs/{task_id}",
        f"{APIFREE_MODEL_BASE_URL}/v1/result/{task_id}",
        f"{APIFREE_MODEL_BASE_URL}/v1/results/{task_id}",
    ]

    for url in candidates:
        code, data, txt = await _request_json("GET", url, None, timeout_s=timeout_s)
        if code == 404:
            continue
        if 200 <= code < 300 and isinstance(data, dict):
            return data

        code, data, txt = await _request_json("POST", url, {}, timeout_s=timeout_s)
        if 200 <= code < 300 and isinstance(data, dict):
            return data

    return None

async def apifree_post_with_optional_polling(
    endpoint_id: str,
    payload: Dict[str, Any],
    *,
    request_timeout_s: float = HTTP_TIMEOUT,
    max_wait_s: float = 1800.0,
    poll_every_s: float = 3.0,
) -> Dict[str, Any]:
    data = await model_submit(endpoint_id, payload, timeout_s=request_timeout_s)

    if _is_final(data):
        return data

    task_id = _extract_task_id(data)
    if not task_id:
        return data

    deadline = asyncio.get_event_loop().time() + max_wait_s
    last_status = None

    while asyncio.get_event_loop().time() < deadline:
        sdata = await model_poll(task_id)
        if sdata:
            last_status = sdata
            status = str(sdata.get("status") or sdata.get("state") or "").lower().strip()

            if status in ("succeeded", "success", "done", "completed", "finished"):
                return sdata
            if status in ("failed", "error", "canceled", "cancelled"):
                raise APIFreeError(f"task failed: {json.dumps(sdata, ensure_ascii=False)[:4000]}")
            if _is_final(sdata):
                return sdata

        await asyncio.sleep(poll_every_s)

    return {"status": "timeout", "task_id": task_id, "last_status": last_status}
