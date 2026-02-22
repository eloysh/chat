import os
from typing import Any, Dict
from fastapi import HTTPException
from app.services.chat import apifree_post

DEFAULT_VIDEO_MODEL = os.getenv("DEFAULT_VIDEO_MODEL", "klingai/kling-v2.6/pro/image-to-video")

async def run_video(model: str, prompt: str) -> Dict[str, Any]:
    """
    Универсальная генерация видео через API Free.
    Ожидаем, что провайдер вернёт либо {url: "..."} либо {data: [{url: "..."}]}
    """
    if not model:
        model = DEFAULT_VIDEO_MODEL

    payload = {"model": model, "prompt": prompt}
    data = await apifree_post("/v1/videos/generations", payload)

    url = data.get("url")
    if not url and isinstance(data.get("data"), list) and data["data"]:
        url = data["data"][0].get("url")

    if not url:
        raise HTTPException(status_code=502, detail={"error": "no_url", "raw": data})

    return {"url": url, "raw": data}
