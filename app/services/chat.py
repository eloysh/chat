import os
import httpx
from typing import Any, Dict
from fastapi import HTTPException
from app.db import log
from app.apifree_client import apifree_post_with_optional_polling
APIFREE_API_KEY = os.getenv("APIFREE_API_KEY", "")
APIFREE_BASE_URL = os.getenv("APIFREE_BASE_URL", "https://api.skycoding.ai").rstrip("/")
APIFREE_HTTP_TIMEOUT_SEC = int(os.getenv("APIFREE_HTTP_TIMEOUT_SEC", "180"))

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
        await log("error", "apifree error", {"status": r.status_code, "endpoint": endpoint, "resp": data})
        raise HTTPException(status_code=r.status_code, detail=data)

    return data

async def run_chat(model: str, message: str) -> Dict[str, Any]:
    payload = {"model": model, "messages": [{"role": "user", "content": message}]}
    data = await apifree_post("/v1/chat/completions", payload)

    text = None
    try:
        text = data["choices"][0]["message"]["content"]
    except Exception:
        text = None

    return {"text": text, "raw": data}
